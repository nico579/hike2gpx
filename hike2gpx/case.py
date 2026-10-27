"""Fabrication d'une case RD5 enrichie, maille par maille.

Une case BRouter de 5° ne tient pas en mémoire d'un bloc : la fusion d'OSM et
des chemins officiels (fusion.Reseau) se fait par mailles de 0,25°, chacune
lue avec une couronne de voisinage. Un registre commun à la case garde le
réseau d'un seul tenant :
- les objets ajoutés reçoivent des identifiants uniques dans la case, au-delà
  des plus grands d'OSM ;
- un tronçon officiel n'est ajouté que par la maille de son premier point, et
  ses bouts, partagés entre mailles, gardent le même nœud de part et d'autre
  d'une limite ;
- les nœuds de raccord insérés dans une voie OSM sont notés par segment
  d'origine, puis réunis : une voie longue peut en recevoir de plusieurs
  mailles.
Un seul passage sur le PBF de la case écrit enfin OSM, ces raccords et les
voies ajoutées ; le créateur de BRouter le compile comme un extrait ordinaire.
"""
from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

from . import franchissements as fr, fusion, geofabrik

MAILLE_DEG = 0.25
HALO_DEG = 0.05


class Identifiants:
    """Compteurs des nœuds et voies ajoutés, communs à toutes les mailles."""

    def __init__(self, premier_noeud: int, premiere_voie: int):
        self.premier_noeud = premier_noeud
        self._noeud, self._voie = premier_noeud, premiere_voie

    def noeud(self) -> int:
        self._noeud += 1
        return self._noeud - 1

    def voie(self) -> int:
        self._voie += 1
        return self._voie - 1


def _position(p, a, b) -> float:
    """Abscisse (0 à 1) de la projection de p sur le segment a-b."""
    echelle = math.cos(math.radians(a[0]))
    vx, vy = (b[1] - a[1]) * echelle, b[0] - a[0]
    px, py = (p[1] - a[1]) * echelle, p[0] - a[0]
    return max(0.0, min(1.0, (px * vx + py * vy) / (vx * vx + vy * vy or 1)))


def mailles(sud: float, ouest: float, nord: float, est: float) -> list:
    """Coins sud-ouest des mailles qui touchent l'emprise."""
    rang = lambda v: math.floor(v / MAILLE_DEG + 1e-9)
    return [(la * MAILLE_DEG, lo * MAILLE_DEG)
            for la in range(rang(sud), rang(nord - 1e-9) + 1)
            for lo in range(rang(ouest), rang(est - 1e-9) + 1)]


def elements_osm(extrait: dict, sud: float, ouest: float) -> list:
    """Les éléments OSM de la maille et de sa couronne, lus dans l'index local."""
    elements = []
    for i, j in fr.tuiles_zone(sud - HALO_DEG, ouest - HALO_DEG,
                               sud + MAILLE_DEG + HALO_DEG, ouest + MAILLE_DEG + HALO_DEG):
        elements += geofabrik.elements_tuile(extrait, i, j)
    return elements


class Registre:
    def __init__(self, premier_noeud: int, premiere_voie: int):
        self.identifiants = Identifiants(premier_noeud, premiere_voie)
        self.bouts = {}             # point -> nœud final, partagé entre mailles
        self.bords = defaultdict(list)  # bouts coupés par basemap.de (ATKIS), recollés d'une maille à l'autre
        self.noeuds = {}            # nœuds ajoutés : id -> (lat, lon)
        self.voies = {}             # voies ajoutées : id -> (ids, tags)
        self.raccords = {}          # voie OSM -> {rang du segment d'origine -> {nœud: abscisse}}
        self.franchissements = {}   # clé -> franchissement

    def fusionner(self, elements: list, troncons: list, sud: float, ouest: float, source: str = "ign") -> dict:
        """Fusionne une maille : ses tronçons (ceux dont le premier point y tombe)
        dans OSM lu avec la couronne. Un tronçon peut porter sa source (une
        maille frontalière mêle plusieurs fournisseurs). Rend les comptes."""
        nord, est = sud + MAILLE_DEG, ouest + MAILLE_DEG
        dedans = lambda lat, lon: sud <= lat < nord and ouest <= lon < est
        reseau = fusion.Reseau(self.identifiants)
        reseau.ajouter_osm(elements)
        origine = {wid: list(ids) for wid, (ids, _) in reseau.voies.items()}
        a_moi = [t for t in troncons if t.get("pts") and dedans(*t["pts"][0])]
        ajoutes = reseau.ajouter_ign(a_moi, source=source, bouts=self.bouts, bords=self.bords)
        for wid in reseau.ign:
            ids, tags = reseau.voies[wid]
            self.voies[wid] = (list(ids), dict(tags))
            for n in ids:
                if n >= self.identifiants.premier_noeud and n in reseau.noeuds:
                    self.noeuds.setdefault(n, tuple(reseau.noeuds[n][:2]))
        raccords = 0
        for wid, avant in origine.items():
            apres = reseau.voies[wid][0]
            if len(apres) == len(avant):
                continue
            rang = 0
            for n in apres:
                if rang < len(avant) and n == avant[rang]:
                    rang += 1
                    continue
                a, b = reseau.noeuds[avant[rang - 1]][:2], reseau.noeuds[avant[rang]][:2]
                p = tuple(reseau.noeuds[n][:2])
                self.noeuds[n] = p
                self.raccords.setdefault(wid, {}).setdefault(rang - 1, {})[n] = _position(p, a, b)
                raccords += 1
        # Un franchissement d'un chemin ajouté ici appartient à cette maille,
        # même dans la couronne : la voisine ne connaît pas ce chemin.
        ajoutees = set(reseau.ign)
        gardes = 0
        for f in fr.analyser(reseau.elements()):
            if set(f.get("voies", ())) & ajoutees or dedans(f["lat"], f["lon"]):
                self.franchissements.setdefault(f["cle"], f)
                gardes += 1
        return {"voies_osm": len(origine), "troncons": len(a_moi), "ajoutes": ajoutes,
                "raccords": raccords, "franchissements": gardes}

    def noeuds_corriges(self, wid: int, refs: list) -> list:
        """Les nœuds d'une voie OSM, raccords de toutes les mailles insérés."""
        inserts = self.raccords.get(wid, {})
        resultat = []
        for rang, n in enumerate(refs):
            resultat.append(n)
            if rang in inserts:
                resultat += sorted(inserts[rang], key=inserts[rang].get)
        return resultat

    def ecrire_pbf(self, source: Path, sortie: Path) -> None:
        """OSM de la case, raccords et voies ajoutées, dans l'ordre que lisent
        les outils : nœuds, voies puis relations, chacun par identifiant."""
        import osmium
        Path(sortie).unlink(missing_ok=True)

        def noeuds(w):
            for nid, (lat, lon) in sorted(self.noeuds.items()):
                w.add_node(osmium.osm.mutable.Node(id=nid, location=osmium.osm.Location(lon, lat), version=1))

        def voies(w):
            for wid, (ids, tags) in sorted(self.voies.items()):
                w.add_way(osmium.osm.mutable.Way(id=wid, nodes=ids, tags=tags, version=1))

        etape = "noeuds"
        with osmium.SimpleWriter(str(sortie)) as w:
            for o in osmium.FileProcessor(str(source)):
                genre = o.type_str()
                if genre == "n":
                    w.add_node(o)
                    continue
                if etape == "noeuds":
                    noeuds(w)
                    etape = "voies"
                if genre == "w":
                    if o.id in self.raccords:
                        o = o.replace(nodes=self.noeuds_corriges(o.id, [n.ref for n in o.nodes]))
                    w.add_way(o)
                    continue
                if etape == "voies":
                    voies(w)
                    etape = "relations"
                w.add_relation(o)
            if etape == "noeuds":
                noeuds(w)
            if etape != "relations":
                voies(w)


def troncons_gpkg(gpkg, sud: float, ouest: float, nord: float, est: float, departement: str | None = None) -> list:
    """Tronçons BD TOPO d'un GeoPackage régional qui touchent l'emprise, entiers
    (la maille garde ceux dont le premier point y tombe), au format de la
    fusion. departement : ne garder que ceux d'un département (« 83 »).
    Reprend la lecture par l'index RTree de la PR #37. Le passage du Lambert 93
    au GPS se fait par rasterio (GDAL et PROJ), déjà embarqué pour le dénivelé,
    en un seul appel pour tous les points de l'emprise."""
    import sqlite3
    from contextlib import closing

    import numpy as np
    from rasterio.warp import transform as reprojeter
    from shapely import from_wkb, get_coordinates, get_parts

    bord = [(ouest + (est - ouest) * k / 8, la) for la in (sud, nord) for k in range(9)]
    bord += [(lo, sud + (nord - sud) * k / 8) for lo in (ouest, est) for k in range(9)]
    xs, ys = reprojeter("EPSG:4326", "EPSG:2154", [lo for lo, _ in bord], [la for _, la in bord])
    requete = ("SELECT t.cleabs, t.nature, t.acces_pieton, t.prive, t.geometrie "
               "FROM rtree_troncon_de_route_geometrie r JOIN troncon_de_route t ON t.fid = r.id "
               "WHERE r.minx <= ? AND r.maxx >= ? AND r.miny <= ? AND r.maxy >= ?")
    valeurs = [max(xs), min(xs), max(ys), min(ys)]
    if departement:
        requete += " AND (t.insee_commune_gauche LIKE ? OR t.insee_commune_droite LIKE ?)"
        valeurs += [departement + "%"] * 2
    tailles = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
    troncons, morceaux = [], []
    with closing(sqlite3.connect(f"file:{Path(gpkg).resolve().as_posix()}?mode=ro", uri=True)) as base:
        for cleabs, nature, acces, prive, blob in base.execute(requete, valeurs):
            for k, ligne in enumerate(get_parts(from_wkb(blob[8 + tailles[(blob[3] >> 1) & 7]:]))):
                points = get_coordinates(ligne)        # x, y en Lambert 93, sans l'altitude
                if len(points) >= 2:
                    troncons.append({"id": f"{cleabs}-{k}", "nature": nature, "acces_pieton": acces,
                                     "prive": bool(prive)})
                    morceaux.append(points)
    if not morceaux:
        return []
    tous = np.concatenate(morceaux)
    lons, lats = reprojeter("EPSG:2154", "EPSG:4326", tous[:, 0].tolist(), tous[:, 1].tolist())
    debut = 0
    for t, points in zip(troncons, morceaux):
        fin = debut + len(points)
        t["pts"] = [[round(la, 7), round(lo, 7)] for lo, la in zip(lons[debut:fin], lats[debut:fin])]
        debut = fin
    return troncons


class StockOSM:
    """Les éléments OSM d'une zone, lus tuile par tuile dans les extraits
    installés (geofabrik.elements_tuile), gardés sur disque pour écrire le PBF
    de la zone : une case entière ne tiendrait pas en mémoire. Un nœud y garde
    ses tags quand une tuile les donne, sa seule position sinon."""

    def __init__(self, chemin: Path):
        Path(chemin).unlink(missing_ok=True)
        self.base = sqlite3.connect(str(chemin))
        self.base.executescript(
            "PRAGMA journal_mode = OFF; PRAGMA synchronous = OFF;"
            "CREATE TABLE noeuds(id INTEGER PRIMARY KEY, lat REAL, lon REAL, tags TEXT NOT NULL);"
            "CREATE TABLE voies(id INTEGER PRIMARY KEY, noeuds TEXT NOT NULL, tags TEXT NOT NULL);"
            "CREATE TABLE relations(id INTEGER PRIMARY KEY, membres TEXT NOT NULL, tags TEXT NOT NULL);")

    def ajouter(self, elements: list) -> None:
        noeuds, positions, voies, relations = [], [], [], []
        for e in elements:
            if e.get("type") == "node":
                noeuds.append((e["id"], e["lat"], e["lon"], json.dumps(e.get("tags") or {})))
            elif e.get("type") == "way" and e.get("geometry"):
                voies.append((e["id"], json.dumps(e["nodes"]), json.dumps(e.get("tags") or {})))
                positions += [(n, p["lat"], p["lon"]) for n, p in zip(e["nodes"], e["geometry"])]
            elif e.get("type") == "relation":
                relations.append((e["id"], json.dumps(e.get("members", [])), json.dumps(e.get("tags") or {})))
        with self.base:
            self.base.executemany("INSERT OR IGNORE INTO noeuds VALUES (?, ?, ?, '{}')", positions)
            self.base.executemany("INSERT INTO noeuds VALUES (?, ?, ?, ?) ON CONFLICT(id) DO UPDATE "
                                  "SET tags = excluded.tags WHERE excluded.tags != '{}'", noeuds)
            self.base.executemany("INSERT OR IGNORE INTO voies VALUES (?, ?, ?)", voies)
            self.base.executemany("INSERT OR IGNORE INTO relations VALUES (?, ?, ?)", relations)

    def maxima(self) -> tuple:
        """(plus grand nœud, plus grande voie) : les objets ajoutés viennent après."""
        return tuple(self.base.execute(f"SELECT coalesce(max(id), 0) FROM {table}").fetchone()[0]
                     for table in ("noeuds", "voies"))

    def ecrire_pbf(self, sortie: Path) -> None:
        """Le PBF de la zone, nœuds, voies puis relations, chacun par identifiant.
        Une relation ne garde que ses voies présentes, comme fusion.Reseau."""
        import osmium
        Path(sortie).unlink(missing_ok=True)
        with osmium.SimpleWriter(str(sortie)) as w:
            for nid, lat, lon, tags in self.base.execute("SELECT id, lat, lon, tags FROM noeuds ORDER BY id"):
                w.add_node(osmium.osm.mutable.Node(id=nid, location=osmium.osm.Location(lon, lat),
                                                   tags=json.loads(tags), version=1))
            presentes = set()
            for wid, noeuds, tags in self.base.execute("SELECT id, noeuds, tags FROM voies ORDER BY id"):
                presentes.add(wid)
                w.add_way(osmium.osm.mutable.Way(id=wid, nodes=json.loads(noeuds), tags=json.loads(tags), version=1))
            for rid, membres, tags in self.base.execute("SELECT id, membres, tags FROM relations ORDER BY id"):
                refs = [("w", m["ref"], m.get("role", "")) for m in json.loads(membres)
                        if m.get("type") == "way" and m.get("ref") in presentes]
                w.add_relation(osmium.osm.mutable.Relation(id=rid, members=refs, tags=json.loads(tags), version=1))

    def fermer(self) -> None:
        self.base.close()
