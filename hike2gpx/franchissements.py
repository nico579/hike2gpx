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
import math
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

from nico579_commons import atomique

from . import __version__, regles

ENDPOINT = "https://overpass-api.de/api/interpreter"
MODE = "foot"
TUILE_DEG = 0.05
TTL_S = 7 * 86400
# Format du cache Overpass, et version des règles : augmenter la seconde dès
# qu'un jugement change, l'analyse en cache est alors refaite.
VERSION_DONNEES = 1
VERSION_ANALYSE = 1
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


class ErreurDonnees(RuntimeError):
    """Les barrières d'une zone n'ont pas pu être vérifiées."""


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

    def ouverture_proche(p, c, d, nds_barriere) -> bool:
        for nid in ouvertures.candidats(p, p, OUVERTURE_M):
            q = position_ouverture[nid]
            if _dist(q, p) <= OUVERTURE_M and (nid in nds_barriere or _distance_segment(q, c, d) <= OUVERTURE_LIGNE_M):
                return True
        return False

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
                if ouverture_proche(p, c, d, nds_set):
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
                 for kk in (k - 1, k + 1) if 0 <= kk < len(vxy[vi])]
        if not liens:
            continue
        p = vxy[liens[0][0]][liens[0][1]]
        for bi, bj in occurrences.items():
            b = barrieres[bi][0]
            tags_b = b.get("tags", {})
            c, d = bxy[bi][bj], bxy[bi][bj + 1]
            gauche = [l for l in liens if _cote(vxy[l[0]][l[2]], c, d) > 0]
            droite = [l for l in liens if _cote(vxy[l[0]][l[2]], c, d) < 0]
            if not gauche or not droite or ouverture_proche(p, c, d, set(b["nodes"])):
                continue
            voies_vues = [voies[vi][0] for vi, _, _ in liens]
            statut, raison = ajuster(regles.status(tags_b, mode), voies_vues, tags_b)
            coupees = gauche if len(gauche) <= len(droite) else droite
            enregistrer(("sommet", nid), statut, raison, tags_b, f"way/{b['id']}", p, voies_vues,
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
            coupes.extend(coupe_lien(vxy[vi][k], vxy[vi][kk]) for kk in (k - 1, k + 1) if 0 <= kk < len(vxy[vi]))
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


def requete(sud: float, ouest: float, nord: float, est: float) -> str:
    bbox = f"{sud:.6f},{ouest:.6f},{nord:.6f},{est:.6f}"
    return ('[out:json][timeout:180];'
            f'way["highway"]["highway"!~"{_EXCLUES.pattern}"]({bbox})->.voies;'
            f'way["barrier"]({bbox})->.lignes;'
            '(.voies;.lignes;node(w.voies)["barrier"];node(w.voies)["entrance"];'
            'node(w.lignes)["barrier"];node(w.lignes)["entrance"];);out body geom;'
            'rel(bw.voies)["route"~"^(hiking|foot)$"];out body;')


def interroger(texte: str, delai_s: float = 200.0, attendre=time.sleep) -> list:
    """Éléments d'une requête Overpass. Les refus passagers (file d'attente
    pleine, délai dépassé) sont retentés, puis l'échec remonte."""
    corps = urllib.parse.urlencode({"data": texte}).encode("utf-8")
    derniere = None
    for essai in range(TENTATIVES):
        if essai:
            attendre(15 * essai)
        demande = urllib.request.Request(ENDPOINT, data=corps,
                                         headers={"User-Agent": f"hike2gpx/{__version__}"})
        try:
            with urllib.request.urlopen(demande, timeout=delai_s) as reponse:
                brut = reponse.read(MAX_OCTETS + 1)
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 502, 503, 504):
                raise ErreurDonnees(f"Overpass refuse la requête (HTTP {exc.code}).") from exc
            derniere = exc
            continue
        except OSError as exc:      # URLError, délai, connexion coupée
            derniere = exc
            continue
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
        return donnees["elements"]
    raise ErreurDonnees(f"Overpass ne répond pas : barrières non vérifiées ({derniere}).") from derniere


def charger_tuile(i: int, j: int, dossier, *, en_ligne: bool = True, interroger=interroger,
                  maintenant=time.time) -> dict:
    chemin = Path(dossier) / "overpass" / f"v{VERSION_DONNEES}_{i}_{j}.json"
    with _verrou(("overpass", i, j)):
        cache = atomique.lire_json(chemin, None)
        valide = isinstance(cache, dict) and isinstance(cache.get("elements"), list) \
            and isinstance(cache.get("fetched_at"), (int, float))
        if valide and (not en_ligne or maintenant() - cache["fetched_at"] < TTL_S):
            return cache
        if not en_ligne:
            raise ErreurDonnees("Hors connexion : les barrières de cette zone n'ont jamais été chargées.")
        donnees = {"version": VERSION_DONNEES, "fetched_at": maintenant(), "bornes": bornes_tuile(i, j),
                   "elements": interroger(requete(*bornes_tuile(i, j)))}
        atomique.ecrire_json(chemin, donnees, indent=None)
        return donnees


def franchissements_tuile(i: int, j: int, dossier, **options) -> list:
    """Franchissements situés dans une tuile. Overpass y renvoie entières
    toutes les voies et barrières qui la touchent : chaque franchissement de
    la tuile y est donc vu, ceux d'à côté sont écartés ici."""
    donnees = charger_tuile(i, j, dossier, **options)
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


def franchissements_zone(sud: float, ouest: float, nord: float, est: float, dossier, **options) -> list:
    resultat = []
    for i, j in tuiles_zone(sud, ouest, nord, est):
        resultat.extend(franchissements_tuile(i, j, dossier, **options))
    return resultat


def voies_affichables(sud: float, ouest: float, nord: float, est: float, dossier, **options) -> dict:
    """Voies praticables (sentier, piste ou route) et barrières qui gênent un
    piéton, telles que les tuiles Overpass les connaissent, pour le calque des
    chemins OSM. Une bordure de trottoir n'y figure pas : elle se franchit."""
    voies, barrieres = {}, {}
    for i, j in tuiles_zone(sud, ouest, nord, est):
        for e in charger_tuile(i, j, dossier, **options)["elements"]:
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
    return {"voies": list(voies.values()), "barrieres": list(barrieres.values())}
