"""Voies ATKIS de basemap.de, lues par petite emprise via ses tuiles vectorielles.

Le niveau 15 est le plus détaillé du service. Les géométries restent celles
d'une carte de présentation, donc leur raccordement est à vérifier avant la
randonnée. Les portions de Bavière et de Thuringe proviennent des WFS natifs.
"""
from __future__ import annotations

import concurrent.futures
import math
import urllib.error
import urllib.request

import mapbox_vector_tile
from shapely.geometry import LineString, box

from .. import __version__
from ..franchissements import ErreurDonnees

URL = "https://sgx.geodatenzentrum.de/gdz_basemapde_vektor/tiles/v2/bm_web_de_3857/{z}/{x}/{y}.pbf"
ZOOM = 15
TAILLE = 4096
LANDS_VECTOR = {"BB", "BE", "BW", "HB", "HE", "HH", "MV", "NI", "NW",
                "RP", "SH", "SL", "SN", "ST"}
CLASSES = {
    "(Kletter-)Steig im Gebirge": "Weg/Pfad/Steig",
    "Fußweg": "Weg/Pfad/Steig",
    "Hauptwirtschaftsweg": "Wirtschaftsweg",
    "Rad- und Fußweg": "Weg/Pfad/Steig",
    "Weg, Pfad, Steig": "Weg/Pfad/Steig",
    "Wirtschaftsweg": "Wirtschaftsweg",
}


def _x(lon):
    return (lon + 180) / 360 * (1 << ZOOM)


def _y(lat):
    lat = max(-85.05112878, min(85.05112878, lat))
    return (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * (1 << ZOOM)


def _lon(x):
    return x / (1 << ZOOM) * 360 - 180


def _lat(y):
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / (1 << ZOOM)))))


def _lignes(geometrie):
    if geometrie.is_empty:
        return
    if geometrie.geom_type == "LineString":
        yield geometrie
    elif hasattr(geometrie, "geoms"):
        for partie in geometrie.geoms:
            yield from _lignes(partie)


def _lire_tuile(x, y, bornes, ouvrir):
    url = URL.format(z=ZOOM, x=x, y=y)
    try:
        demande = urllib.request.Request(url, headers={"User-Agent": f"hike2gpx/{__version__}"})
        with ouvrir(demande, timeout=30) as reponse:
            contenu = reponse.read()
        if not contenu:
            return []
        donnees = mapbox_vector_tile.decode(contenu, default_options={"y_coord_down": True})
    except urllib.error.HTTPError as exc:
        if exc.code == 404:  # tuile sans voie, par exemple en mer
            return []
        raise ErreurDonnees(f"basemap.de : tuile de chemins indisponible ({exc}).") from exc
    except Exception as exc:
        raise ErreurDonnees(f"basemap.de : tuile de chemins indisponible ({exc}).") from exc
    couche = donnees.get("Verkehrslinie", {"features": [], "extent": TAILLE})
    if not isinstance(couche.get("features"), list):
        raise ErreurDonnees("basemap.de : couche Verkehrslinie invalide.")
    taille = couche.get("extent", TAILLE)
    sud, ouest, nord, est = bornes
    zone = box(ouest, sud, est, nord)
    tuile = box(0, 0, taille, taille)
    limites_lat = (sud, nord, _lat(y + 1), _lat(y))
    limites_lon = (ouest, est, _lon(x), _lon(x + 1))
    resultat = []
    for indice, objet in enumerate(couche["features"]):
        props = objet["properties"]
        land, classe = props.get("land"), props.get("klasse")
        if land not in LANDS_VECTOR or classe not in CLASSES:
            continue
        geom = objet["geometry"]
        if geom["type"] not in ("LineString", "MultiLineString"):
            continue
        lignes = [geom["coordinates"]] if geom["type"] == "LineString" else geom["coordinates"]
        for rang, points in enumerate(lignes):
            if len(points) < 2:
                continue
            for segment, ligne in enumerate(_lignes(LineString(points).intersection(tuile))):
                coordonnees = [(_lon(x + px / taille), _lat(y + py / taille)) for px, py in ligne.coords]
                for morceau, section in enumerate(_lignes(LineString(coordonnees).intersection(zone))):
                    pts = [[lat, lon] for lon, lat in section.coords]
                    if len(pts) >= 2 and pts[0] != pts[-1]:
                        bouts = [any(abs(lat - limite) < 1e-8 for limite in limites_lat) or
                                 any(abs(lon - limite) < 1e-8 for limite in limites_lon)
                                 for lat, lon in (pts[0], pts[-1])]
                        resultat.append({"id": f"BM:{ZOOM}:{x}:{y}:{indice}:{rang}:{segment}:{morceau}",
                                         "land": land, "niveau": props.get("ebene", 0),
                                         "bords": bouts, "nature": CLASSES[classe], "pts": pts})
    return resultat


def lire_tuile(bornes, *, ouvrir=urllib.request.urlopen):
    """Ne lit que les tuiles vectorielles qui touchent l'emprise de 0,05°."""
    sud, ouest, nord, est = bornes
    if not (-90 <= sud < nord <= 90 and -180 <= ouest < est <= 180):
        raise ValueError("Emprise basemap.de invalide.")
    xs = range(math.floor(_x(ouest)), math.floor(_x(est)) + 1)
    ys = range(math.floor(_y(nord)), math.floor(_y(sud)) + 1)
    couples = [(x, y) for x in xs for y in ys]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        troncons = pool.map(lambda xy: _lire_tuile(*xy, bornes, ouvrir), couples)
        return [troncon for groupe in troncons for troncon in groupe]
