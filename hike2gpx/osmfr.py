"""Extraits d'OpenStreetMap France : la France métropolitaine en régions et en
départements (download.openstreetmap.fr). Un département pèse quatre à cinq
fois moins qu'une région (le Var 83 Mo, la PACA 391 Mo chez Geofabrik) : il
est prêt en une quarantaine de secondes, import compris, quand la PACA en
demande plus de trois minutes (rapport du 2026-10-20 : 37,9 s contre 204,8 s).

Il ne sert pourtant qu'en attendant. OSM France coupe net les voies à sa
frontière (197 chemins et clôtures incomplets dans le Var), là où Geofabrik
les garde entières : la région de Geofabrik se prépare donc aussitôt après,
et prend le relais dès qu'elle est là (Nico, 2026-10-20 : « comme ça, on a la
main rapidement sur le var, on peut travailler, pendant ce temps paca se
prépare »). Ses extraits portent pour cela voies_coupees, que lisent
geofabrik.extrait_de_tuile et application._extrait_automatique.

OSM France ne publie pas d'index JSON comme Geofabrik : la liste se bâtit
depuis ses pages d'index et ses contours (.poly), en tâche de fond, et se garde
un mois au dossier de données (geofabrik.Index). Ses régions ont la forme de
celles de Geofabrik (geofabrik._region) : la règle « le plus petit extrait qui
contient toute la tuile » y prend d'elle-même le département, sinon la région
de l'arborescence (les régions d'avant 2016). Chaque fichier a son MD5 à côté
(var.osm.pbf.md5), comme chez Geofabrik.
"""
from __future__ import annotations

import logging
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import geofabrik

journal = logging.getLogger(__name__)

EXTRAITS = "https://download.openstreetmap.fr/extracts/europe/france/"
CONTOURS = "https://download.openstreetmap.fr/polygons/europe/france/"
VERSION_INDEX = 1
PETITS_MOTS = {"de", "du", "des", "la", "le", "les", "et", "sur", "en", "d", "l"}


def _liens(page: str) -> list:
    """Les répertoires (« alsace/ ») et les extraits (« alsace.osm.pbf ») d'une
    page d'index ; « alsace-latest.osm.pbf » est le même fichier, sans MD5 à
    côté de son nom."""
    return re.findall(r'href="([a-z0-9_]+/|[a-z0-9_]+\.osm\.pbf)"', page)


def _nom(brut: str) -> str:
    """« alpes_de_haute_provence » -> « Alpes-de-Haute-Provence » (sans accents :
    l'arborescence n'en a pas)."""
    return "-".join(mot if rang and mot in PETITS_MOTS else mot.capitalize()
                    for rang, mot in enumerate(brut.split("_")))


def lire_poly(texte: str) -> list:
    """Les anneaux d'un contour .poly (format d'Osmosis : un nom, puis des
    anneaux de « lon lat » fermés par END) en un seul polygone : la règle
    pair-impair de geofabrik._dans y traite trous (« !2 ») et îles."""
    anneaux, anneau = [], None
    for ligne in texte.splitlines()[1:]:
        mots = ligne.split()
        if not mots:
            continue
        if mots[0] == "END":
            if anneau is not None and len(anneau) >= 3:
                anneaux.append(anneau)
            anneau = None
        elif anneau is None:
            anneau = []             # en-tête d'anneau : « 1 », « !2 »
        else:
            anneau.append((float(mots[0]), float(mots[1])))
    if not anneaux:
        raise ValueError("contour vide")
    return [anneaux]


def _region(brut: str, pbf: str, poly: str, genre: str) -> dict:
    polygones = lire_poly(poly)
    lons = [x for anneau in polygones[0] for x, _ in anneau]
    lats = [y for anneau in polygones[0] for _, y in anneau]
    return {"id": "fr-" + brut.replace("_", "-"), "nom": _nom(brut), "pbf": pbf, "genre": genre,
            "bornes": (min(lats), min(lons), max(lats), max(lons)), "polygones": polygones,
            "voies_coupees": True}


def _lire(url: str, ouvrir) -> str:
    def lire():
        with ouvrir(urllib.request.Request(url, headers=geofabrik.AGENT), timeout=geofabrik.DELAI_S) as reponse:
            return reponse.read().decode("utf-8", "replace")
    return geofabrik._avec_essais(lire, time.sleep)


def batir(ouvrir=None) -> list:
    """L'index de la France : les régions de l'arborescence, puis leurs
    départements, chacun avec son contour. Un contour introuvable écarte son
    seul département, que sa région couvre encore."""
    ouvrir = ouvrir or urllib.request.urlopen
    racine = _liens(_lire(EXTRAITS, ouvrir))
    regions = [lien[:-1] for lien in racine if lien.endswith("/") and f"{lien[:-1]}.osm.pbf" in racine]
    with ThreadPoolExecutor(8) as pool:
        pages = list(pool.map(lambda region: _liens(_lire(f"{EXTRAITS}{region}/", ouvrir)), regions))
        a_lire = [(region, f"{EXTRAITS}{region}.osm.pbf", f"{CONTOURS}{region}.poly", "region") for region in regions]
        for region, liens in zip(regions, pages):
            a_lire += [(lien[:-8], f"{EXTRAITS}{region}/{lien}", f"{CONTOURS}{region}/{lien[:-8]}.poly", "departement")
                       for lien in liens if lien.endswith(".osm.pbf")]

        def contour(element):
            try:
                return _region(element[0], element[1], _lire(element[2], ouvrir), element[3])
            except (OSError, ValueError) as exc:
                journal.warning("Contour d'OSM France illisible, %s écarté : %s", element[0], exc)
                return None
        return [region for region in pool.map(contour, a_lire) if region]


INDEX = geofabrik.Index("d'OSM France", f"osmfr-v{VERSION_INDEX}.json", batir)


def regions(dossier, **options) -> list:
    """Les régions et départements d'OSM France ; une liste vide le temps que
    l'index se bâtisse, la première fois (geofabrik.Index)."""
    return INDEX.regions(dossier, **options)
