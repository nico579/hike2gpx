"""Recherche de communes françaises pour recentrer la carte."""
from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request

from . import __version__

API_COMMUNES = "https://geo.api.gouv.fr/communes"


def chercher(payload, ouvrir=None) -> dict:
    nom = payload.get("recherche") if isinstance(payload, dict) else None
    if not isinstance(nom, str) or not 2 <= len(nom.strip()) <= 80:
        return {"erreur": "Saisissez au moins deux caractères pour rechercher une ville."}
    parametres = {"nom": nom.strip(), "fields": "nom,code,centre,departement",
                  "boost": "population", "limit": 8}
    url = API_COMMUNES + "?" + urllib.parse.urlencode(parametres)
    demande = urllib.request.Request(url, headers={"User-Agent": f"hike2gpx/{__version__}"})
    try:
        with (ouvrir or urllib.request.urlopen)(demande, timeout=8) as reponse:
            brut = reponse.read(65537)
        if len(brut) > 65536:
            raise ValueError("réponse trop volumineuse")
        donnees = json.loads(brut)
        if not isinstance(donnees, list):
            raise ValueError("réponse inattendue")
        communes = []
        for ville in donnees:
            if not isinstance(ville, dict):
                continue
            centre = ville.get("centre")
            coords = centre.get("coordinates") if isinstance(centre, dict) else None
            departement = ville.get("departement")
            if (isinstance(ville.get("nom"), str) and isinstance(coords, list) and len(coords) == 2
                    and all(isinstance(c, (float, int)) and math.isfinite(c) for c in coords)
                    and -180 <= coords[0] <= 180 and -90 <= coords[1] <= 90):
                communes.append({"nom": ville["nom"], "departement": departement.get("nom", "") if isinstance(departement, dict) else "",
                                 "lat": coords[1], "lon": coords[0]})
        communes.sort(key=lambda ville: ville["nom"].casefold() != nom.strip().casefold())
        return {"communes": communes}
    except (OSError, ValueError, UnicodeError) as exc:
        return {"erreur": f"Recherche de ville indisponible ({exc})."}
