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

import logging
import urllib.parse

from ..franchissements import ErreurDonnees, VueRemplacee, bornes_tuile  # noqa: F401  (bdtopo.VueRemplacee)
from .core import TTL_S, TuilesOfficielles, lignes, lire_json  # noqa: F401  (TTL_S : bdtopo.TTL_S)

journal = logging.getLogger(__name__)

WFS = "https://data.geopf.fr/wfs/ows"
COUCHE = "BDTOPO_V3:troncon_de_route"
PAGE = 5000                 # le service ne rend pas davantage par requête
PAGES_MAX = 20
VERSION_CACHE = 1
ATTRIBUTS = ("nature", "acces_pieton", "acces_vehicule_leger", "prive")

def interroger(parametres: dict, delai_s: float = 120.0) -> dict:
    donnees = lire_json(WFS + "?" + urllib.parse.urlencode(parametres), "BD TOPO", delai_s)
    if not isinstance(donnees, dict) or not isinstance(donnees.get("features"), list):
        raise ErreurDonnees("Réponse BD TOPO inattendue.")
    return donnees


def _lignes(geometrie) -> list:
    """Lignes [[lat, lon], …] d'une géométrie GeoJSON, au micro-degré (10 cm)."""
    return lignes(geometrie, arrondi=6)


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


# Le cache et le parcours des tuiles, communs aux sources officielles. La
# lambda relit lire_tuile à chaque appel : les essais peuvent la remplacer.
_TUILES = TuilesOfficielles("bdtopo", lambda i, j, **options: lire_tuile(i, j, **options),
                            par_tuile=True, version=VERSION_CACHE, nom="BD TOPO")
lire_cache = _TUILES.lire_cache
charger_tuile = _TUILES.charger_tuile
troncons_zone = _TUILES.troncons_zone
