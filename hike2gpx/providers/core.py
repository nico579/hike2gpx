"""Lecture, cache et registre communs aux sources de chemins officiels."""
from __future__ import annotations

import logging
import math
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from nico579_commons import atomique

from .. import __version__
from ..franchissements import ErreurDonnees, VueRemplacee, bornes_tuile, tuiles_zone

journal = logging.getLogger(__name__)
TTL_S = 30 * 86400
PAGE = 2000
_verrou = threading.Lock()
_verrous = {}


def _tuile_verrou(cle):
    with _verrou:
        return _verrous.setdefault(cle, threading.Lock())


def _json(url):
    demande = urllib.request.Request(url, headers={"User-Agent": f"hike2gpx/{__version__}"})
    try:
        with urllib.request.urlopen(demande, timeout=120) as reponse:
            import json
            donnees = json.load(reponse)
    except (OSError, ValueError) as exc:
        raise ErreurDonnees(f"Source officielle indisponible ({exc}).") from exc
    if not isinstance(donnees, dict) or "error" in donnees:
        raise ErreurDonnees(f"Réponse officielle invalide : {donnees.get('error') if isinstance(donnees, dict) else donnees}")
    return donnees


def _lignes(geometrie):
    if not geometrie:
        return []
    if "paths" in geometrie:
        lignes = geometrie["paths"]
    elif geometrie.get("type") == "LineString":
        lignes = [geometrie.get("coordinates", [])]
    elif geometrie.get("type") == "MultiLineString":
        lignes = geometrie.get("coordinates", [])
    else:
        return []
    return [[[lat, lon] for lon, lat in points if math.isfinite(lat) and math.isfinite(lon)]
            for points in lignes if len(points) >= 2]


@dataclass(frozen=True)
class Source:
    cle: str
    pays: str
    nom: str
    module: object
    calque: str
    borne: tuple | None = None  # sud, ouest, nord, est ; seulement si service régional
    lecteur_local: object | None = None  # archive locale, si ce provider en offre une

    def disponible(self, zone):
        return self.borne is None or (zone[0] >= self.borne[0] and zone[1] >= self.borne[1]
                                      and zone[2] <= self.borne[2] and zone[3] <= self.borne[3])

    def troncons_pour_job(self, zone, dossier, source_locale=None):
        """Contrat commun du job serveur, indépendant du pays et du format brut."""
        if source_locale is not None:
            if self.lecteur_local is None:
                raise ValueError(f"Source locale indisponible pour {self.nom}.")
            return self.lecteur_local(source_locale, *zone)
        return self.module.troncons_zone(*zone, dossier)


class TuilesOfficielles:
    """Cache et parcours de tuiles communs aux nouveaux services officiels."""

    def __init__(self, cle, lire):
        self.cle, self.lire = cle, lire

    def _chemin(self, i, j, dossier):
        return Path(dossier) / self.cle / f"v1_{i}_{j}.json"

    def lire_cache(self, i, j, dossier):
        cache = atomique.lire_json(self._chemin(i, j, dossier), None)
        return cache if isinstance(cache, dict) and isinstance(cache.get("troncons"), list) \
            and isinstance(cache.get("fetched_at"), (int, float)) else None

    def charger_tuile(self, i, j, dossier, *, en_ligne=True, maintenant=time.time):
        with _tuile_verrou((self.cle, i, j)):
            cache = self.lire_cache(i, j, dossier)
            if cache and (not en_ligne or maintenant() - cache["fetched_at"] < TTL_S):
                return cache["troncons"]
            if not en_ligne:
                raise ErreurDonnees(f"Hors connexion : chemins {self.cle} de cette zone jamais chargés.")
            troncons = self.lire(*bornes_tuile(i, j))
            atomique.ecrire_json(self._chemin(i, j, dossier),
                                {"fetched_at": maintenant(), "troncons": troncons}, indent=None)
            journal.info("%s : tuile %d_%d, %d tronçons", self.cle, i, j, len(troncons))
            return troncons

    def troncons_zone(self, sud, ouest, nord, est, dossier, *, continuer=None, suivi=None):
        tuiles, vus, resultat = tuiles_zone(sud, ouest, nord, est), set(), []
        if suivi:
            suivi(0, len(tuiles))
        for rang, (i, j) in enumerate(tuiles):
            if continuer and not continuer():
                raise VueRemplacee()
            for troncon in self.charger_tuile(i, j, dossier):
                if troncon["id"] not in vus:
                    vus.add(troncon["id"])
                    resultat.append(troncon)
            if suivi:
                suivi(rang + 1, len(tuiles))
        return resultat


def _arcgis(couches, zone, accepter=lambda _: True):
    sud, ouest, nord, est = zone
    resultat = []
    for url, nature in couches:
        for debut in range(0, 100_000, PAGE):
            q = {"where": "1=1", "geometry": f"{ouest},{sud},{est},{nord}",
                 "geometryType": "esriGeometryEnvelope", "inSR": 4326,
                 "spatialRel": "esriSpatialRelIntersects", "outSR": 4326,
                 "outFields": "*", "f": "json", "resultRecordCount": PAGE,
                 "resultOffset": debut}
            donnees = _json(url + "/query?" + urllib.parse.urlencode(q))
            objets = donnees.get("features", [])
            for objet in objets:
                attrs = objet.get("attributes") or {}
                if not accepter(attrs):
                    continue
                identifiant = attrs.get("OBJECTID") or attrs.get("objectid") or attrs.get("FID")
                if identifiant is None:
                    raise ErreurDonnees("Identifiant d'objet officiel absent.")
                for rang, points in enumerate(_lignes(objet.get("geometry"))):
                    if len(points) >= 2:
                        resultat.append({"id": f"{url.rsplit('/', 1)[-1]}:{identifiant}:{rang}",
                                         "nature": nature, "pts": points})
            if len(objets) < PAGE:
                break
        else:
            raise ErreurDonnees("Trop de chemins officiels dans une tuile.")
    return resultat


