"""Chemins swissTLM3D suisses praticables à pied, lus par petite emprise."""
import urllib.parse

from ..franchissements import ErreurDonnees
from .core import _json, _lignes


def lire(s, w, n, e):
    resultat, vus = [], set()
    for offset in range(0, 20_000, 200):
        q = {"geometry": f"{w},{s},{e},{n}", "geometryType": "esriGeometryEnvelope",
             "sr": 4326, "layers": "all:ch.swisstopo.swisstlm3d-strassen",
             "tolerance": 0, "returnGeometry": "true", "geometryFormat": "geojson",
             "limit": 200, "offset": offset, "mapExtent": f"{w},{s},{e},{n}",
             "imageDisplay": "1024,1024,96"}
        donnees = _json("https://api3.geo.admin.ch/rest/services/api/MapServer/identify?"
                        + urllib.parse.urlencode(q))
        nouveaux = 0
        for objet in donnees.get("results", []):
            identifiant = objet.get("id")
            if identifiant is None or identifiant in vus:
                continue
            vus.add(identifiant)
            nouveaux += 1
            attrs = objet.get("properties") or objet.get("attributes") or {}
            if attrs.get("objektart") not in (15, 16, 17, 18) \
                    or attrs.get("verkehrsbeschraenkung") != 100:
                continue
            for rang, points in enumerate(_lignes(objet.get("geometry"))):
                if len(points) >= 2:
                    resultat.append({"id": f"{identifiant}:{rang}",
                                     "nature": f"Weg {attrs['objektart']}", "pts": points})
        if not nouveaux:
            return resultat
    raise ErreurDonnees("Trop de chemins swissTLM3D dans une tuile.")
