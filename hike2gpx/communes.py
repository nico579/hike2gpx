"""Recherche de villes pour recentrer la carte : les communes françaises
d'abord, puis le reste du monde.

En France, le service officiel de découpage administratif connaît chaque
commune, même minuscule, et son département. Ailleurs (Nico, 2026-10-22 :
« je cherche "madrid", aucune réponse ! »), Nominatim, le moteur de recherche
d'OpenStreetMap : le tracé hors de France repose déjà sur OSM (Overpass,
Geofabrik, BRouter). Une seule requête, à la validation et seulement quand
la France n'a rien donné, comme le demandent ses conditions d'usage.
"""
from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request

from . import __version__

API_COMMUNES = "https://geo.api.gouv.fr/communes"
API_NOMINATIM = "https://nominatim.openstreetmap.org/search"
AGENT = f"hike2gpx/{__version__} (+https://github.com/nico579/hike2gpx)"
LIMITE = 8


def _lire_json(url: str, ouvrir):
    demande = urllib.request.Request(url, headers={"User-Agent": AGENT})
    with (ouvrir or urllib.request.urlopen)(demande, timeout=8) as reponse:
        brut = reponse.read(65537)
    if len(brut) > 65536:
        raise ValueError("réponse trop volumineuse")
    donnees = json.loads(brut)
    if not isinstance(donnees, list):
        raise ValueError("réponse inattendue")
    return [element for element in donnees if isinstance(element, dict)]


def _point(lat, lon):
    """(lat, lon) en nombres, ou None si l'une des deux n'est pas une
    coordonnée valable. Nominatim les donne en chaînes."""
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    if math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
        return lat, lon
    return None


def _communes_francaises(nom: str, ouvrir) -> list:
    parametres = {"nom": nom, "fields": "nom,code,centre,departement",
                  "boost": "population", "limit": LIMITE}
    villes = []
    for ville in _lire_json(API_COMMUNES + "?" + urllib.parse.urlencode(parametres), ouvrir):
        centre = ville.get("centre")
        coords = centre.get("coordinates") if isinstance(centre, dict) else None
        point = _point(coords[1], coords[0]) if isinstance(coords, list) and len(coords) == 2 else None
        departement = ville.get("departement")
        if isinstance(ville.get("nom"), str) and point:
            villes.append({"nom": ville["nom"],
                           "detail": departement.get("nom", "") if isinstance(departement, dict) else "",
                           "lat": point[0], "lon": point[1]})
    return villes


def _lieux_du_monde(nom: str, ouvrir) -> list:
    """Villes et villages (featureType=settlement), noms en français quand
    OSM les connaît (« Barcelone »). Le détail : la région et le pays."""
    parametres = {"q": nom, "format": "jsonv2", "addressdetails": 1, "limit": LIMITE,
                  "featureType": "settlement", "accept-language": "fr,en"}
    villes = []
    for lieu in _lire_json(API_NOMINATIM + "?" + urllib.parse.urlencode(parametres), ouvrir):
        point = _point(lieu.get("lat"), lieu.get("lon"))
        adresse = lieu.get("address") if isinstance(lieu.get("address"), dict) else {}
        region = adresse.get("state") or adresse.get("region") or adresse.get("county")
        detail = ", ".join(p for p in (region, adresse.get("country")) if isinstance(p, str) and p)
        if isinstance(lieu.get("name"), str) and lieu["name"] and point:
            villes.append({"nom": lieu["name"], "detail": detail, "lat": point[0], "lon": point[1]})
    return villes


def chercher(payload, ouvrir=None) -> dict:
    nom = payload.get("recherche") if isinstance(payload, dict) else None
    if not isinstance(nom, str) or not 2 <= len(nom.strip()) <= 80:
        return {"erreur": "Saisissez au moins deux caractères pour rechercher une ville."}
    nom = nom.strip()
    try:
        villes = _communes_francaises(nom, ouvrir)
    except (OSError, ValueError, UnicodeError):
        villes = []     # le service français en panne : le reste du monde la couvre aussi
    if not villes:
        try:
            villes = _lieux_du_monde(nom, ouvrir)
        except (OSError, ValueError, UnicodeError) as exc:
            return {"erreur": f"Recherche de ville indisponible ({exc})."}
    villes.sort(key=lambda ville: ville["nom"].casefold() != nom.casefold())
    return {"communes": villes}
