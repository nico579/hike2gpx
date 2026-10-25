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

from .. import __version__
from ..franchissements import ErreurDonnees, VueRemplacee, bornes_tuile, tuiles_zone

journal = logging.getLogger(__name__)

WFS = "https://data.geopf.fr/wfs/ows"
COUCHE = "BDTOPO_V3:troncon_de_route"
PAGE = 5000                 # le service ne rend pas davantage par requête
PAGES_MAX = 20
TTL_S = 30 * 86400
VERSION_CACHE = 1
ATTRIBUTS = ("nature", "acces_pieton", "acces_vehicule_leger", "prive")
NATURES_CHEMINS = {"Chemin", "Route empierrée", "Sentier", "Escalier"}


def chemin_affichable(troncon):
    return troncon.get("nature") in NATURES_CHEMINS

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


def troncons_zone(sud: float, ouest: float, nord: float, est: float, dossier, *, continuer=None,
                  suivi=None, **options) -> list:
    """Tronçons des tuiles de la zone ; un tronçon à cheval sur deux tuiles
    n'est rendu qu'une fois. continuer() faux (vue quittée) arrête la lecture ;
    suivi(faites, total), tuile après tuile, pour la barre de la page."""
    vus, resultat = set(), []
    tuiles = tuiles_zone(sud, ouest, nord, est)
    if suivi:
        suivi(0, len(tuiles))
    for k, (i, j) in enumerate(tuiles):
        if continuer and not continuer():
            raise VueRemplacee()
        for t in charger_tuile(i, j, dossier, **options):
            if t["id"] not in vus:
                vus.add(t["id"])
                resultat.append(t)
        if suivi:
            suivi(k + 1, len(tuiles))
    return resultat


def troncons_gpkg(gpkg, sud: float, ouest: float, nord: float, est: float) -> list:
    """Extrait local IGN par emprise : même format normalisé que le WFS.

    Utilisé uniquement par le job serveur. Le RTree du GeoPackage borne la
    lecture ; la reprojection et l'intersection exacte traitent les frontières
    courbes et les tronçons à cheval sur deux mailles.
    """
    import sqlite3
    from contextlib import closing
    from shapely import from_wkb, transform
    from shapely.geometry import box
    from pyproj import Transformer

    projecteur = Transformer.from_crs(4326, 2154, always_xy=True)
    inverse = Transformer.from_crs(2154, 4326, always_xy=True)
    points_bord = [(ouest + (est - ouest) * k / 8, lat)
                   for lat in (sud, nord) for k in range(9)]
    points_bord += [(lon, sud + (nord - sud) * k / 8)
                    for lon in (ouest, est) for k in range(9)]
    projetes = [projecteur.transform(lon, lat) for lon, lat in points_bord]
    xs, ys = zip(*projetes)
    emprise = box(ouest, sud, est, nord)
    requete = """SELECT t.cleabs, t.nature, t.acces_pieton,
                        t.acces_vehicule_leger, t.prive, t.geometrie
                 FROM rtree_troncon_de_route_geometrie r
                 JOIN troncon_de_route t ON t.fid = r.id
                 WHERE r.minx <= ? AND r.maxx >= ? AND r.miny <= ? AND r.maxy >= ?"""
    troncons = []
    with closing(sqlite3.connect(f"file:{Path(gpkg).resolve().as_posix()}?mode=ro", uri=True)) as base:
        for identifiant, nature, acces, vehicule, prive, blob in base.execute(
                requete, (max(xs), min(xs), max(ys), min(ys))):
            if not blob or blob[:2] != b"GP":
                raise ErreurDonnees("Géométrie BD TOPO GeoPackage invalide.")
            tailles = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
            taille = tailles.get((blob[3] >> 1) & 7)
            if taille is None:
                raise ErreurDonnees("Enveloppe GeoPackage inconnue.")
            geometrie = transform(from_wkb(blob[8 + taille:]), inverse.transform,
                                  interleaved=False)
            if not geometrie.intersects(emprise):
                continue
            lignes = [geometrie] if geometrie.geom_type == "LineString" else list(geometrie.geoms)
            for k, ligne in enumerate(lignes):
                if ligne.geom_type != "LineString" or len(ligne.coords) < 2:
                    continue
                troncons.append({"id": f"{identifiant}-{k}", "nature": nature,
                                 "acces_pieton": acces, "acces_vehicule_leger": vehicule,
                                 "prive": prive,
                                 "pts": [[round(point[1], 6), round(point[0], 6)]
                                         for point in ligne.coords]})
    return troncons
