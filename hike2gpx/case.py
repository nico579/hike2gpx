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

from . import franchissements as fr, fusion

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


class IdentifiantsPartages(Identifiants):
    """Les mêmes compteurs, partagés entre les processus d'une fusion en
    damier (fabrication._fusionner_mailles). Chaque processus en prend des
    blocs : les identifiants restent presque contigus (au plus un bloc
    entamé par maille), sans plage fixe à dimensionner d'avance ni
    renumérotation après coup. Le créateur de tuiles BRouter paie en mémoire
    le plus grand identifiant (useDenseMaps), d'où des blocs petits.
    compteurs : {"noeud": Value, "voie": Value} de multiprocessing."""

    BLOC = 10_000

    def __init__(self, premier_noeud: int, compteurs: dict):
        self.premier_noeud = premier_noeud
        self._compteurs = compteurs
        self._plages = {"noeud": [0, 0], "voie": [0, 0]}

    def _suivant(self, genre: str) -> int:
        plage = self._plages[genre]
        if plage[0] == plage[1]:
            compteur = self._compteurs[genre]
            with compteur.get_lock():
                plage[0] = compteur.value
                compteur.value += self.BLOC
            plage[1] = plage[0] + self.BLOC
        plage[0] += 1
        return plage[0] - 1

    def noeud(self) -> int:
        return self._suivant("noeud")

    def voie(self) -> int:
        return self._suivant("voie")


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


class Registre:
    def __init__(self, premier_noeud: int, premiere_voie: int):
        self.identifiants = Identifiants(premier_noeud, premiere_voie)
        self.bouts = {}             # point -> nœud final, partagé entre mailles
        self.bords = defaultdict(list)  # bouts coupés par basemap.de (ATKIS), recollés d'une maille à l'autre
        self.noeuds = {}            # nœuds ajoutés : id -> (lat, lon)
        self.voies = {}             # voies ajoutées : id -> (ids, tags)
        self.raccords = {}          # voie OSM -> {rang du segment d'origine -> {nœud: abscisse}}
        self.franchissements = {}   # clé -> franchissement
        self._bouts_ecrits = None   # clés de bouts écrites depuis isoler()

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
        if self._bouts_ecrits is not None:          # maille isolée : relevé pour apport()
            self._bouts_ecrits.update(reseau.bouts_ecrits)
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

    # ------------------------------------------- fusion en damier (processus)

    def isoler(self) -> None:
        """Prépare la fusion d'une maille dans un processus fils : ce qu'elle
        ajoute est relevé à part (apport()), les bouts déjà connus restent."""
        # Les clés écrites, et non une copie de bouts : celle-ci, refaite à
        # chaque maille sur des millions de points, puis comparée en entier
        # dans apport(), coûtait plus que la fusion elle-même (issue #80).
        self._bouts_ecrits = set()
        self._bords_avant = {cle: len(v) for cle, v in self.bords.items()}
        self.noeuds, self.voies, self.raccords, self.franchissements = {}, {}, {}, {}

    def apport(self) -> dict:
        """Ce que la maille isolée a ajouté, à rendre au registre commun."""
        return {"noeuds": self.noeuds, "voies": self.voies, "raccords": self.raccords,
                "franchissements": self.franchissements,
                "bouts": {p: self.bouts[p] for p in self._bouts_ecrits},
                "bords": {cle: v[self._bords_avant.get(cle, 0):] for cle, v in self.bords.items()
                          if len(v) > self._bords_avant.get(cle, 0)}}

    def integrer(self, apport: dict) -> None:
        """Ajoute l'apport d'une maille fusionnée à part. Deux mailles d'une
        même phase ne sont jamais voisines, mais un tronçon qui enjamberait
        toute une maille peut leur faire créer chacune un nœud au même bout :
        le premier intégré reste, l'autre est renommé en lui partout."""
        renomme = {}
        for p, n in apport["bouts"].items():
            deja = self.bouts.get(p)
            if deja is not None and deja != n:
                renomme[n] = deja
            else:
                self.bouts[p] = n
        for wid, (ids, tags) in apport["voies"].items():
            self.voies[wid] = ([renomme.get(n, n) for n in ids], tags)
        for n, p in apport["noeuds"].items():
            if n not in renomme:
                self.noeuds.setdefault(n, p)
        for wid, par_rang in apport["raccords"].items():
            for rang, positions in par_rang.items():
                cible = self.raccords.setdefault(wid, {}).setdefault(rang, {})
                for n, x in positions.items():
                    cible[renomme.get(n, n)] = x
        for cle, f in apport["franchissements"].items():
            self.franchissements.setdefault(cle, f)
        for cle, entrees in apport["bords"].items():
            self.bords[cle].extend(entrees)

    def noeuds_corriges(self, wid: int, refs: list) -> list:
        """Les nœuds d'une voie OSM, raccords de toutes les mailles insérés."""
        inserts = self.raccords.get(wid, {})
        resultat = []
        for rang, n in enumerate(refs):
            resultat.append(n)
            if rang in inserts:
                resultat += sorted(inserts[rang], key=inserts[rang].get)
        return resultat

def troncons_gpkg(gpkg, sud: float, ouest: float, nord: float, est: float, departement: str | None = None) -> list:
    """Tronçons BD TOPO d'un GeoPackage régional qui touchent l'emprise, entiers
    (la maille garde ceux dont le premier point y tombe), au format de la
    fusion. departement : ne garder que ceux d'un département (« 83 »).
    Lus par l'index RTree (PR #37), puis ramenés du Lambert 93 au GPS par
    rasterio : en_bloc.lignes_gpkg, commun aux lectures en bloc."""
    from .en_bloc import lignes_gpkg
    filtre, valeurs = "", ()
    if departement:
        filtre, valeurs = "t.insee_commune_gauche LIKE ? OR t.insee_commune_droite LIKE ?", (departement + "%",) * 2
    return [{"id": f"{cleabs}-{k}", "nature": nature, "acces_pieton": acces, "prive": bool(prive), "pts": pts}
            for (cleabs, nature, acces, prive), k, pts
            in lignes_gpkg(gpkg, "troncon_de_route", ("cleabs", "nature", "acces_pieton", "prive"), 2154,
                           sud, ouest, nord, est, geometrie="geometrie", filtre=filtre, valeurs=valeurs)]


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

    def ecrire_pbf(self, sortie: Path, enrichi: Registre | None = None) -> None:
        """Le PBF de la zone, nœuds, voies puis relations, chacun par identifiant.
        Une relation ne garde que ses voies présentes, comme fusion.Reseau.

        enrichi : le registre de la case, pour écrire directement le PBF compilé
        — raccords insérés dans les voies OSM et voies ajoutées — au lieu d'un
        PBF intermédiaire que Registre relisait pour le réécrire (un passage de
        moins sur plusieurs centaines de Mo par case)."""
        import osmium
        Path(sortie).unlink(missing_ok=True)
        raccords = enrichi.raccords if enrichi is not None else {}
        noeuds_ajoutes = enrichi.noeuds if enrichi is not None else {}
        voies_ajoutees = enrichi.voies if enrichi is not None else {}
        with osmium.SimpleWriter(str(sortie)) as w:
            for nid, lat, lon, tags in self.base.execute("SELECT id, lat, lon, tags FROM noeuds ORDER BY id"):
                w.add_node(osmium.osm.mutable.Node(id=nid, location=osmium.osm.Location(lon, lat),
                                                   tags=json.loads(tags), version=1))
            for nid, (lat, lon) in sorted(noeuds_ajoutes.items()):
                w.add_node(osmium.osm.mutable.Node(id=nid, location=osmium.osm.Location(lon, lat), version=1))
            presentes = set()
            for wid, noeuds, tags in self.base.execute("SELECT id, noeuds, tags FROM voies ORDER BY id"):
                presentes.add(wid)
                refs = json.loads(noeuds)
                if wid in raccords:
                    refs = enrichi.noeuds_corriges(wid, refs)
                w.add_way(osmium.osm.mutable.Way(id=wid, nodes=refs, tags=json.loads(tags), version=1))
            for wid, (ids, tags) in sorted(voies_ajoutees.items()):
                presentes.add(wid)
                w.add_way(osmium.osm.mutable.Way(id=wid, nodes=ids, tags=tags, version=1))
            for rid, membres, tags in self.base.execute("SELECT id, membres, tags FROM relations ORDER BY id"):
                refs = [("w", m["ref"], m.get("role", "")) for m in json.loads(membres)
                        if m.get("type") == "way" and m.get("ref") in presentes]
                w.add_relation(osmium.osm.mutable.Relation(id=rid, members=refs, tags=json.loads(tags), version=1))

    def fermer(self) -> None:
        self.base.close()
