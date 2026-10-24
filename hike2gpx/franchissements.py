"""Franchissements entre les voies praticables à pied et les barrières
d'OpenStreetMap, sur toute une zone.

gpx2elev vérifie une trace déjà faite ; hike2gpx examine d'avance tout le
réseau d'une zone, pour que le calcul d'itinéraire évite ce qui bloque. Le
jugement d'une barrière (bloquante, à vérifier, franchissable) est celui de
gpx2elev, recopié dans regles.py. Ce fichier n'ajoute que ce qu'exige un
réseau entier :

- une barrière qui s'arrête sur un chemin, ou qui le touche et repart du même
  côté, ne le traverse pas ; un chemin sur un pont ou dans un tunnel non plus ;
- une barrière qui se termine à moins de 2 m du chemin se contourne ;
- un sentier balisé (relation route=hiking ou foot) passe forcément quelque
  part : une barrière qui le bloquerait y devient « à vérifier » ;
- chaque franchissement retenu porte des coupes, petits segments posés en
  travers de la voie, que BRouter reçoit comme lignes interdites (paramètre
  polylines). Sans poids, une coupe retire le tronçon du calcul ; avec un
  poids, elle le rend seulement coûteux.

Les données viennent d'Overpass, par tuiles de 0,05° gardées sept jours en
cache, comme dans gpx2elev. Une donnée absente ne prouve jamais qu'un passage
est libre : si Overpass ne répond pas, le calcul s'arrête au lieu de
continuer sans les barrières.
"""
from __future__ import annotations

import json
import logging
import math
import re
import sqlite3
import threading
import time
from functools import lru_cache
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

from nico579_commons import atomique

from . import __version__, regles

journal = logging.getLogger(__name__)

ENDPOINT = "https://overpass-api.de/api/interpreter"
MODE = "foot"
TUILE_DEG = 0.05
TTL_S = 7 * 86400
# Format du cache Overpass, et version des règles : augmenter la seconde dès
# qu'un jugement change, l'analyse en cache est alors refaite.
VERSION_DONNEES = 1
VERSION_ANALYSE = 3         # 2 : ouvertures voisines (B01), liens nuls (B08) ; 3 : horaires et conditions (B07)
MAX_OCTETS = 256 * 1024 * 1024
TENTATIVES = 3

VOIES_EXCLUES = ("motorway", "motorway_link", "trunk", "trunk_link", "construction",
                 "proposed", "abandoned", "razed", "disused", "platform", "raceway",
                 "bus_guideway", "busway", "elevator", "corridor", "via_ferrata",
                 "services", "rest_area", "emergency_bay")
_EXCLUES = re.compile("^(" + "|".join(VOIES_EXCLUES) + ")$")

DEMI_COUPE_M = 0.5        # demi-longueur d'une coupe, de part et d'autre de la voie
RECUL_M = 2.0             # coupe d'un lien posée à cette distance du nœud barrière
CONTOURNABLE_M = 2.0      # barrière qui finit si près du chemin : on passe à côté
OUVERTURE_M = 3.0         # ouverture cartographiée assez proche (règle de gpx2elev)
OUVERTURE_LIGNE_M = 0.5   # ... et posée sur la barrière (règle de gpx2elev)
EPS_M = 0.05              # deux points plus proches sont confondus
M_PAR_DEGRE = 111195.08

PROBABLE = "Sentier balisé : passage probable, à vérifier"
NIVEAU = "Niveau de franchissement à confirmer"

# Genre d'une voie pour le calque des chemins OSM ; toute autre voie est une route.
GENRES = {"path": "sentier", "footway": "sentier", "bridleway": "sentier", "steps": "sentier",
          "pedestrian": "sentier", "cycleway": "sentier", "track": "piste"}

# Une tuile n'est lue qu'une fois à la fois : le calque et un calcul
# d'itinéraire qui la demandent ensemble n'interrogent pas Overpass deux fois.
_verrou_global = threading.Lock()
_verrous = {}


def _verrou(cle) -> threading.Lock:
    with _verrou_global:
        return _verrous.setdefault(cle, threading.Lock())


# overpass-api.de accorde deux requêtes simultanées par adresse et répond 429
# au-delà : calques et calcul d'itinéraire se partagent ces deux créneaux.
# Sans eux, chaque déplacement de la carte ajoutait ses requêtes à celles des
# vues précédentes (journal du 2026-10-19 : 429 en rafale, tuiles en 5 min).
CRENEAUX = 2
_creneaux = threading.BoundedSemaphore(CRENEAUX)
_sante_overpass = {"disponible": None, "verifiee": 0.0, "fil": None}
_verrou_sante = threading.Lock()


def _noter_overpass(disponible: bool) -> None:
    with _verrou_sante:
        _sante_overpass.update(disponible=disponible, verifiee=time.monotonic())


def disponibilite_overpass() -> bool | None:
    """Sonde courte en arrière-plan, sans faire attendre la page ni un calcul.

    Une requête de données réussie ou échouée met aussi cet état à jour.
    """
    with _verrou_sante:
        etat = _sante_overpass["disponible"]
        age = time.monotonic() - _sante_overpass["verifiee"]
        fil = _sante_overpass["fil"]
        if (etat is None or age > (60 if etat is False else 300)) and not (fil and fil.is_alive()):
            def sonder():
                try:
                    demande = urllib.request.Request(ENDPOINT.rsplit("/", 1)[0] + "/status",
                                                     headers={"User-Agent": f"hike2gpx/{__version__}"})
                    with urllib.request.urlopen(demande, timeout=6) as reponse:
                        reponse.read(128)
                    _noter_overpass(True)
                except OSError:
                    _noter_overpass(False)
            fil = threading.Thread(target=sonder, daemon=True, name="overpass-disponibilite")
            _sante_overpass["fil"] = fil
            fil.start()
        return etat


class ErreurDonnees(RuntimeError):
    """Les barrières d'une zone n'ont pas pu être vérifiées."""


class VueRemplacee(Exception):
    """La vue qui demandait ces données a laissé place à une autre : inutile
    de continuer à les lire."""


def _toujours() -> bool:
    return True


# ------------------------------------------------------------- géométrie

class Projection:
    """Plan local équirectangulaire en mètres, juste à l'échelle d'une zone."""

    def __init__(self, lat0: float, lon0: float):
        self.lat0, self.lon0 = lat0, lon0
        self.kx = M_PAR_DEGRE * math.cos(math.radians(lat0))

    def xy(self, lat: float, lon: float) -> tuple:
        return (lon - self.lon0) * self.kx, (lat - self.lat0) * M_PAR_DEGRE

    def geo(self, x: float, y: float) -> tuple:
        return self.lat0 + y / M_PAR_DEGRE, self.lon0 + x / self.kx


def _sous(a, b):
    return a[0] - b[0], a[1] - b[1]


def _vect(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _cote(p, a, b) -> int:
    """+1 ou -1 selon le côté de la droite ab où tombe p, 0 s'il est dessus."""
    longueur = _dist(a, b)
    if longueur == 0:
        return 0
    ecart = _vect(_sous(b, a), _sous(p, a)) / longueur
    return 0 if abs(ecart) <= EPS_M else (1 if ecart > 0 else -1)


def _intersection(a, b, c, d):
    """Paramètres (t, u) du point commun des segments ab et cd, ou None.
    Deux segments parallèles ne se coupent pas : une clôture qui longe un
    chemin ne le bloque pas."""
    r, s = _sous(b, a), _sous(d, c)
    lr, ls = math.hypot(*r), math.hypot(*s)
    den = _vect(r, s)
    if lr == 0 or ls == 0 or abs(den) <= 1e-9 * lr * ls:
        return None
    ca = _sous(c, a)
    t, u = _vect(ca, s) / den, _vect(ca, r) / den
    if -EPS_M / lr <= t <= 1 + EPS_M / lr and -EPS_M / ls <= u <= 1 + EPS_M / ls:
        return min(1.0, max(0.0, t)), min(1.0, max(0.0, u))
    return None


def _distance_segment(p, a, b) -> float:
    v = _sous(b, a)
    l2 = v[0] * v[0] + v[1] * v[1]
    t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * v[0] + (p[1] - a[1]) * v[1]) / l2))
    return math.hypot(p[0] - a[0] - t * v[0], p[1] - a[1] - t * v[1])


class _Grille:
    """Index spatial en cases de 50 m, comme la trace de gpx2elev."""
    PAS_M = 50.0

    def __init__(self):
        self.cases = defaultdict(list)

    def _plages(self, a, b, marge):
        pas = self.PAS_M
        return (range(math.floor((min(a[0], b[0]) - marge) / pas), math.floor((max(a[0], b[0]) + marge) / pas) + 1),
                range(math.floor((min(a[1], b[1]) - marge) / pas), math.floor((max(a[1], b[1]) + marge) / pas) + 1))

    def ajouter(self, cle, a, b):
        xs, ys = self._plages(a, b, 0.0)
        for x in xs:
            for y in ys:
                self.cases[x, y].append(cle)

    def candidats(self, a, b, marge=0.0):
        xs, ys = self._plages(a, b, marge)
        vus = set()
        for x in xs:
            for y in ys:
                for cle in self.cases.get((x, y), ()):
                    if cle not in vus:
                        vus.add(cle)
                        yield cle


# ------------------------------------------------------------- étiquettes

def _praticable(tags) -> bool:
    return "highway" in tags and not _EXCLUES.match(tags["highway"])


def _hors_sol(tags) -> bool:
    """Pont ou tunnel : la voie passe au-dessus ou au-dessous de la barrière."""
    return tags.get("bridge", "no") != "no" or tags.get("tunnel", "no") != "no" or tags.get("covered") == "yes"


def _niveau(tags) -> int:
    try:
        return int(float(tags.get("layer", "0")))
    except ValueError:
        return 0


def _est_ouverture(tags) -> bool:
    # Même critère que les « openings » de gpx2elev.
    return tags.get("entrance") != "no" and tags.get("barrier", "entrance" if "entrance" in tags else "") in regles.PASSAGES


def _coordonnees(element):
    lat, lon = element.get("lat"), element.get("lon")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)) and math.isfinite(lat) \
            and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180:
        return lat, lon
    return None


def _geometrie(element) -> list:
    """Points (lat, lon) d'une voie OSM, ou [] si la réponse est incomplète
    (géométrie absente, non alignée sur la liste des nœuds, coordonnées
    invalides)."""
    geom, noeuds = element.get("geometry") or [], element.get("nodes") or []
    if len(geom) < 2 or len(geom) != len(noeuds):
        return []
    points = []
    for p in geom:
        c = _coordonnees(p) if isinstance(p, dict) else None
        if c is None:
            return []
        points.append(c)
    return points


def _ferme(noeuds) -> bool:
    return len(noeuds) > 3 and noeuds[0] == noeuds[-1]


# ------------------------------------------------------------- analyse

def analyser(elements, mode: str = MODE) -> list:
    """Franchissements bloquants ou à vérifier d'un lot d'éléments Overpass
    (voies, barrières, nœuds étiquetés, relations de randonnée)."""
    noeuds = {e["id"]: e for e in elements if e.get("type") == "node" and _coordonnees(e)}
    lignes = [(e, pts) for e in elements if e.get("type") == "way" for pts in (_geometrie(e),) if pts]
    balises = {m.get("ref") for e in elements
               if e.get("type") == "relation" and e.get("tags", {}).get("route") in ("hiking", "foot")
               for m in e.get("members", ()) if m.get("type") == "way"}
    voies = [(e, pts) for e, pts in lignes if _praticable(e.get("tags", {}))]
    barrieres = [(e, pts) for e, pts in lignes
                 if "barrier" in e.get("tags", {}) and "highway" not in e.get("tags", {})]
    if not voies:
        return []

    lats = [p[0] for _, pts in voies for p in pts]
    lons = [p[1] for _, pts in voies for p in pts]
    proj = Projection((min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2)
    vxy = [[proj.xy(*p) for p in pts] for _, pts in voies]
    bxy = [[proj.xy(*p) for p in pts] for _, pts in barrieres]

    grille = _Grille()
    for vi, pts in enumerate(vxy):
        for si in range(len(pts) - 1):
            grille.ajouter((vi, si), pts[si], pts[si + 1])
    incidences = defaultdict(list)          # nœud -> [(voie, rang)]
    for vi, (v, _) in enumerate(voies):
        for k, nid in enumerate(v["nodes"]):
            incidences[nid].append((vi, k))
    positions_b = defaultdict(list)         # nœud -> [(barrière, rang)]
    for bi, (b, _) in enumerate(barrieres):
        nds = b["nodes"]
        for k, nid in enumerate(nds[:-1] if _ferme(nds) else nds):
            positions_b[nid].append((bi, k))
    usage = Counter(nid for b, _ in barrieres for nid in set(b["nodes"]))
    ouvertures, position_ouverture = _Grille(), {}
    for nid, n in noeuds.items():
        if _est_ouverture(n.get("tags", {})):
            position_ouverture[nid] = proj.xy(n["lat"], n["lon"])
            ouvertures.ajouter(nid, position_ouverture[nid], position_ouverture[nid])

    resultats = {}

    def voisins_barriere(nid):
        """Sommets voisins de nid le long des barrières qui le contiennent :
        une clôture découpée en plusieurs voies OSM reste une seule clôture."""
        for bi, k in positions_b.get(nid, ()):
            pts, nds = bxy[bi], barrieres[bi][0]["nodes"]
            dernier = len(pts) - 2 if _ferme(nds) else len(pts) - 1
            if k > 0:
                yield pts[k - 1]
            elif _ferme(nds):
                yield pts[dernier]
            if k < dernier:
                yield pts[k + 1]
            elif _ferme(nds):
                yield pts[0]

    def ouvertures_proches(p, c, d, nds_barriere) -> list:
        """Ouvertures cartographiées sur la barrière, assez près du croisement
        (règle de gpx2elev)."""
        return [nid for nid in ouvertures.candidats(p, p, OUVERTURE_M)
                if _dist(position_ouverture[nid], p) <= OUVERTURE_M
                and (nid in nds_barriere or _distance_segment(position_ouverture[nid], c, d) <= OUVERTURE_LIGNE_M)]

    def par_les_ouvertures(proches, voies_vues):
        """Jugement d'un croisement par ses ouvertures voisines : None si l'une
        laisse passer, ou si l'une est portée par la voie (l'étape 3 la juge) ;
        sinon (statut, raison, nœud) de la plus favorable. Une ouverture
        privée ou verrouillée n'efface plus la clôture (audit B01)."""
        meilleur = None
        for nid in proches:
            if any(nid in v["nodes"] for v in voies_vues):
                return None
            statut, raison = regles.status(noeuds[nid].get("tags", {}), mode, None, voies_vues[0].get("tags", {}))
            if statut == "passable":
                return None
            if meilleur is None or (statut == "uncertain" and meilleur[0] == "blocked"):
                meilleur = (statut, raison, nid)
        return meilleur

    def ajuster(jugement, voies_vues, tags_barriere):
        statut, raison = jugement
        if any(_niveau(v.get("tags", {})) != _niveau(tags_barriere) for v in voies_vues):
            statut, raison = "uncertain", NIVEAU
        if statut == "blocked" and any(v["id"] in balises for v in voies_vues):
            statut, raison = "uncertain", PROBABLE
        return statut, raison

    def coupe(centre, direction):
        longueur = math.hypot(*direction)
        nx, ny = -direction[1] / longueur, direction[0] / longueur
        extremites = ((centre[0] + nx * DEMI_COUPE_M, centre[1] + ny * DEMI_COUPE_M),
                      (centre[0] - nx * DEMI_COUPE_M, centre[1] - ny * DEMI_COUPE_M))
        return [[round(lon, 7), round(lat, 7)] for lat, lon in (proj.geo(*q) for q in extremites)]

    def voisin(vi, k, pas):
        """Rang du premier sommet de la voie vi distinct du sommet k, vers
        l'avant (pas = 1) ou l'arrière (-1), ou None : un nœud répété, ou deux
        nœuds au même endroit, ne font pas un lien (audit B08)."""
        pts, kk = vxy[vi], k + pas
        while 0 <= kk < len(pts):
            if _dist(pts[kk], pts[k]) > EPS_M:
                return kk
            kk += pas
        return None

    def coupe_lien(p, q):
        """Coupe d'un lien de voie qui part du nœud p vers q."""
        v = _sous(q, p)
        longueur = math.hypot(*v)
        recul = min(RECUL_M, 0.45 * longueur)
        return coupe((p[0] + v[0] / longueur * recul, p[1] + v[1] / longueur * recul), v)

    def enregistrer(cle, statut, raison, tags_barriere, osm, p, voies_vues, coupes):
        if not coupes:
            return
        ancien = resultats.get(cle)
        if ancien is not None and not (statut == "blocked" and ancien["statut"] != "blocked"):
            return
        lat, lon = proj.geo(*p)
        nature = tags_barriere.get("barrier", "entrance")
        resultats[cle] = {"cle": "-".join(str(x) for x in cle), "statut": statut, "raison": raison,
                          "nature": regles.LABELS.get(nature, "Barrière"), "barriere": nature,
                          "lat": round(lat, 7), "lon": round(lon, 7), "osm": osm,
                          "voies": sorted({v["id"] for v in voies_vues}), "coupes": coupes}

    # 1. Barrières dessinées en ligne, croisées par une voie.
    sommets = defaultdict(dict)             # sommet de voie posé sur une barrière -> {barrière: segment}
    for bi, (b, _) in enumerate(barrieres):
        tags_b = b.get("tags", {})
        jugement = regles.status(tags_b, mode)
        if jugement[0] == "passable":
            continue
        pts, nds = bxy[bi], b["nodes"]
        nds_set = set(nds)
        cumul = [0.0]
        for c, d in zip(pts, pts[1:]):
            cumul.append(cumul[-1] + _dist(c, d))
        debut_libre = not _ferme(nds) and usage[nds[0]] == 1
        fin_libre = not _ferme(nds) and usage[nds[-1]] == 1
        for bj in range(len(pts) - 1):
            c, d = pts[bj], pts[bj + 1]
            lb = _dist(c, d)
            if lb == 0:
                continue
            for vi, si in grille.candidats(c, d):
                v = voies[vi][0]
                a, e = vxy[vi][si], vxy[vi][si + 1]
                inter = _intersection(a, e, c, d)
                if inter is None or _hors_sol(v.get("tags", {})):
                    continue
                t, u = inter
                abscisse = cumul[bj] + u * lb
                if (debut_libre and abscisse <= CONTOURNABLE_M) or (fin_libre and cumul[-1] - abscisse <= CONTOURNABLE_M):
                    continue
                lv = _dist(a, e)
                if t * lv <= EPS_M or (1 - t) * lv <= EPS_M:
                    # Un sommet de la voie posé sur la barrière : un carrefour
                    # possible, jugé avec tous ses liens plus bas.
                    sommets[v["nodes"][si if t * lv <= EPS_M else si + 1]].setdefault(bi, bj)
                    continue
                cle_sommet = None
                if u * lb <= EPS_M or (1 - u) * lb <= EPS_M:
                    # Un sommet de la barrière posé sur la voie : elle ne la
                    # traverse que si elle repart de l'autre côté.
                    nb = nds[bj if u * lb <= EPS_M else bj + 1]
                    if {_cote(q, a, e) for q in voisins_barriere(nb)} - {0} != {1, -1}:
                        continue
                    cle_sommet = nb
                p = (a[0] + t * (e[0] - a[0]), a[1] + t * (e[1] - a[1]))
                proches = ouvertures_proches(p, c, d, nds_set)
                if proches:
                    # L'ouverture voisine décide à la place de la barrière.
                    ouverture = par_les_ouvertures(proches, [v])
                    if ouverture is not None:
                        statut_o, raison_o, no = ouverture
                        tags_o = noeuds[no].get("tags", {})
                        statut, raison = ajuster((statut_o, raison_o), [v], tags_o)
                        enregistrer(("ouverture", no, v["id"]), statut, raison, tags_o, f"node/{no}", p, [v],
                                    [coupe(p, _sous(e, a))])
                    continue
                statut, raison = ajuster(jugement, [v], tags_b)
                # Un sommet de barrière partagé par deux morceaux de la même
                # clôture ne compte qu'une fois.
                cle = ("pli", cle_sommet, v["id"]) if cle_sommet is not None \
                    else ("ligne", b["id"], v["id"], round(p[0] * 2), round(p[1] * 2))
                enregistrer(cle, statut, raison, tags_b, f"way/{b['id']}", p, [v], [coupe(p, _sous(e, a))])

    # 2. Sommets de voie posés sur une barrière (nœud commun non étiqueté,
    #    carrefour, voie qui s'arrête sur la clôture et qu'une autre prolonge).
    for nid, occurrences in sommets.items():
        tags_n = noeuds.get(nid, {}).get("tags", {})
        if "barrier" in tags_n or "entrance" in tags_n:
            continue    # nœud étiqueté : jugé à l'étape 3, comme dans gpx2elev
        liens = [(vi, k, kk) for vi, k in incidences.get(nid, ())
                 if not _hors_sol(voies[vi][0].get("tags", {}))
                 for kk in (voisin(vi, k, -1), voisin(vi, k, 1)) if kk is not None]
        if not liens:
            continue
        p = vxy[liens[0][0]][liens[0][1]]
        for bi, bj in occurrences.items():
            b = barrieres[bi][0]
            tags_b = b.get("tags", {})
            c, d = bxy[bi][bj], bxy[bi][bj + 1]
            gauche = [l for l in liens if _cote(vxy[l[0]][l[2]], c, d) > 0]
            droite = [l for l in liens if _cote(vxy[l[0]][l[2]], c, d) < 0]
            if not gauche or not droite:
                continue
            voies_vues = [voies[vi][0] for vi, _, _ in liens]
            proches = ouvertures_proches(p, c, d, set(b["nodes"]))
            if proches:
                ouverture = par_les_ouvertures(proches, voies_vues)
                if ouverture is None:
                    continue
                statut_o, raison_o, no = ouverture
                tags_j, osm = noeuds[no].get("tags", {}), f"node/{no}"
                statut, raison = ajuster((statut_o, raison_o), voies_vues, tags_j)
            else:
                tags_j, osm = tags_b, f"way/{b['id']}"
                statut, raison = ajuster(regles.status(tags_b, mode), voies_vues, tags_b)
            coupees = gauche if len(gauche) <= len(droite) else droite
            enregistrer(("sommet", nid), statut, raison, tags_j, osm, p, voies_vues,
                        [coupe_lien(vxy[vi][k], vxy[vi][kk]) for vi, k, kk in coupees])

    # 3. Nœuds étiquetés (portail, borne, clôture notée sur le nœud...) posés
    #    sur une voie : jugés avec chaque voie qui les porte, comme dans gpx2elev.
    for nid, n in noeuds.items():
        tags_n = n.get("tags", {})
        if ("barrier" not in tags_n and "entrance" not in tags_n) or nid not in incidences:
            continue
        jugements, coupes, voies_vues = [], [], []
        for vi, k in incidences[nid]:
            v = voies[vi][0]
            statut, raison = regles.status(tags_n, mode, None, v.get("tags", {}))
            if statut == "blocked" and v["id"] in balises:
                statut, raison = "uncertain", PROBABLE
            if statut == "passable":
                continue
            jugements.append((statut, raison))
            voies_vues.append(v)
            coupes.extend(coupe_lien(vxy[vi][k], vxy[vi][kk]) for kk in (voisin(vi, k, -1), voisin(vi, k, 1))
                          if kk is not None)
        if jugements:
            statut, raison = next((j for j in jugements if j[0] == "blocked"), jugements[0])
            enregistrer(("noeud", nid), statut, raison, tags_n, f"node/{nid}",
                        proj.xy(n["lat"], n["lon"]), voies_vues, coupes)

    return sorted(resultats.values(), key=lambda f: (f["statut"] != "blocked", f["lat"], f["lon"]))


# ------------------------------------------------------------- données

def _rang(valeur: float) -> int:
    # 43.30 / 0.05 vaut 865.999… en virgule flottante : sans cette marge, une
    # borne de tuile tomberait dans la tuile d'avant.
    return math.floor(valeur / TUILE_DEG + 1e-9)


def tuiles_zone(sud: float, ouest: float, nord: float, est: float) -> list:
    return [(i, j) for i in range(_rang(sud), _rang(nord) + 1) for j in range(_rang(ouest), _rang(est) + 1)]


def tuile_du_point(lat: float, lon: float) -> tuple:
    return _rang(lat), _rang(lon)


def bornes_tuile(i: int, j: int) -> tuple:
    return (round(i * TUILE_DEG, 6), round(j * TUILE_DEG, 6),
            round((i + 1) * TUILE_DEG, 6), round((j + 1) * TUILE_DEG, 6))


def bornes_zone(sud: float, ouest: float, nord: float, est: float) -> tuple:
    """(sud, ouest, nord, est) des tuiles qui couvrent la zone : ce qu'un
    calque lit vraiment, et que la page n'a pas à redemander."""
    return bornes_tuile(_rang(sud), _rang(ouest))[:2] + bornes_tuile(_rang(nord), _rang(est))[2:]


def requete(sud: float, ouest: float, nord: float, est: float) -> str:
    bbox = f"{sud:.6f},{ouest:.6f},{nord:.6f},{est:.6f}"
    return ('[out:json][timeout:180];'
            f'way["highway"]["highway"!~"{_EXCLUES.pattern}"]({bbox})->.voies;'
            f'way["barrier"]({bbox})->.lignes;'
            '(.voies;.lignes;node(w.voies)["barrier"];node(w.voies)["entrance"];'
            'node(w.lignes)["barrier"];node(w.lignes)["entrance"];);out body geom;'
            'rel(bw.voies)["route"~"^(hiking|foot)$"];out body;')


def _prendre_creneau(continuer) -> None:
    """Attend l'un des CRENEAUX Overpass ; une vue quittée renonce à attendre."""
    while not _creneaux.acquire(timeout=1.0):
        if not continuer():
            raise VueRemplacee()
    if not continuer():
        _creneaux.release()
        raise VueRemplacee()


def interroger(texte: str, delai_s: float = 200.0, attendre=time.sleep, continuer=_toujours) -> list:
    """Éléments d'une requête Overpass, posée dans l'un des CRENEAUX. Les refus
    passagers (file d'attente pleine, délai dépassé) sont retentés, puis
    l'échec remonte. Quand continuer() devient faux (la vue a changé, un
    extrait couvre la tuile), ni l'attente d'un créneau, ni la fin d'une
    pause, ni un nouvel essai n'ont lieu."""
    corps = urllib.parse.urlencode({"data": texte}).encode("utf-8")
    derniere = None
    for essai in range(TENTATIVES):
        if essai:
            for _ in range(15 * essai):         # une seconde à la fois
                if not continuer():
                    break
                attendre(1)
        demande = urllib.request.Request(ENDPOINT, data=corps,
                                         headers={"User-Agent": f"hike2gpx/{__version__}"})
        _prendre_creneau(continuer)
        try:
            with urllib.request.urlopen(demande, timeout=delai_s) as reponse:
                brut = reponse.read(MAX_OCTETS + 1)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 502, 503, 504):
                raise ErreurDonnees(f"Overpass refuse la requête (HTTP {exc.code}).") from exc
            journal.warning("Overpass, essai %d sur %d : HTTP %s", essai + 1, TENTATIVES, exc.code)
            derniere = exc
            continue
        except OSError as exc:      # URLError, délai, connexion coupée
            journal.warning("Overpass, essai %d sur %d : %s", essai + 1, TENTATIVES, exc)
            derniere = exc
            continue
        finally:
            _creneaux.release()
        if len(brut) > MAX_OCTETS:
            raise ErreurDonnees("Réponse Overpass trop volumineuse : barrières non vérifiées.")
        try:
            donnees = json.loads(brut)
        except ValueError as exc:
            derniere = exc
            continue
        if donnees.get("remark") or not isinstance(donnees.get("elements"), list):
            derniere = ErreurDonnees(str(donnees.get("remark") or "réponse incomplète"))
            continue
        _noter_overpass(True)
        return donnees["elements"]
    _noter_overpass(False)
    raise ErreurDonnees(f"Overpass ne répond pas : barrières non vérifiées ({derniere}).") from derniere


def tuile_de_l_extrait(i: int, j: int, dossier) -> dict | None:
    """La tuile lue dans l'extrait Geofabrik installé qui la contient tout
    entière (geofabrik.py), au format du cache Overpass, ou None. Un extrait
    trop vieux lance son renouvellement en tâche de fond et sert en attendant."""
    from . import geofabrik     # pas de cycle : geofabrik importe ce module
    try:
        extrait = geofabrik.extrait_de_tuile(dossier, i, j)
        if extrait is None:
            return None
        geofabrik.telechargements(dossier).renouveler_si_perime(extrait)
        return {"version": VERSION_DONNEES, "fetched_at": geofabrik.horodatage(extrait),
                "bornes": bornes_tuile(i, j), "elements": geofabrik.elements_tuile(extrait, i, j),
                "source": f"geofabrik:{extrait['id']}:{extrait['date']}"}
    except (OSError, ValueError, sqlite3.Error) as exc:
        journal.warning("Extrait OSM illisible pour la tuile %d_%d, Overpass à la place : %s", i, j, exc)
        return None


def _couverte(i: int, j: int, dossier) -> bool:
    """Un extrait installé contient-il toute la tuile ? Assez léger pour être
    redemandé à chaque seconde d'attente d'Overpass."""
    from . import geofabrik     # pas de cycle : geofabrik importe ce module
    try:
        return geofabrik.extrait_de_tuile(dossier, i, j) is not None
    except (OSError, ValueError):
        return False


@lru_cache(maxsize=512)
def _date_cache_valide(chemin: Path, modification: int, taille: int) -> float | None:
    """Valide le cache une seule fois tant que son fichier ne change pas."""
    cache = atomique.lire_json(chemin, None)
    if isinstance(cache, dict) and isinstance(cache.get("elements"), list) \
            and isinstance(cache.get("fetched_at"), (int, float)):
        return cache["fetched_at"]
    return None


def tuile_disponible(i: int, j: int, dossier, maintenant=time.time) -> bool:
    """Une tuile peut fournir ses franchissements sans nouvel appel Overpass."""
    from . import geofabrik
    if geofabrik.extrait_de_tuile(dossier, i, j) is not None:
        return True
    chemin = Path(dossier) / "overpass" / f"v{VERSION_DONNEES}_{i}_{j}.json"
    try:
        info = chemin.stat()
    except OSError:
        return False
    date = _date_cache_valide(chemin, info.st_mtime_ns, info.st_size)
    return date is not None and maintenant() - date < TTL_S


def charger_tuile(i: int, j: int, dossier, *, en_ligne: bool = True, interroger=interroger,
                  maintenant=time.time, continuer=_toujours) -> dict:
    """Les données OSM d'une tuile : celles de l'extrait Geofabrik installé qui
    la contient, sinon celles d'Overpass (cache de sept jours)."""
    extrait = tuile_de_l_extrait(i, j, dossier)
    if extrait is not None:
        return extrait
    chemin = Path(dossier) / "overpass" / f"v{VERSION_DONNEES}_{i}_{j}.json"
    with _verrou(("overpass", i, j)):
        cache = atomique.lire_json(chemin, None)
        valide = isinstance(cache, dict) and isinstance(cache.get("elements"), list) \
            and isinstance(cache.get("fetched_at"), (int, float))
        if valide and (not en_ligne or maintenant() - cache["fetched_at"] < TTL_S):
            return cache
        if not en_ligne:
            raise ErreurDonnees("Hors connexion : les barrières de cette zone n'ont jamais été chargées.")
        debut, instant, texte = time.monotonic(), maintenant(), requete(*bornes_tuile(i, j))
        # Un extrait installé pendant l'attente d'Overpass prend aussitôt le
        # relais (essai réel du 2026-10-20 : le Var installé au bout de 39 s,
        # la tuile suivante attendait encore Overpass, en HTTP 502, jusqu'à 80 s).
        try:
            elements = interroger(texte, continuer=lambda: continuer() and not _couverte(i, j, dossier))
        except VueRemplacee:
            if not continuer():
                raise
            extrait = tuile_de_l_extrait(i, j, dossier)
            if extrait is not None:
                journal.info("Tuile %d_%d : l'extrait arrivé pendant l'attente d'Overpass prend le relais", i, j)
                return extrait
            elements = interroger(texte, continuer=continuer)      # extrait illisible : Overpass, comme avant
        donnees = {"version": VERSION_DONNEES, "fetched_at": instant, "bornes": bornes_tuile(i, j),
                   "elements": elements}
        journal.info("Overpass : tuile %d_%d lue en %.1f s (%d éléments)", i, j, time.monotonic() - debut,
                     len(donnees["elements"]))
        atomique.ecrire_json(chemin, donnees, indent=None)
        return donnees


def franchissements_tuile(i: int, j: int, dossier, *, donnees=None, **options) -> list:
    """Franchissements situés dans une tuile. Overpass y renvoie entières
    toutes les voies et barrières qui la touchent : chaque franchissement de
    la tuile y est donc vu, ceux d'à côté sont écartés ici."""
    donnees = donnees if donnees is not None else charger_tuile(i, j, dossier, **options)
    chemin = Path(dossier) / "franchissements" / f"v{VERSION_ANALYSE}_{i}_{j}.json"
    cache = atomique.lire_json(chemin, None)
    if isinstance(cache, dict) and cache.get("fetched_at") == donnees["fetched_at"] \
            and isinstance(cache.get("franchissements"), list):
        return cache["franchissements"]
    sud, ouest, nord, est = bornes_tuile(i, j)
    liste = [f for f in analyser(donnees["elements"])
             if sud <= f["lat"] < nord and ouest <= f["lon"] < est]
    atomique.ecrire_json(chemin, {"version": VERSION_ANALYSE, "fetched_at": donnees["fetched_at"],
                                  "franchissements": liste}, indent=None)
    return liste


def franchissements_zone(sud: float, ouest: float, nord: float, est: float, dossier, *, suivi=None,
                         **options) -> list:
    """Franchissements des tuiles de la zone ; suivi(faites, total) après
    chaque tuile, pour la barre de progression de la page."""
    resultat, tuiles = [], tuiles_zone(sud, ouest, nord, est)
    if suivi:
        suivi(0, len(tuiles))
    for k, (i, j) in enumerate(tuiles):
        resultat.extend(franchissements_tuile(i, j, dossier, **options))
        if suivi:
            suivi(k + 1, len(tuiles))
    return resultat


def _couvertes_d_abord(tuiles: list, dossier) -> list:
    """Les tuiles qu'un extrait installé contient d'abord, dans leur ordre :
    elles se lisent en un instant, et la barre de la page avance avant
    d'attendre Overpass pour celles qu'aucun extrait ne contient tout
    entières (au bord d'une région)."""
    from . import geofabrik     # pas de cycle : geofabrik importe ce module
    try:
        extraits = geofabrik.installes(dossier)
    except OSError:
        return tuiles
    return sorted(tuiles, key=lambda tuile: geofabrik.region_de_tuile(extraits, *tuile) is None)


def voies_affichables(sud: float, ouest: float, nord: float, est: float, dossier, **options) -> dict:
    """Voies praticables (sentier, piste ou route) et barrières qui gênent un
    piéton, telles que les tuiles Overpass les connaissent, pour le calque des
    chemins OSM. Une bordure de trottoir n'y figure pas : elle se franchit.
    suivi(faites, total), tuile après tuile, pour la barre de la page."""
    voies, barrieres, franchissements = {}, {}, []
    continuer = options.get("continuer", _toujours)
    suivi = options.pop("suivi", None)
    tuiles = _couvertes_d_abord(tuiles_zone(sud, ouest, nord, est), dossier)
    if suivi:
        suivi(0, len(tuiles))
    for k, (i, j) in enumerate(tuiles):
        if not continuer():
            raise VueRemplacee()
        donnees = charger_tuile(i, j, dossier, **options)
        for e in donnees["elements"]:
            points = _geometrie(e) if e.get("type") == "way" else []
            if not points:
                continue
            tags = e.get("tags", {})
            ligne = [[round(lat, 6), round(lon, 6)] for lat, lon in points]
            if _praticable(tags):
                voies[e["id"]] = {"id": e["id"], "genre": GENRES.get(tags["highway"], "route"), "pts": ligne}
            elif "barrier" in tags and "highway" not in tags and regles.status(tags, MODE)[0] != "passable":
                barrieres[e["id"]] = {"id": e["id"], "nature": regles.LABELS.get(tags["barrier"], "Barrière"),
                                      "pts": ligne}
        franchissements.extend({cle: f[cle] for cle in ("cle", "statut", "raison", "nature", "lat", "lon", "osm")}
                               for f in franchissements_tuile(i, j, dossier, donnees=donnees)
                               if f["statut"] in ("blocked", "uncertain"))
        if suivi:
            suivi(k + 1, len(tuiles))
    return {"voies": list(voies.values()), "barrieres": list(barrieres.values()),
            "franchissements": franchissements}
