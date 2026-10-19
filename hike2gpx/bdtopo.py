"""Tronçons de la BD TOPO de l'IGN (routes, chemins, sentiers), lus par le
service WFS public de la Géoplateforme pour les dessiner sur la carte.

La BD TOPO montre des chemins absents d'OpenStreetMap, mais ne dit presque
rien des accès piétons : à l'essai du 18 octobre, 36 tronçons sur 5 000
autour de Garéoult portaient un accès piéton, tous « Libre ». Elle sert donc
à voir ; OpenStreetMap reste juge des passages. Même découpage que
franchissements.py, en tuiles de 0,05° ; cache de 30 jours, la BD TOPO
étant mise à jour chaque trimestre.
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from nico579_commons import atomique

from . import __version__
from .franchissements import ErreurDonnees, bornes_tuile, tuiles_zone

journal = logging.getLogger(__name__)

WFS = "https://data.geopf.fr/wfs/ows"
COUCHE = "BDTOPO_V3:troncon_de_route"
PAGE = 5000                 # le service ne rend pas davantage par requête
PAGES_MAX = 20
TTL_S = 30 * 86400
VERSION_CACHE = 1
ATTRIBUTS = ("nature", "acces_pieton", "acces_vehicule_leger", "prive")

_verrou_global = threading.Lock()
_verrous = {}


def _verrou(cle) -> threading.Lock:
    with _verrou_global:
        return _verrous.setdefault(cle, threading.Lock())


def interroger(parametres: dict, delai_s: float = 120.0) -> dict:
    url = WFS + "?" + urllib.parse.urlencode(parametres)
    demande = urllib.request.Request(url, headers={"User-Agent": f"hike2gpx/{__version__}"})
    try:
        with urllib.request.urlopen(demande, timeout=delai_s) as reponse:
            donnees = json.loads(reponse.read())
    except (OSError, ValueError) as exc:     # URLError, délai, JSON illisible
        raise ErreurDonnees(f"BD TOPO indisponible ({exc}).") from exc
    if not isinstance(donnees, dict) or not isinstance(donnees.get("features"), list):
        raise ErreurDonnees("Réponse BD TOPO inattendue.")
    return donnees


def _lignes(geometrie) -> list:
    """Lignes [[lat, lon], …] d'une géométrie GeoJSON (lon, lat[, alt])."""
    if not isinstance(geometrie, dict):
        return []
    genre, coordonnees = geometrie.get("type"), geometrie.get("coordinates")
    brutes = [coordonnees] if genre == "LineString" else coordonnees if genre == "MultiLineString" else []
    lignes = []
    for ligne in brutes or ():
        points = []
        for p in ligne:
            if not (isinstance(p, list) and len(p) >= 2 and all(isinstance(v, (int, float)) for v in p[:2])
                    and math.isfinite(p[0]) and math.isfinite(p[1])):
                break
            points.append([round(p[1], 6), round(p[0], 6)])
        else:
            if len(points) >= 2:
                lignes.append(points)
    return lignes


def lire_tuile(i: int, j: int, interroger=interroger) -> list:
    """Tronçons d'une tuile, page après page."""
    sud, ouest, nord, est = bornes_tuile(i, j)
    troncons = []
    for page in range(PAGES_MAX):
        donnees = interroger({"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
                              "TYPENAMES": COUCHE, "OUTPUTFORMAT": "application/json",
                              "BBOX": f"{sud},{ouest},{nord},{est},urn:ogc:def:crs:EPSG::4326",
                              "SORTBY": "cleabs", "COUNT": PAGE, "STARTINDEX": page * PAGE})
        for entite in donnees["features"]:
            proprietes = entite.get("properties") or {}
            for k, ligne in enumerate(_lignes(entite.get("geometry"))):
                troncons.append({"id": f"{proprietes.get('cleabs', entite.get('id'))}-{k}",
                                 **{a: proprietes.get(a) for a in ATTRIBUTS}, "pts": ligne})
        if len(donnees["features"]) < PAGE:
            return troncons
    raise ErreurDonnees("BD TOPO : trop de tronçons dans cette zone.")


def lire_cache(i: int, j: int, dossier):
    """Contenu du cache d'une tuile ({"fetched_at", "troncons"}), sans réseau, ou None."""
    cache = atomique.lire_json(Path(dossier) / "bdtopo" / f"v{VERSION_CACHE}_{i}_{j}.json", None)
    if isinstance(cache, dict) and isinstance(cache.get("troncons"), list) \
            and isinstance(cache.get("fetched_at"), (int, float)):
        return cache
    return None


def charger_tuile(i: int, j: int, dossier, *, en_ligne: bool = True, interroger=interroger,
                  maintenant=time.time) -> list:
    chemin = Path(dossier) / "bdtopo" / f"v{VERSION_CACHE}_{i}_{j}.json"
    with _verrou(("bdtopo", i, j)):
        cache = atomique.lire_json(chemin, None)
        if isinstance(cache, dict) and isinstance(cache.get("troncons"), list) \
                and isinstance(cache.get("fetched_at"), (int, float)) \
                and (not en_ligne or maintenant() - cache["fetched_at"] < TTL_S):
            return cache["troncons"]
        if not en_ligne:
            raise ErreurDonnees("Hors connexion : chemins BD TOPO de cette zone jamais chargés.")
        debut = time.monotonic()
        troncons = lire_tuile(i, j, interroger)
        journal.info("BD TOPO : tuile %d_%d lue en %.1f s (%d tronçons)", i, j, time.monotonic() - debut,
                     len(troncons))
        atomique.ecrire_json(chemin, {"version": VERSION_CACHE, "fetched_at": maintenant(),
                                      "troncons": troncons}, indent=None)
        return troncons


def troncons_zone(sud: float, ouest: float, nord: float, est: float, dossier, **options) -> list:
    """Tronçons des tuiles de la zone ; un tronçon à cheval sur deux tuiles
    n'est rendu qu'une fois."""
    vus, resultat = set(), []
    for i, j in tuiles_zone(sud, ouest, nord, est):
        for t in charger_tuile(i, j, dossier, **options):
            if t["id"] not in vus:
                vus.add(t["id"])
                resultat.append(t)
    return resultat
