"""Lecture, cache et registre communs aux sources de chemins officiels."""
from __future__ import annotations

import http.client
import json
import logging
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from nico579_commons import atomique

from .. import __version__, en_bloc
from ..franchissements import ErreurDonnees, VueRemplacee, bornes_tuile, tuiles_zone

journal = logging.getLogger(__name__)
TTL_S = 30 * 86400
PAGE = 2000
ESSAIS, PAUSE_S = 3, 5.0


def lire_json(url: str, nom: str, delai_s: float = 120.0):
    """Le JSON d'un service officiel, en trois essais. Un lot de case entière
    lit des milliers de tuiles : une réponse coupée (IncompleteRead, essai
    GitHub Actions du 2026-10-27), un délai dépassé ou une erreur 5xx finit
    toujours par arriver, et ne doit pas perdre une heure de fabrication.
    Une erreur 4xx, elle, ne guérit pas en réessayant."""
    demande = urllib.request.Request(url, headers={"User-Agent": f"hike2gpx/{__version__}"})
    derniere = None
    for essai in range(ESSAIS):
        try:
            with urllib.request.urlopen(demande, timeout=delai_s) as reponse:
                return json.loads(reponse.read())
        except urllib.error.HTTPError as exc:
            if exc.code < 500 and exc.code != 429:
                raise ErreurDonnees(f"{nom} indisponible ({exc}).") from exc
            derniere = exc
        except (OSError, ValueError, http.client.HTTPException) as exc:     # délai, coupure, JSON tronqué
            derniere = exc
        if essai < ESSAIS - 1:
            journal.info("%s : essai %d en échec (%s), nouvel essai", nom, essai + 1, derniere)
            time.sleep(PAUSE_S * (essai + 1))
    raise ErreurDonnees(f"{nom} indisponible ({derniere}).") from derniere


def _json(url):
    donnees = lire_json(url, "Source officielle")
    if not isinstance(donnees, dict) or "error" in donnees:
        raise ErreurDonnees(f"Réponse officielle invalide : {donnees.get('error') if isinstance(donnees, dict) else donnees}")
    return donnees


def _point(p) -> bool:
    return isinstance(p, (list, tuple)) and len(p) >= 2 \
        and all(isinstance(v, (int, float)) and math.isfinite(v) for v in p[:2])


def lignes(geometrie, arrondi: int | None = None) -> list:
    """Lignes [[lat, lon], …] d'une géométrie Esri (paths) ou GeoJSON
    (LineString, MultiLineString), points en lon, lat[, alt]. Un point non
    numérique ou non fini est écarté, une ligne de moins de deux points aussi.
    arrondi : décimales gardées (None : toutes)."""
    if not isinstance(geometrie, dict):
        return []
    genre, coordonnees = geometrie.get("type"), geometrie.get("coordinates")
    brutes = geometrie["paths"] if "paths" in geometrie else [coordonnees] if genre == "LineString" \
        else coordonnees if genre == "MultiLineString" else []
    resultat = []
    for ligne in brutes or ():
        points = [[p[1], p[0]] if arrondi is None else [round(p[1], arrondi), round(p[0], arrondi)]
                  for p in ligne or () if _point(p)]
        if len(points) >= 2:
            resultat.append(points)
    return resultat


@dataclass(frozen=True)
class Source:
    cle: str
    pays: str
    nom: str
    module: object
    calque: str
    borne: tuple | None = None  # sud, ouest, nord, est ; seulement si service régional

    def disponible(self, zone):
        return self.borne is None or (zone[0] >= self.borne[0] and zone[1] >= self.borne[1]
                                      and zone[2] <= self.borne[2] and zone[3] <= self.borne[3])


class TuilesOfficielles:
    """Cache et parcours de tuiles communs aux services officiels : un cache
    JSON par tuile de 0,05°, renouvelé après TTL_S, et le parcours d'une zone
    sans doublon. Un module de fournisseur en expose les méthodes sous ses
    propres noms (lire_cache, charger_tuile, troncons_zone)."""

    def __init__(self, cle, lire, *, avec_dossier=False, version=1, par_tuile=False, nom=None):
        """lire(sud, ouest, nord, est, **options) rend les tronçons d'une tuile ;
        par_tuile : lire(i, j, **options), avec les indices de la tuile.
        avec_dossier : lire reçoit aussi le dossier des données, pour un
        service dont les fichiers se gardent sur disque (BDOT10k par powiats).
        version : à augmenter quand la source ou le format des tronçons
        change, pour ne pas mêler d'anciennes tuiles en cache aux nouvelles.
        nom : celui des messages (la clé par défaut). Les options de
        charger_tuile et troncons_zone (interroger=, pour les essais) vont à lire."""
        self.cle, self.lire, self.nom = cle, lire, nom or cle
        self.avec_dossier, self.version, self.par_tuile = avec_dossier, version, par_tuile

    def _chemin(self, i, j, dossier):
        return Path(dossier) / self.cle / f"v{self.version}_{i}_{j}.json"

    def lire_cache(self, i, j, dossier):
        cache = atomique.lire_json(self._chemin(i, j, dossier), None)
        return cache if isinstance(cache, dict) and isinstance(cache.get("troncons"), list) \
            and isinstance(cache.get("fetched_at"), (int, float)) else None

    def charger_tuile(self, i, j, dossier, *, en_ligne=True, maintenant=time.time, **options):
        with en_bloc.verrou((self.cle, i, j)):
            cache = self.lire_cache(i, j, dossier)
            if cache and (not en_ligne or maintenant() - cache["fetched_at"] < TTL_S):
                return cache["troncons"]
            if not en_ligne:
                raise ErreurDonnees(f"Hors connexion : chemins {self.nom} de cette zone jamais chargés.")
            debut = time.monotonic()
            arguments = (i, j) if self.par_tuile else bornes_tuile(i, j)
            if self.avec_dossier:
                arguments = (*arguments, dossier)
            troncons = self.lire(*arguments, **options)
            atomique.ecrire_json(self._chemin(i, j, dossier),
                                {"fetched_at": maintenant(), "troncons": troncons}, indent=None)
            journal.info("%s : tuile %d_%d lue en %.1f s (%d tronçons)", self.nom, i, j,
                         time.monotonic() - debut, len(troncons))
            return troncons

    def troncons_zone(self, sud, ouest, nord, est, dossier, *, continuer=None, suivi=None, **options):
        """Tronçons des tuiles de la zone ; un tronçon à cheval sur deux tuiles
        n'est rendu qu'une fois. continuer() faux (vue quittée) arrête la lecture ;
        suivi(faites, total), tuile après tuile, pour la barre de la page."""
        tuiles, vus, resultat = tuiles_zone(sud, ouest, nord, est), set(), []
        if suivi:
            suivi(0, len(tuiles))
        for rang, (i, j) in enumerate(tuiles):
            if continuer and not continuer():
                raise VueRemplacee()
            for troncon in self.charger_tuile(i, j, dossier, **options):
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
                for rang, points in enumerate(lignes(objet.get("geometry"))):
                    if len(points) >= 2:
                        resultat.append({"id": f"{url.rsplit('/', 1)[-1]}:{identifiant}:{rang}",
                                         "nature": nature, "pts": points})
            if len(objets) < PAGE:
                break
        else:
            raise ErreurDonnees("Trop de chemins officiels dans une tuile.")
    return resultat


