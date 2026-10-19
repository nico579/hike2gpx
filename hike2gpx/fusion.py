"""Réseau fusionné : les voies OSM des tuiles Overpass déjà lues, plus les
tronçons de la BD TOPO qui y manquent, pour fabriquer les tuiles BRouter de
hike2gpx.

Un tronçon IGN est gardé quand moins de la moitié de sa longueur passe à
moins de 12 m d'une voie OSM : sinon OSM le connaît déjà, et OSM reste juge
des accès. Ses bouts sont raccordés aux autres tronçons gardés qui partagent
le même point, et à la voie OSM la plus proche quand elle passe à moins de
15 m (par un nœud inséré dans la voie, ou par un sommet existant à moins
d'un mètre). Il porte hike2gpx=ign : le profil le rend plus coûteux et la
page le signale « non vérifié ». Un accès piéton autre que libre ou payant
devient foot=private, que le profil interdit comme sur OSM.

Les franchissements se calculent ensuite sur le réseau entier (elements) :
un raccord crée des carrefours que ni OSM seul ni les chemins IGN seuls ne
montrent, par exemple deux bouts arrêtés de part et d'autre d'une clôture.

Les identifiants ajoutés suivent ceux de l'extrait : le créateur de tuiles
de BRouter réserve sa mémoire jusqu'au plus grand identifiant.
"""
from __future__ import annotations

import math
from collections import defaultdict

from . import franchissements as fr

NATURES_EXCLUES = {"Type autoroutier", "Quasi-autoroute", "Bretelle", "Route à 2 chaussées",
                   "Bac ou liaison maritime", "Bac auto", "Bac piéton"}
COUVERT_M = 12.0
PART_COUVERTE_MAX = 0.5
RELIE_M = 15.0
PAS_M = 10.0
ETIQUETTE = {"highway": "path", "hike2gpx": "ign"}
# Valeurs de l'accès piéton qui n'empêchent pas de passer ; toute autre,
# connue ou non (« Restreint aux ayants droit »…), vaut interdiction.
ACCES_OUVERTS = {None, "", "Libre", "A péage"}
_CASE_DEG = 0.002


def _xy(lat, lon, lat0, lon0):
    """Plan local en mètres autour de (lat0, lon0)."""
    return ((lon - lon0) * fr.M_PAR_DEGRE * math.cos(math.radians(lat0)), (lat - lat0) * fr.M_PAR_DEGRE)


class IndexVoies:
    """Segments des voies OSM praticables, rangés par cases de 0,002° ; les
    distances se mesurent dans un plan local autour du point cherché."""

    def __init__(self):
        self.cases = defaultdict(list)

    def ajouter(self, wid, k, a, b):
        for x in range(math.floor(min(a[0], b[0]) / _CASE_DEG), math.floor(max(a[0], b[0]) / _CASE_DEG) + 1):
            for y in range(math.floor(min(a[1], b[1]) / _CASE_DEG), math.floor(max(a[1], b[1]) / _CASE_DEG) + 1):
                self.cases[x, y].append((wid, k, a, b))

    def plus_proche(self, lat, lon, rayon_m):
        """(distance, voie, rang du segment) de la voie la plus proche dans le
        rayon, ou None."""
        dlat = rayon_m / fr.M_PAR_DEGRE
        dlon = dlat / max(0.2, math.cos(math.radians(lat)))
        meilleur = None
        vus = set()
        for x in range(math.floor((lat - dlat) / _CASE_DEG), math.floor((lat + dlat) / _CASE_DEG) + 1):
            for y in range(math.floor((lon - dlon) / _CASE_DEG), math.floor((lon + dlon) / _CASE_DEG) + 1):
                for wid, k, a, b in self.cases.get((x, y), ()):
                    if (wid, k) in vus:
                        continue
                    vus.add((wid, k))
                    d = fr._distance_segment((0.0, 0.0), _xy(*a, lat, lon), _xy(*b, lat, lon))
                    if d <= rayon_m and (meilleur is None or d < meilleur[0]):
                        meilleur = (d, wid, k)
        return meilleur


class Reseau:
    def __init__(self):
        self.noeuds = {}        # id -> [lat, lon, tags]
        self.voies = {}         # id -> [ids de nœuds, tags]
        self.relations = {}     # id -> [membres, tags]
        self.ign = []           # voies ajoutées depuis la BD TOPO
        self._prochain_noeud = self._prochaine_voie = None

    # ------------------------------------------------------------ OSM

    def ajouter_osm(self, elements) -> None:
        for e in elements:
            if e.get("type") == "node" and fr._coordonnees(e):
                self.noeuds[e["id"]] = [e["lat"], e["lon"], dict(e.get("tags", {}))]
            elif e.get("type") == "way" and fr._geometrie(e) and e["id"] not in self.voies:
                for nid, p in zip(e["nodes"], e["geometry"]):
                    self.noeuds.setdefault(nid, [p["lat"], p["lon"], {}])
                self.voies[e["id"]] = [list(e["nodes"]), dict(e.get("tags", {}))]
            elif e.get("type") == "relation":
                self.relations[e["id"]] = [list(e.get("members", [])), dict(e.get("tags", {}))]

    def index(self) -> IndexVoies:
        index = IndexVoies()
        for wid, (ids, tags) in self.voies.items():
            if fr._praticable(tags) and not fr._hors_sol(tags):
                for k in range(len(ids) - 1):
                    index.ajouter(wid, k, self.noeuds[ids[k]][:2], self.noeuds[ids[k + 1]][:2])
        return index

    # ------------------------------------------------------------ IGN

    def _nouveau_noeud(self, lat, lon) -> int:
        if self._prochain_noeud is None:
            self._prochain_noeud = max(self.noeuds, default=0) + 1
        nid, self._prochain_noeud = self._prochain_noeud, self._prochain_noeud + 1
        self.noeuds[nid] = [lat, lon, {}]
        return nid

    def _nouvelle_voie(self) -> int:
        if self._prochaine_voie is None:
            self._prochaine_voie = max(self.voies, default=0) + 1
        wid, self._prochaine_voie = self._prochaine_voie, self._prochaine_voie + 1
        return wid

    def _raccorder_osm(self, nid, index) -> bool:
        """Relie le nœud nid à la voie OSM la plus proche (moins de RELIE_M)."""
        lat, lon = self.noeuds[nid][:2]
        trouve = index.plus_proche(lat, lon, RELIE_M)
        if trouve is None:
            return False
        _, wid, _ = trouve
        ids = self.voies[wid][0]
        # Le rang a pu bouger (insertions précédentes) : on recherche le segment.
        meilleur = None
        for k in range(len(ids) - 1):
            a, b = _xy(*self.noeuds[ids[k]][:2], lat, lon), _xy(*self.noeuds[ids[k + 1]][:2], lat, lon)
            d = fr._distance_segment((0.0, 0.0), a, b)
            if meilleur is None or d < meilleur[0]:
                meilleur = (d, k, a, b)
        _, k, a, b = meilleur
        v = (b[0] - a[0], b[1] - a[1])
        t = max(0.0, min(1.0, -(a[0] * v[0] + a[1] * v[1]) / (v[0] ** 2 + v[1] ** 2 or 1)))
        q = (a[0] + t * v[0], a[1] + t * v[1])
        if math.hypot(*_sous(q, a)) < 1:
            cible = ids[k]
        elif math.hypot(*_sous(q, b)) < 1:
            cible = ids[k + 1]
        else:
            cible = self._nouveau_noeud(lat + q[1] / fr.M_PAR_DEGRE,
                                        lon + q[0] / (fr.M_PAR_DEGRE * math.cos(math.radians(lat))))
            ids.insert(k + 1, cible)
        self._liens.append((nid, cible))
        return True

    def ajouter_ign(self, troncons) -> int:
        """Ajoute les tronçons IGN absents d'OSM ; rend leur nombre."""
        index = self.index()
        self._liens = []
        bouts = {}                  # point (arrondi au 1e-7) -> nœud commun des tronçons IGN
        ajoutes = 0
        for t in troncons:
            if t.get("nature") in NATURES_EXCLUES or len(t.get("pts") or []) < 2:
                continue
            if _part_couverte(t["pts"], index) >= PART_COUVERTE_MAX:
                continue
            ids = []
            for k, (lat, lon) in enumerate(t["pts"]):
                if k in (0, len(t["pts"]) - 1):
                    cle = (round(lat, 7), round(lon, 7))
                    if cle not in bouts:
                        bouts[cle] = self._nouveau_noeud(lat, lon)
                    ids.append(bouts[cle])
                else:
                    ids.append(self._nouveau_noeud(lat, lon))
            wid = self._nouvelle_voie()
            tags = dict(ETIQUETTE)
            if t.get("acces_pieton") not in ACCES_OUVERTS:
                tags["foot"] = "private"
            self.voies[wid] = [ids, tags]
            self.ign.append(wid)
            ajoutes += 1
        for nid in set(bouts.values()):
            self._raccorder_osm(nid, index)
        # Un bout raccordé à un nœud OSM voisin ne garde qu'un nœud : le sien
        # devient celui de la voie OSM, partout où il apparaît.
        remplace = dict(self._liens)
        for wid in self.ign:
            ids = self.voies[wid][0]
            self.voies[wid][0] = [remplace.get(n, n) for n in ids]
        for nid in remplace:
            self.noeuds.pop(nid, None)
        return ajoutes

    # ------------------------------------------------------------ sorties

    def elements(self) -> list:
        """Le réseau entier au format Overpass (nœuds étiquetés, voies et leur
        géométrie, relations), pour l'analyse des franchissements."""
        elements = [{"type": "node", "id": nid, "lat": lat, "lon": lon, "tags": dict(tags)}
                    for nid, (lat, lon, tags) in self.noeuds.items() if tags]
        elements += [{"type": "way", "id": wid, "nodes": list(ids), "tags": dict(tags),
                      "geometry": [{"lat": self.noeuds[n][0], "lon": self.noeuds[n][1]} for n in ids]}
                     for wid, (ids, tags) in self.voies.items()]
        elements += [{"type": "relation", "id": rid, "members": list(membres), "tags": dict(tags)}
                     for rid, (membres, tags) in self.relations.items()]
        return elements

    def ecrire_pbf(self, chemin) -> None:
        import osmium     # chargé à la première fabrication, pas au démarrage
        from pathlib import Path
        Path(chemin).unlink(missing_ok=True)
        with osmium.SimpleWriter(str(chemin)) as w:
            for nid in sorted(self.noeuds):
                lat, lon, tags = self.noeuds[nid]
                w.add_node(osmium.osm.mutable.Node(id=nid, location=osmium.osm.Location(lon, lat), tags=tags, version=1))
            for wid in sorted(self.voies):
                ids, tags = self.voies[wid]
                w.add_way(osmium.osm.mutable.Way(id=wid, nodes=ids, tags=tags, version=1))
            for rid in sorted(self.relations):
                membres, tags = self.relations[rid]
                refs = [("w", m["ref"], m.get("role", "")) for m in membres
                        if m.get("type") == "way" and m.get("ref") in self.voies]
                w.add_relation(osmium.osm.mutable.Relation(id=rid, members=refs, tags=tags, version=1))


def _sous(a, b):
    return a[0] - b[0], a[1] - b[1]


def _echantillons(points, pas_m=PAS_M) -> list:
    """Points régulièrement espacés d'environ pas_m le long du tracé, bouts
    compris. Placés selon la distance parcourue et non aux sommets, ils ne
    dépendent pas de la façon dont la ligne est découpée."""
    xy = [_xy(lat, lon, *points[0]) for lat, lon in points]
    cumul = [0.0]
    for a, b in zip(xy, xy[1:]):
        cumul.append(cumul[-1] + math.dist(a, b))
    n = max(1, round(cumul[-1] / pas_m))
    resultat, k = [], 0
    for m in range(n + 1):
        s = cumul[-1] * m / n
        while k < len(cumul) - 2 and cumul[k + 1] < s:
            k += 1
        longueur = cumul[k + 1] - cumul[k]
        t = (s - cumul[k]) / longueur if longueur else 0.0
        (la, lo), (lb, lob) = points[k], points[k + 1]
        resultat.append((la + (lb - la) * t, lo + (lob - lo) * t))
    return resultat


def _part_couverte(points, index) -> float:
    """Part de la longueur du tracé qui passe à moins de COUVERT_M d'une voie OSM."""
    echantillons = _echantillons(points)
    couverts = sum(index.plus_proche(lat, lon, COUVERT_M) is not None for lat, lon in echantillons)
    return couverts / len(echantillons)
