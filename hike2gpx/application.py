"""Une instance de hike2gpx : réglages, moteur BRouter, et les routes /api/*
de la page.

Un itinéraire se calcule en quatre temps : la zone des points, élargie ;
les franchissements de cette zone ; BRouter avec leurs coupes ; puis, si le
tracé sort de la zone examinée, la zone s'agrandit et le calcul recommence,
pour qu'aucun détour ne passe par une barrière jamais vérifiée.
"""
from __future__ import annotations

import math
import re
import threading
import time
from pathlib import Path

from nico579_commons import atomique

from . import __version__, brouter, franchissements

MARGE_DEG = 0.01            # environ 1 km autour des points
MARGE_RELATIVE = 0.25
POINTS_MAX = 50
ELARGISSEMENTS = 3
_CLE_IGN = re.compile(r"^[A-Za-z0-9_\-]{0,100}$")


def zone_autour(points, marge_relative=MARGE_RELATIVE):
    lats, lons = [p[0] for p in points], [p[1] for p in points]
    marge_lat = max(MARGE_DEG, (max(lats) - min(lats)) * marge_relative)
    marge_lon = max(MARGE_DEG / max(.2, math.cos(math.radians(sum(lats) / len(lats)))),
                    (max(lons) - min(lons)) * marge_relative)
    return (round(min(lats) - marge_lat, 6), round(min(lons) - marge_lon, 6),
            round(max(lats) + marge_lat, 6), round(max(lons) + marge_lon, 6))


def contient(zone, autre, marge_deg=0.002) -> bool:
    return (zone[0] + marge_deg <= autre[0] and zone[1] + marge_deg <= autre[1]
            and autre[2] <= zone[2] - marge_deg and autre[3] <= zone[3] - marge_deg)


def union(a, b):
    return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])


def valider_points(brut) -> list:
    if not isinstance(brut, list) or not 2 <= len(brut) <= POINTS_MAX:
        raise ValueError(f"Il faut entre 2 et {POINTS_MAX} points.")
    points = []
    for p in brut:
        if not (isinstance(p, list) and len(p) == 2 and all(isinstance(v, (int, float)) for v in p)
                and -85 <= p[0] <= 85 and -180 <= p[1] <= 180):
            raise ValueError("Point invalide.")
        points.append((float(p[0]), float(p[1])))
    return points


def sur_le_trace(coordonnees, liste) -> list:
    """Franchissements que le tracé passe vraiment : il coupe l'une de leurs
    coupes. La proximité ne suffit pas : deux voies croisent parfois la même
    clôture à un mètre l'une de l'autre, l'une bloquée, l'autre non (constaté
    à Garéoult, way 1558904264). Distance comptée depuis le départ."""
    if len(coordonnees) < 2 or not liste:
        return []
    proj = franchissements.Projection(coordonnees[0][1], coordonnees[0][0])
    pts = [proj.xy(c[1], c[0]) for c in coordonnees]
    cumul = [0.0]
    grille = franchissements._Grille()
    for k, (a, b) in enumerate(zip(pts, pts[1:])):
        cumul.append(cumul[-1] + math.dist(a, b))
        grille.ajouter(k, a, b)
    resultat = []
    for f in liste:
        distances = []
        for (lon1, lat1), (lon2, lat2) in f["coupes"]:
            c, d = proj.xy(lat1, lon1), proj.xy(lat2, lon2)
            for k in grille.candidats(c, d):
                inter = franchissements._intersection(pts[k], pts[k + 1], c, d)
                if inter is not None:
                    distances.append(cumul[k] + inter[0] * (cumul[k + 1] - cumul[k]))
        if distances:
            resultat.append({**{k: f[k] for k in ("cle", "statut", "raison", "nature", "lat", "lon", "osm")},
                             "distance_m": round(min(distances))})
    return sorted(resultat, key=lambda f: f["distance_m"])


def _nombre(proprietes, cle):
    try:
        return float(proprietes.get(cle))
    except (TypeError, ValueError):
        return None


class Application:
    def __init__(self, dossier: Path):
        self.dossier = Path(dossier)
        self.installation = brouter.Installation(self.dossier)
        self.preferences = self.dossier / "preferences.json"
        self.serveur = None
        self._verrou_moteur = threading.Lock()
        self._verrou_calcul = threading.Lock()

    # ---------------------------------------------------------- réglages

    def reglages(self) -> dict:
        prefs = atomique.lire_json(self.preferences, {})
        cle = prefs.get("cle_ign") if isinstance(prefs, dict) else None
        return {"cle_ign": cle if isinstance(cle, str) and _CLE_IGN.match(cle) else ""}

    def enregistrer_reglages(self, payload) -> dict:
        cle = (payload or {}).get("cle_ign", "")
        if not isinstance(cle, str) or not _CLE_IGN.match(cle.strip()):
            return {"erreur": "Clé IGN invalide : lettres, chiffres, _ et - seulement."}
        prefs = atomique.lire_json(self.preferences, {})
        prefs = prefs if isinstance(prefs, dict) else {}
        prefs["cle_ign"] = cle.strip()
        atomique.ecrire_json(self.preferences, prefs)
        return self.reglages()

    def etat(self) -> dict:
        segments = sorted(p.stem for p in self.installation.segments.glob("*.rd5")) \
            if self.installation.segments.is_dir() else []
        return {"app": "hike2gpx", "version": __version__, "dossier": str(self.dossier),
                "moteur_installe": self.installation.installee(), "segments": segments,
                "brouter": brouter.VERSION, "poids_a_verifier": brouter.POIDS_A_VERIFIER}

    # ---------------------------------------------------------- moteur

    def moteur(self) -> int:
        with self._verrou_moteur:
            if self.serveur is None or self.serveur.processus is None or self.serveur.processus.poll() is not None:
                serveur = brouter.Serveur(self.installation)
                serveur.demarrer()
                self.serveur = serveur
            return self.serveur.port

    def arreter(self) -> None:
        with self._verrou_moteur:
            if self.serveur is not None:
                self.serveur.arreter()
                self.serveur = None

    def installer_moteur(self, _payload=None) -> dict:
        try:
            self.installation.installer()
        except (brouter.ErreurBRouter, OSError, ValueError) as exc:
            return {"erreur": str(exc)}
        return self.etat()

    def telecharger_segment(self, payload) -> dict:
        nom = (payload or {}).get("nom")
        if not isinstance(nom, str) or not re.fullmatch(r"[EW]\d{1,3}_[NS]\d{1,2}", nom):
            return {"erreur": "Nom de tuile invalide."}
        try:
            self.installation.telecharger_segment(nom)
        except brouter.ErreurBRouter as exc:
            return {"erreur": str(exc)}
        return self.etat()

    # ---------------------------------------------------------- itinéraire

    def itineraire(self, payload) -> dict:
        payload = payload or {}
        try:
            points = valider_points(payload.get("points"))
        except ValueError as exc:
            return {"erreur": str(exc)}
        strict, comparer = bool(payload.get("strict")), bool(payload.get("comparer", True))
        if not self.installation.installee():
            return {"erreur": "Le moteur BRouter n'est pas installé.", "moteur_absent": True}
        with self._verrou_calcul:
            debut = time.monotonic()
            zone = zone_autour(points)
            try:
                for essai in range(ELARGISSEMENTS):
                    manquants = [n for n in brouter.segments_zone(*zone)
                                 if not self.installation.segment_present(n)]
                    if manquants:
                        return {"erreur": "Données BRouter absentes pour cette zone.",
                                "segments_manquants": manquants}
                    liste = franchissements.franchissements_zone(*zone, self.dossier)
                    trace = brouter.calculer(self.moteur(), points, liste, strict=strict)
                    coords = trace["geometry"]["coordinates"]
                    etendue = (min(c[1] for c in coords), min(c[0] for c in coords),
                               max(c[1] for c in coords), max(c[0] for c in coords))
                    if contient(zone, etendue):
                        break
                    zone = union(zone, zone_autour([etendue[:2], etendue[2:]], 0.1))
                else:
                    return {"erreur": "Le tracé sort sans cesse de la zone examinée : rapprochez les points."}
            except (franchissements.ErreurDonnees, brouter.ErreurBRouter) as exc:
                return {"erreur": str(exc)}
            reponse = {"itineraire": trace, "zone": zone, "franchissements": liste,
                       "longueur_m": _nombre(trace["properties"], "track-length"),
                       "denivele_m": _nombre(trace["properties"], "filtered ascend"),
                       "sur_le_trace": sur_le_trace(coords, liste), "strict": strict}
            if comparer:
                try:
                    naif = brouter.calculer(self.moteur(), points, profil="hiking-mountain")
                    traverses = [f for f in sur_le_trace(naif["geometry"]["coordinates"], liste)
                                 if f["statut"] == "blocked"]
                    reponse.update(naif=naif, naif_longueur_m=_nombre(naif["properties"], "track-length"),
                                   naif_traverse=traverses)
                except brouter.ErreurBRouter:
                    reponse["naif"] = None
            reponse["duree_s"] = round(time.monotonic() - debut, 2)
            return reponse

    def routes(self):
        get = {"init": self.etat, "etat": self.etat, "reglages": self.reglages}
        post = {"itineraire": self.itineraire, "reglages": self.enregistrer_reglages,
                "segment": self.telecharger_segment, "moteur": self.installer_moteur}
        return get, post
