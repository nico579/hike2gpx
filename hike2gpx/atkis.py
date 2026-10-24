"""Chemins du Basis-DLM allemand, lus par zone comme la BD TOPO.

Les WFS de Thuringe et de Bavière servent leurs tronçons par emprise ; les
autres Länder passent par les tuiles vectorielles officielles de basemap.de.
Chaque tuile de 0,05° est gardée trente jours. Les voies ne décrivent pas
l'accès piéton : un chemin absent d'OSM doit toujours être vérifié sur place.
"""
from __future__ import annotations

import logging
import math
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from nico579_commons import atomique

from . import __version__, basemap_atkis
from .franchissements import ErreurDonnees, VueRemplacee, bornes_tuile, tuiles_zone

journal = logging.getLogger(__name__)
WFS_NS = "{http://www.opengis.net/wfs/2.0}"
GML_NS = "{http://www.opengis.net/gml/3.2}"
PAGE = 1000
PAGES_MAX = 20
TTL_S = 30 * 86400
VERSION_CACHE = 2

# Bornes larges : une tuile de frontière interroge les deux WFS et chacun
# rend seulement ses objets. basemap.de fournit les quatorze autres Länder.
SOURCES = {
    "TH": {"url": "https://www.geoproxy.geoportal-th.de/geoproxy/services/adv_atkis_wfs",
           "prefixe": "dlm", "namespace": "http://www.adv-online.de/namespaces/adv/gid/7.1/dlm",
           "geometrie": "geom", "crs": "EPSG:4326", "ordre": "lonlat",
           "bornes": (50.1, 9.7, 51.8, 12.8),
           "types": (("AX_WEGPFADSTEIG", "Weg/Pfad/Steig"),
                     ("AX_FAHRWEGACHSE", "Wirtschaftsweg"))},
    "BY": {"url": "https://geoservices.bayern.de/wfs/v1/ogc_atkis_basisdlm.cgi",
           "prefixe": "adv", "namespace": "http://www.adv-online.de/namespaces/adv/gid/7.1",
           "geometrie": "position", "crs": "urn:ogc:def:crs:EPSG::4326", "ordre": "latlon",
           "bornes": (47.1, 8.8, 50.6, 14.0),
           "types": (("AX_WegPfadSteig", "Weg/Pfad/Steig"),
                     ("AX_Fahrwegachse", "Wirtschaftsweg"))},
}

_verrou_global = threading.Lock()
_verrous = {}


def _verrou(cle):
    with _verrou_global:
        return _verrous.setdefault(cle, threading.Lock())


def _intersecte(a, b):
    return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]


def _filtre(source, bornes):
    sud, ouest, nord, est = bornes
    if source["ordre"] == "latlon":
        debut, fin = f"{sud} {ouest}", f"{nord} {est}"
    else:
        debut, fin = f"{ouest} {sud}", f"{est} {nord}"
    p = source["prefixe"]
    return (f"<fes:Filter xmlns:fes='http://www.opengis.net/fes/2.0' "
            f"xmlns:gml='http://www.opengis.net/gml/3.2' xmlns:{p}='{source['namespace']}'>"
            f"<fes:BBOX><fes:ValueReference>{p}:{source['geometrie']}</fes:ValueReference>"
            f"<gml:Envelope srsName='{source['crs']}'>"
            f"<gml:lowerCorner>{debut}</gml:lowerCorner><gml:upperCorner>{fin}</gml:upperCorner>"
            "</gml:Envelope></fes:BBOX></fes:Filter>")


def interroger(source, parametres, delai_s=120):
    url = source["url"] + "?" + urllib.parse.urlencode(parametres)
    demande = urllib.request.Request(url, headers={"User-Agent": f"hike2gpx/{__version__}"})
    try:
        with urllib.request.urlopen(demande, timeout=delai_s) as reponse:
            racine = ET.fromstring(reponse.read())
    except (OSError, ET.ParseError) as exc:
        raise ErreurDonnees(f"ATKIS indisponible ({exc}).") from exc
    if racine.tag.endswith("ExceptionReport"):
        raise ErreurDonnees("ATKIS : " + " ".join(racine.itertext()))
    if racine.tag != WFS_NS + "FeatureCollection":
        raise ErreurDonnees("Réponse ATKIS inattendue.")
    return racine


def lire_tuile(i, j, interroger=interroger):
    bornes = bornes_tuile(i, j)
    troncons = basemap_atkis.lire_tuile(bornes)
    for land, source in SOURCES.items():
        if not _intersecte(bornes, source["bornes"]):
            continue
        filtre = _filtre(source, bornes)
        for type_nom, nature in source["types"]:
            for page in range(PAGES_MAX):
                racine = interroger(source, {"SERVICE": "WFS", "VERSION": "2.0.0",
                    "REQUEST": "GetFeature", "TYPENAMES": f"{source['prefixe']}:{type_nom}",
                    "SRSNAME": "EPSG:4326", "FILTER": filtre, "COUNT": PAGE,
                    "STARTINDEX": page * PAGE})
                membres = racine.findall(WFS_NS + "member")
                for membre_index, membre in enumerate(membres):
                    objet = next(iter(membre), None)
                    if objet is None:
                        continue
                    identifiant = objet.attrib.get(GML_NS + "id") or f"{type_nom}-{page * PAGE + membre_index}"
                    for rang, pos in enumerate(objet.findall(".//" + GML_NS + "posList")):
                        if not pos.text:
                            continue
                        try:
                            valeurs = [float(v) for v in pos.text.split()]
                        except ValueError as exc:
                            raise ErreurDonnees("Coordonnées ATKIS inattendues.") from exc
                        if len(valeurs) % 2 or not all(math.isfinite(v) for v in valeurs):
                            raise ErreurDonnees("Coordonnées ATKIS inattendues.")
                        pts = [[a, b] if source["ordre"] == "latlon" else [b, a]
                               for a, b in zip(valeurs[::2], valeurs[1::2])]
                        if len(pts) >= 2:
                            troncons.append({"id": f"{land}:{identifiant}-{rang}",
                                             "land": land, "nature": nature, "pts": pts})
                if len(membres) < PAGE:
                    break
            else:
                raise ErreurDonnees(f"ATKIS : plus de {PAGE * PAGES_MAX} tronçons par type dans cette tuile.")
    return troncons


def lire_cache(i, j, dossier):
    cache = atomique.lire_json(Path(dossier) / "atkis" / f"v{VERSION_CACHE}_{i}_{j}.json", None)
    if isinstance(cache, dict) and isinstance(cache.get("troncons"), list) \
            and isinstance(cache.get("fetched_at"), (int, float)):
        return cache
    return None


def charger_tuile(i, j, dossier, *, en_ligne=True, interroger=interroger, maintenant=time.time):
    chemin = Path(dossier) / "atkis" / f"v{VERSION_CACHE}_{i}_{j}.json"
    with _verrou((i, j)):
        cache = lire_cache(i, j, dossier)
        if cache and (not en_ligne or maintenant() - cache["fetched_at"] < TTL_S):
            return cache["troncons"]
        if not en_ligne:
            raise ErreurDonnees("Hors connexion : chemins ATKIS de cette zone jamais chargés.")
        debut = time.monotonic()
        troncons = lire_tuile(i, j, interroger)
        journal.info("ATKIS : tuile %d_%d lue en %.1f s (%d tronçons)", i, j,
                     time.monotonic() - debut, len(troncons))
        atomique.ecrire_json(chemin, {"version": VERSION_CACHE, "fetched_at": maintenant(),
                                    "troncons": troncons}, indent=None)
        return troncons


def troncons_zone(sud, ouest, nord, est, dossier, *, continuer=None, suivi=None, **options):
    vus, resultat = set(), []
    tuiles = tuiles_zone(sud, ouest, nord, est)
    if suivi:
        suivi(0, len(tuiles))
    for k, (i, j) in enumerate(tuiles):
        if continuer and not continuer():
            raise VueRemplacee()
        for troncon in charger_tuile(i, j, dossier, **options):
            if troncon["id"] not in vus:
                vus.add(troncon["id"])
                resultat.append(troncon)
        if suivi:
            suivi(k + 1, len(tuiles))
    return resultat
