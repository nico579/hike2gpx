"""Données OpenStreetMap hors ligne : les extraits de Geofabrik, pour toute la
planète.

Geofabrik découpe la planète en quelque 550 régions, refaites chaque jour, et
les décrit dans un index qui donne le contour de chacune. Pour une tuile de
0,05°, hike2gpx retient le plus petit extrait qui la contient entièrement :
Provence-Alpes-Côte d'Azur à Garéoult, la Bavière à Munich. En France, les
départements d'OSM France passent avant (osmfr.py), sur le même modèle. Il se
télécharge de lui-même dès que la région sert, en tâche de fond (jusqu'à
plusieurs centaines de Mo, vérifiés par leur MD5), pendant qu'Overpass
continue de servir. pyosmium le lit une fois et range voies, barrières,
portails et itinéraires balisés dans une base SQLite indexée par tuile ; le
fichier téléchargé est alors effacé.

Une fois installé, l'extrait devient la source des tuiles qu'il contient :
lecture instantanée, sans quota ni panne, même hors connexion. Une tuile en
sort au format exact des réponses d'Overpass, l'analyse des franchissements
ne voit pas la différence. Overpass ne sert plus qu'au-delà (autre région,
tuile à cheval sur une frontière). Plus vieil que RENOUVELLEMENT_S, l'extrait
se renouvelle de lui-même en tâche de fond, l'ancien servant jusqu'à la
bascule.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import logging
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from nico579_commons import atomique, enfants

from . import __version__
from . import franchissements as fr

journal = logging.getLogger(__name__)

INDEX_URL = "https://download.geofabrik.de/index-v1.json"
INDEX_TTL_S = 30 * 86400
RENOUVELLEMENT_S = 7 * 86400        # le même âge maximal que le cache Overpass (TTL_S)
TAILLE_MAX = 2 * 1024 ** 3          # au-delà (grands pays d'un seul tenant), Overpass seul
# Geofabrik met parfois une minute à répondre, puis répond en 0,2 s (mesuré le
# 2026-10-20, après l'échec de l'extrait Centre sur un délai de 30 s) : délai
# large, et quelques essais avant de renoncer.
DELAI_S = 120
ESSAIS = 3
PAUSES_S = (10, 30)                 # entre deux essais
# 2 : identifiants des nœuds (int64) et points (lat, lon en int32 au 1e-7 degré,
# la précision d'OSM) en binaire petit-boutiste, au lieu de JSON.
VERSION_BASE = 2
AGENT = {"User-Agent": f"hike2gpx/{__version__}"}
LOT = 20000

SCHEMA = """
CREATE TABLE info(cle TEXT PRIMARY KEY, valeur TEXT NOT NULL);
CREATE TABLE voies(id INTEGER PRIMARY KEY, tags TEXT NOT NULL, noeuds BLOB NOT NULL, points BLOB NOT NULL);
CREATE TABLE tuiles(i INTEGER NOT NULL, j INTEGER NOT NULL, voie INTEGER NOT NULL);
CREATE TABLE noeuds(id INTEGER PRIMARY KEY, lat REAL NOT NULL, lon REAL NOT NULL, tags TEXT NOT NULL);
CREATE TABLE relations(id INTEGER PRIMARY KEY, tags TEXT NOT NULL, membres TEXT NOT NULL);
CREATE TABLE liens(voie INTEGER NOT NULL, relation INTEGER NOT NULL);
"""
INDEX_SQL = "CREATE INDEX tuiles_ij ON tuiles(i, j); CREATE INDEX liens_voie ON liens(voie);"


class ErreurExtrait(RuntimeError):
    """L'extrait n'a pas pu être téléchargé ou lu."""


def dossier_extraits(dossier) -> Path:
    return Path(dossier) / "geofabrik"


# ------------------------------------------------------------------ régions

def _dans(lat: float, lon: float, polygones: list) -> bool:
    """Point dans un MultiPolygon GeoJSON ([lon, lat]), trous compris : règle
    pair-impair sur tous les anneaux de chaque polygone."""
    for polygone in polygones:
        dedans = False
        for anneau in polygone:
            for (x1, y1), (x2, y2) in zip(anneau, anneau[1:] + anneau[:1]):
                if (y1 > lat) != (y2 > lat) and lon < x1 + (lat - y1) * (x2 - x1) / (y2 - y1):
                    dedans = not dedans
        if dedans:
            return True
    return False


def contient_tuile(region: dict, i: int, j: int) -> bool:
    """La tuile entière dans le contour : ses coins, le milieu de ses côtés et
    son centre (les contours de Geofabrik sont lisses et larges)."""
    sud, ouest, nord, est = fr.bornes_tuile(i, j)
    s, w, n, e = region["bornes"]
    if sud < s or nord > n or ouest < w or est > e:
        return False
    points = [(la, lo) for la in (sud, (sud + nord) / 2, nord) for lo in (ouest, (ouest + est) / 2, est)]
    return all(_dans(la, lo, region["polygones"]) for la, lo in points)


def _surface(region: dict) -> float:
    s, w, n, e = region["bornes"]
    return (n - s) * (e - w)


def region_de_tuile(regions: list, i: int, j: int) -> dict | None:
    """Le plus petit extrait qui contient toute la tuile, ou None."""
    candidates = [r for r in regions if contient_tuile(r, i, j)]
    return min(candidates, key=_surface) if candidates else None


def _region(feature: dict) -> dict | None:
    proprietes, geometrie = feature.get("properties") or {}, feature.get("geometry") or {}
    pbf = (proprietes.get("urls") or {}).get("pbf")
    if not pbf or geometrie.get("type") not in ("Polygon", "MultiPolygon"):
        return None
    polygones = geometrie["coordinates"] if geometrie["type"] == "MultiPolygon" else [geometrie["coordinates"]]
    polygones = [[[(float(x), float(y)) for x, y, *_ in anneau] for anneau in polygone] for polygone in polygones]
    lons = [x for p in polygones for a in p for x, _ in a]
    lats = [y for p in polygones for a in p for _, y in a]
    return {"id": str(proprietes["id"]), "nom": str(proprietes.get("name") or proprietes["id"]), "pbf": pbf,
            "bornes": (min(lats), min(lons), max(lats), max(lons)), "polygones": polygones}


def _a_garder(region: dict) -> dict:
    """Ce que la base d'un extrait garde de sa région : de quoi le renouveler
    sans index (voies_coupees : un extrait d'OSM France, osmfr.py)."""
    return {k: region[k] for k in ("id", "nom", "pbf", "bornes", "polygones", "voies_coupees") if k in region}


class Index:
    """Un index de régions gardé un mois au dossier de données. Il sert tel
    quel, même vieux, et se refait en tâche de fond : un seul à la fois, pas
    plus d'un essai par heure après un échec. Aucune requête de la page
    n'attend donc son téléchargement, qui prend parfois une minute chez
    Geofabrik (rapport du 2026-10-20). Absent, il rend une liste vide le
    temps de se préparer. Sert à Geofabrik comme à OSM France (osmfr.py)."""

    REESSAI_S = 3600.0

    def __init__(self, nom: str, fichier: str, batir):
        self.nom = nom              # pour le journal : « de Geofabrik », « d'OSM France »
        self.fichier = fichier      # au dossier des extraits
        self.batir = batir          # batir(ouvrir) -> [régions], sur le réseau
        self._verrou = threading.Lock()
        self._charge = {"cle": None, "regions": []}
        self._fil = None
        self._echec = None          # instant (monotonic) du dernier échec

    def chemin(self, dossier) -> Path:
        return dossier_extraits(dossier) / self.fichier

    def regions(self, dossier, *, maintenant=time.time) -> list:
        chemin = self.chemin(dossier)
        try:
            age = maintenant() - chemin.stat().st_mtime
        except OSError:
            age = None
        if age is None or age > INDEX_TTL_S:
            self.preparer(dossier)
        if age is None:
            return []
        with self._verrou:
            try:
                cle = (str(chemin), chemin.stat().st_mtime)
                if self._charge["cle"] != cle:
                    liste = json.loads(chemin.read_text(encoding="utf-8"))["regions"]
                    self._charge.update(cle=cle, regions=[{**r, "bornes": tuple(r["bornes"])} for r in liste])
            except (OSError, ValueError, KeyError, TypeError) as exc:
                journal.warning("Index %s illisible : %s", self.nom, exc)
                return []
            return self._charge["regions"]

    def preparer(self, dossier, *, ouvrir=None) -> None:
        with self._verrou:
            if self._fil is not None and self._fil.is_alive():
                return
            if self._echec is not None and time.monotonic() - self._echec < self.REESSAI_S:
                return
            self._fil = threading.Thread(target=self._refaire, args=(Path(dossier), ouvrir), daemon=True,
                                         name=f"index-{self.fichier}")
            self._fil.start()

    def _refaire(self, dossier: Path, ouvrir) -> None:
        debut = time.monotonic()
        try:
            liste = self.batir(ouvrir)
            if not liste:
                raise ValueError("aucune région")
            chemin = self.chemin(dossier)
            chemin.parent.mkdir(parents=True, exist_ok=True)
            atomique.ecrire_json(chemin, {"version": 1, "regions": liste}, indent=None)
        except Exception as exc:        # réseau, réponse inattendue : l'ancien index sert encore
            self._echec = time.monotonic()
            journal.warning("Index %s non bâti : %s", self.nom, exc)
        else:
            self._echec = None
            journal.info("Index %s bâti en %.0f s : %d régions", self.nom, time.monotonic() - debut, len(liste))


def _batir(ouvrir=None) -> list:
    """Les régions de l'index de Geofabrik, contours compris."""
    ouvrir = ouvrir or urllib.request.urlopen

    def lire():
        with ouvrir(urllib.request.Request(INDEX_URL, headers=AGENT), timeout=60) as reponse:
            return reponse.read()

    features = json.loads(_avec_essais(lire, time.sleep)).get("features", [])
    return [r for r in map(_region, features) if r]


# Les régions déjà lues, comme celles d'OSM France : un autre nom que
# l'ancien index-v1.json, qui gardait le GeoJSON brut de Geofabrik.
INDEX = Index("de Geofabrik", "geofabrik-v1.json", _batir)


def regions(dossier, **options) -> list:
    """Les régions de Geofabrik, sans jamais attendre son serveur (Index)."""
    return INDEX.regions(dossier, **options)


# ------------------------------------------------------------------ extraits installés

def _base(dossier, identifiant: str) -> Path:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", identifiant):
        raise ValueError(f"Identifiant d'extrait invalide : {identifiant}")
    return dossier_extraits(dossier) / f"{identifiant}.sqlite"


def _lire(base: Path):
    """Connexion en lecture seule, fermée en sortie de bloc : une base restée
    ouverte empêcherait sous Windows son remplacement au renouvellement."""
    return closing(sqlite3.connect(f"file:{base.as_posix()}?mode=ro", uri=True))


def _info(base: Path) -> dict:
    with _lire(base) as con:
        return {cle: json.loads(valeur) for cle, valeur in con.execute("SELECT cle, valeur FROM info")}


_installes = {"cle": None, "liste": []}


def installes(dossier) -> list:
    """Les extraits installés : leur région (contour compris, gardé dans la
    base : pas besoin de l'index) et la date de leurs données."""
    racine = dossier_extraits(dossier)
    bases = sorted(racine.glob("*.sqlite")) if racine.is_dir() else []
    cle = tuple((str(b), b.stat().st_mtime) for b in bases)
    if _installes["cle"] != cle:
        liste = []
        for base in bases:
            try:
                info = _info(base)
            except (sqlite3.Error, ValueError) as exc:
                journal.warning("Extrait illisible, ignoré : %s (%s)", base.name, exc)
                continue
            if info.get("version") == VERSION_BASE:
                liste.append({**info["region"], "bornes": tuple(info["region"]["bornes"]), "base": base,
                              "date": info["date"]})
        _installes.update(cle=cle, liste=liste)
    return _installes["liste"]


def extrait_de_tuile(dossier, i: int, j: int) -> dict | None:
    """Le plus petit extrait installé qui contient toute la tuile, aux voies
    entières d'abord. Celles d'un extrait d'OSM France s'arrêtent net à sa
    frontière (197 chemins et clôtures coupés dans le Var, aucun dans la PACA
    de Geofabrik) : un département ne sert qu'en attendant sa région de
    Geofabrik (Nico, 2026-10-20 : « dès que paca est dispo, on l'utilise pour
    ne pas avoir de pb aux frontières »)."""
    liste = installes(dossier)
    return region_de_tuile([r for r in liste if not r.get("voies_coupees")], i, j) or region_de_tuile(liste, i, j)


def _morceaux(valeurs: list, taille: int = 900):
    for k in range(0, len(valeurs), taille):
        yield valeurs[k:k + taille]


def elements_tuile(extrait: dict, i: int, j: int) -> list:
    """Les éléments de la tuile au format d'Overpass (requete() : voies et
    barrières qui la touchent, avec leur géométrie entière, nœuds barrière ou
    entrée de ces voies, itinéraires pédestres balisés qui les empruntent)."""
    with _lire(Path(extrait["base"])) as con:
        voies = con.execute("SELECT v.id, v.tags, v.noeuds, v.points FROM tuiles t JOIN voies v ON v.id = t.voie "
                            "WHERE t.i = ? AND t.j = ? ORDER BY v.id", (i, j)).fetchall()
        elements, ids_noeuds, chemins = [], set(), []
        for identifiant, tags, noeuds, points in voies:
            tags, noeuds = json.loads(tags), np.frombuffer(noeuds, "<i8").tolist()
            ids_noeuds.update(noeuds)
            if "highway" in tags:
                chemins.append(identifiant)
            # int / 1e7 donne le même flottant que le texte à 7 décimales d'Overpass.
            geometrie = (np.frombuffer(points, "<i4").reshape(-1, 2) / 1e7).tolist()
            elements.append({"type": "way", "id": identifiant, "nodes": noeuds, "tags": tags,
                             "geometry": [{"lat": la, "lon": lo} for la, lo in geometrie]})
        noeuds = []
        for lot in _morceaux(sorted(ids_noeuds)):
            noeuds += con.execute(f"SELECT id, lat, lon, tags FROM noeuds WHERE id IN ({','.join('?' * len(lot))})",
                                  lot).fetchall()
        relations = set()
        for lot in _morceaux(chemins):
            relations.update(r for (r,) in con.execute(
                f"SELECT relation FROM liens WHERE voie IN ({','.join('?' * len(lot))})", lot))
        lignes = []
        for lot in _morceaux(sorted(relations)):
            lignes += con.execute(f"SELECT id, tags, membres FROM relations WHERE id IN ({','.join('?' * len(lot))})",
                                  lot).fetchall()
    return ([{"type": "node", "id": n, "lat": la, "lon": lo, "tags": json.loads(t)} for n, la, lo, t in sorted(noeuds)]
            + elements
            + [{"type": "relation", "id": r, "members": json.loads(m), "tags": json.loads(t)} for r, t, m in lignes])


# ------------------------------------------------------------------ import

def tuiles_segment(la1: float, lo1: float, la2: float, lo2: float) -> set:
    """Les tuiles que traverse un segment, coins frôlés compris : il est coupé
    aux lignes de la grille, et chaque morceau compte pour la tuile qui
    contient son milieu."""
    pas = fr.TUILE_DEG
    coupes = {0.0, 1.0}
    for a, b in ((la1, la2), (lo1, lo2)):
        if a != b:
            bas, haut = sorted((a, b))
            coupes.update((k * pas - a) / (b - a) for k in range(math.floor(bas / pas) + 1, math.floor(haut / pas) + 1))
    coupes = sorted(t for t in coupes if 0.0 <= t <= 1.0)
    cases = {fr.tuile_du_point(la1, lo1), fr.tuile_du_point(la2, lo2)}
    for t1, t2 in zip(coupes, coupes[1:]):
        t = (t1 + t2) / 2
        cases.add(fr.tuile_du_point(la1 + t * (la2 - la1), lo1 + t * (lo2 - lo1)))
    return cases


def tuiles_ligne(points: list) -> set:
    """Les tuiles que traverse une ligne [(lat, lon), …]."""
    cases = {fr.tuile_du_point(*p) for p in points}
    for (la1, lo1), (la2, lo2) in zip(points, points[1:]):
        cases |= tuiles_segment(la1, lo1, la2, lo2)
    return cases


def tuiles_des_voies(voies: np.ndarray, longueurs: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Les lignes (i, j, voie) d'un lot de voies mises bout à bout : la tuile
    de chaque point, calculée d'un bloc comme _rang(), plus celles que
    traversent les seuls segments qui changent de tuile (tuiles_segment). La
    plupart des voies tiennent dans une tuile et ne coûtent qu'un calcul
    groupé (profil du 2026-10-19 : la moitié de l'import passait là)."""
    ti = np.floor(lat / fr.TUILE_DEG + 1e-9).astype(np.int64)
    tj = np.floor(lon / fr.TUILE_DEG + 1e-9).astype(np.int64)
    voie = np.repeat(voies, longueurs)
    lignes = [np.stack([ti, tj, voie], axis=1)]
    changent = np.nonzero((voie[1:] == voie[:-1]) & ((ti[1:] != ti[:-1]) | (tj[1:] != tj[:-1])))[0]
    if len(changent):
        lignes.append(np.array([(i, j, int(voie[k])) for k in changent.tolist()
                                for i, j in tuiles_segment(lat[k], lon[k], lat[k + 1], lon[k + 1])],
                               dtype=np.int64).reshape(-1, 3))
    tout = np.concatenate(lignes)
    if tout[:, 2].max() >= 1 << 33:     # identifiants hors de la clé ci-dessous
        return np.unique(tout, axis=0)
    # Dédoublonnage sur une seule clé entière, bien plus rapide qu'un tri à
    # trois colonnes : rangs décalés pour rester positifs sur toute la planète
    # (|i| ≤ 1800, |j| ≤ 3600), identifiants de voie sous 2^33.
    cle = ((tout[:, 0] + 2048) << 46) | ((tout[:, 1] + 4096) << 33) | tout[:, 2]
    cle = np.unique(cle)
    return np.stack([(cle >> 46) - 2048, ((cle >> 33) & 0x1FFF) - 4096, cle & ((1 << 33) - 1)], axis=1)


def date_des_donnees(pbf: Path) -> str | None:
    """La date des données d'un fichier PBF de Geofabrik (en-tête
    osmosis_replication_timestamp), ou None."""
    import osmium
    lecteur = osmium.io.Reader(str(pbf), osmium.osm.osm_entity_bits.NOTHING)
    try:
        return lecteur.header().get("osmosis_replication_timestamp") or None
    finally:
        lecteur.close()


def stockage_des_noeuds(base: Path) -> Path:
    return base.with_name(base.name + ".noeuds")


def _geometrie(voie, fabrique, tous_les_noeuds) -> tuple:
    """(identifiants int64, [[lon, lat], …]) d'une voie. La ligne entière vient
    d'un seul appel C++ (WKB) plutôt que nœud par nœud ; une voie qui sort de
    l'extrait (nœud sans position) ne garde, une à une, que ses nœuds placés."""
    import osmium
    ids = np.array([n.ref for n in voie.nodes], dtype=np.int64)     # plus vite que np.fromiter, mesuré
    try:
        brut = bytes.fromhex(fabrique.create_linestring(voie, use_nodes=tous_les_noeuds))
        # WKB : ordre des octets (1 = petit-boutiste), type, nombre de points, puis x, y.
        if brut[0] == 1 and int.from_bytes(brut[5:9], "little") == len(ids):
            return ids, np.frombuffer(brut, "<f8", offset=9).reshape(-1, 2)
    except (osmium.InvalidLocationError, RuntimeError):
        pass
    places = [(n.ref, n.location.lon, n.location.lat) for n in voie.nodes if n.location.valid()]
    return (np.array([p[0] for p in places], dtype=np.int64),
            np.array([p[1:] for p in places], dtype=np.float64).reshape(-1, 2))


def importer(pbf: Path, base: Path, region: dict, date: str, *, suivi=None) -> dict:
    """Range dans une base SQLite neuve ce que requete() demanderait à Overpass,
    pour toute la région. Rend les comptes de ce qui a été rangé.

    pyosmium garde son index de positions (stockage_des_noeuds) ouvert jusqu'à
    la fin du processus : installer() fait donc tourner cet import dans un
    processus à part (--importer-extrait), qui rend en sortant le fichier et
    la mémoire, et efface l'index ensuite."""
    import osmium
    base.unlink(missing_ok=True)
    stockage = stockage_des_noeuds(base)
    stockage.unlink(missing_ok=True)
    compte = {"voies": 0, "noeuds": 0, "relations": 0}
    con = sqlite3.connect(base)
    try:
        con.executescript("PRAGMA journal_mode = OFF; PRAGMA synchronous = OFF;" + SCHEMA)
        voies, points, noeuds, relations, liens = [], [], [], [], []

        def vider():
            if voies:
                tous = np.concatenate(points)
                tuiles = tuiles_des_voies(np.array([v[0] for v in voies], dtype=np.int64),
                                          np.array([len(p) for p in points]), tous[:, 0] / 1e7, tous[:, 1] / 1e7)
                con.executemany("INSERT INTO voies VALUES (?, ?, ?, ?)",
                                [(v, t, ids, p.tobytes()) for (v, t, ids), p in zip(voies, points)])
                con.executemany("INSERT INTO tuiles VALUES (?, ?, ?)", tuiles.tolist())
            con.executemany("INSERT OR REPLACE INTO noeuds VALUES (?, ?, ?, ?)", noeuds)
            con.executemany("INSERT OR REPLACE INTO relations VALUES (?, ?, ?)", relations)
            con.executemany("INSERT INTO liens VALUES (?, ?)", liens)
            for liste in (voies, points, noeuds, relations, liens):
                liste.clear()
            if suivi:
                suivi(compte)

        def parcourir():
            # Les positions de tous les nœuds passent par un index sur disque,
            # côté C++ ; Python ne voit que les objets qui portent l'une de ces
            # clés. Dans sa propre fonction : au retour, plus rien ne retient
            # l'index, que Windows refuserait sinon d'effacer.
            lecture = osmium.FileProcessor(str(pbf)).with_locations(f"sparse_file_array,{stockage}") \
                .with_filter(osmium.filter.KeyFilter("highway", "barrier", "entrance", "route"))
            fabrique, tous_les_noeuds = osmium.geom.WKBFactory(), osmium.geom.use_nodes.ALL
            for objet in lecture:
                if objet.is_node():
                    if "barrier" in objet.tags or "entrance" in objet.tags:
                        noeuds.append((objet.id, objet.location.lat, objet.location.lon,
                                       json.dumps(dict(objet.tags))))
                        compte["noeuds"] += 1
                elif objet.is_way():
                    tags = dict(objet.tags)
                    chemin = "highway" in tags and not fr._EXCLUES.match(tags["highway"])
                    if not chemin and "barrier" not in tags:
                        continue
                    ids, lonlat = _geometrie(objet, fabrique, tous_les_noeuds)
                    if len(ids) < 2:
                        continue
                    voies.append((objet.id, json.dumps(tags), ids.astype("<i8").tobytes()))
                    # (lat, lon) au 1e-7 degré, la précision d'OSM : entiers exacts.
                    points.append(np.rint(lonlat[:, ::-1] * 1e7).astype("<i4"))
                    compte["voies"] += 1
                elif objet.is_relation() and objet.tags.get("route") in ("hiking", "foot"):
                    membres = [{"type": {"n": "node", "w": "way", "r": "relation"}[m.type], "ref": m.ref,
                                "role": m.role} for m in objet.members]
                    relations.append((objet.id, json.dumps(dict(objet.tags)), json.dumps(membres)))
                    liens.extend((m["ref"], objet.id) for m in membres if m["type"] == "way")
                    compte["relations"] += 1
                if len(voies) + len(noeuds) + len(liens) >= LOT:
                    vider()

        parcourir()
        vider()
        con.executescript(INDEX_SQL)
        con.executemany("INSERT INTO info VALUES (?, ?)",
                        [(cle, json.dumps(valeur)) for cle, valeur in
                         {"version": VERSION_BASE, "region": _a_garder(region), "date": date,
                          "compte": compte}.items()])
        con.commit()
    finally:
        con.close()
    return compte


def _commande_import(pbf: Path, base: Path, region_json: Path, date: str) -> list:
    """Le programme lui-même, en mode import : l'exécutable une fois figé,
    python -m hike2gpx depuis les sources."""
    prefixe = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "hike2gpx"]
    return [*prefixe, "--importer-extrait", str(pbf), str(base), str(region_json), date]


class Abandon(Exception):
    """Une autre région sert désormais : ce téléchargement s'arrête, sans
    compter comme un échec."""


def _effacer(chemin: Path, essais: int = 30) -> None:
    """Efface un fichier de travail, en laissant au processus d'import qu'on
    vient d'arrêter le temps de le relâcher : sous Windows, le python.exe d'un
    venv n'est qu'un lanceur, et le vrai interpréteur meurt un peu après lui
    (WinError 5 constaté le 2026-10-20). Ce qui résiste reste, sans erreur :
    la prochaine installation de la région le reprend."""
    for _ in range(essais):
        try:
            chemin.unlink(missing_ok=True)
            return
        except PermissionError:
            time.sleep(0.1)
    journal.warning("Fichier de travail laissé, encore pris : %s", chemin)


def _surveiller(processus, continuer) -> None:
    """Met fin à l'import dès que continuer() devient faux. Un fil à part :
    l'import ne dit rien tant qu'il lit les nœuds, sa sortie ne suffit pas."""
    while processus.poll() is None:
        if not continuer():
            processus.terminate()
            return
        time.sleep(0.5)


def _importer_a_part(pbf: Path, base: Path, region: dict, date: str, suivi=None, continuer=None) -> dict:
    """importer() dans un processus à part, suivi par sa sortie : « voies N »
    au fil de l'import, « fini {comptes} » au bout. Il meurt avec hike2gpx
    (nico579_commons.enfants) : orphelin, il écrirait encore la base quand
    l'instance suivante relance le même import. continuer() faux l'arrête
    (Abandon)."""
    description = base.with_name(base.name + ".region.json")
    description.write_text(json.dumps(region), encoding="utf-8")
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    racine = None if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
    compte, fin = None, []
    try:
        with enfants.demarrer(_commande_import(pbf, base, description, date), stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                              errors="replace", cwd=racine, **options) as processus:
            if continuer:
                threading.Thread(target=_surveiller, args=(processus, continuer), daemon=True,
                                 name="geofabrik-import-surveillance").start()
            for ligne in processus.stdout:
                mots = ligne.split(maxsplit=1)
                if mots[:1] == ["voies"] and len(mots) == 2 and mots[1].strip().isdigit():
                    if suivi:
                        suivi(int(mots[1]))
                elif mots[:1] == ["fini"] and len(mots) == 2:
                    compte = json.loads(mots[1])
                else:
                    fin = (fin + [ligne.rstrip()])[-20:]
    finally:
        _effacer(description)
        _effacer(stockage_des_noeuds(base))
    if continuer and not continuer() and compte is None:
        raise Abandon()
    if processus.returncode or compte is None:
        raise ErreurExtrait("Import de l'extrait impossible : " + " | ".join(fin)[-400:])
    return compte


class ExtraitEcarte(ErreurExtrait):
    """Extrait trop gros, ou place disque insuffisante : la région reste à
    Overpass, sans nouvel essai jusqu'à la fin du programme."""


def _passagere(exc: BaseException) -> bool:
    """Une panne qui mérite un nouvel essai : délai dépassé, connexion refusée
    ou coupée, réponse tronquée, serveur surchargé (5xx, 429)."""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code >= 500 or exc.code == 429
    return isinstance(exc, (TimeoutError, ConnectionError, urllib.error.URLError, http.client.HTTPException))


def _avec_essais(lire, attendre):
    """lire() jusqu'à ESSAIS fois, tant que la panne est passagère."""
    for essai in range(1, ESSAIS + 1):
        try:
            return lire()
        except Exception as exc:
            if essai == ESSAIS or not _passagere(exc):
                raise
            journal.warning("Geofabrik, essai %d sur %d : %s", essai, ESSAIS, exc)
            attendre(PAUSES_S[min(essai, len(PAUSES_S)) - 1])


def message(exc: BaseException) -> str:
    """Une panne de téléchargement dite en clair, pour la page."""
    if isinstance(exc, ErreurExtrait):
        return str(exc)
    if isinstance(exc, urllib.error.HTTPError):
        return f"Geofabrik répond HTTP {exc.code}"
    if isinstance(getattr(exc, "reason", exc), TimeoutError):
        return "Geofabrik ne répond pas (délai dépassé)"
    if isinstance(exc, (urllib.error.URLError, ConnectionError, http.client.HTTPException)):
        return f"connexion à Geofabrik impossible ou coupée ({getattr(exc, 'reason', exc)})"
    return str(exc)


def _verifier_place(octets: int, dossier: Path) -> None:
    """Trois fois la taille de l'extrait : le fichier, la base et l'index des
    nœuds le temps de l'import."""
    if octets > TAILLE_MAX:
        raise ExtraitEcarte(f"extrait trop gros ({octets / 1024 ** 3:.1f} Go), Overpass reste la source")
    if shutil.disk_usage(dossier).free < 3 * octets:
        raise ExtraitEcarte(f"place disque insuffisante pour {octets / 1024 ** 2:.0f} Mo, "
                            "Overpass reste la source")


def _telecharger(url: str, cible: Path, *, suivi=None, ouvrir=None, attendre=time.sleep, continuer=None) -> None:
    """Le PBF, vérifié par le MD5 publié à côté du fichier daté vers lequel
    renvoie l'adresse « -latest » : une version parue entre-temps ne fait pas
    refuser le bon fichier, et un fichier qui ne correspond pas n'est jamais
    importé. Chaque requête a ESSAIS essais, et le PBF reprend là où le flux
    s'est coupé (en-tête Range). Taille et place disque se vérifient dès les
    en-têtes, ici, en tâche de fond, et non dans une requête de la page.
    continuer() faux arrête tout, à chaque mégaoctet (Abandon)."""
    ouvrir = ouvrir or urllib.request.urlopen
    continuer = continuer or (lambda: True)
    partiel = atomique.chemin_part(cible)
    flux = {"adresse": url, "recu": 0, "total": 0, "somme": hashlib.md5(usedforsecurity=False)}

    def lire_pbf():
        if not continuer():
            raise Abandon()
        recu = flux["recu"]
        entetes = {**AGENT, **({"Range": f"bytes={recu}-"} if recu else {})}
        with ouvrir(urllib.request.Request(flux["adresse"], headers=entetes), timeout=DELAI_S) as reponse, \
                open(partiel, "r+b" if recu else "wb") as sortie:
            flux["adresse"] = reponse.geturl() or flux["adresse"]
            if recu and reponse.status != 206:      # reprise refusée : tout recommencer
                recu, flux["somme"] = 0, hashlib.md5(usedforsecurity=False)
                sortie.truncate(0)
            sortie.seek(recu)
            if not flux["total"]:
                flux["total"] = recu + int(reponse.headers.get("Content-Length") or 0)
                _verifier_place(flux["total"], cible.parent)
                hote, _, fichier = flux["adresse"].split("//", 1)[-1].partition("/")
                journal.info("%s : %s, %d Mo", hote, fichier.rsplit("/", 1)[-1], flux["total"] // 1024 ** 2)
            while bloc := reponse.read(1 << 20):
                if not continuer():
                    raise Abandon()
                flux["somme"].update(bloc)
                sortie.write(bloc)
                recu += len(bloc)
                flux["recu"] = recu
                if suivi and flux["total"]:
                    suivi(min(recu / flux["total"], 1.0))
        if recu < flux["total"]:
            raise http.client.IncompleteRead(b"", flux["total"] - recu)

    def lire_md5():
        demande = urllib.request.Request(flux["adresse"] + ".md5", headers=AGENT)
        with ouvrir(demande, timeout=DELAI_S) as reponse:
            return reponse.read(4096).decode("ascii", "replace").split()[0].lower()

    try:
        _avec_essais(lire_pbf, attendre)
        if flux["somme"].hexdigest() != _avec_essais(lire_md5, attendre):
            raise ErreurExtrait(f"Empreinte MD5 inattendue pour {flux['adresse']} : extrait refusé.")
        atomique.remplacer(partiel, cible)
    finally:
        partiel.unlink(missing_ok=True)


def installer(dossier, region: dict, *, suivi=None, ouvrir=None, continuer=None) -> dict:
    """Télécharge l'extrait, l'importe, puis remplace d'un coup l'ancienne base
    (une lecture en cours la garde ouverte jusqu'au bout). continuer() faux
    arrête le téléchargement ou l'import (Abandon) ; rien n'en reste."""
    debut = time.monotonic()
    base = _base(dossier, region["id"])
    base.parent.mkdir(parents=True, exist_ok=True)
    pbf = base.with_suffix(".osm.pbf")
    partielle = base.with_name(base.name + ".part")
    # Ce qu'une installation abandonnée ou coupée par l'arrêt du programme a pu
    # laisser pour cette région, téléchargement en cours (*.part) compris.
    for reste in (pbf, partielle, stockage_des_noeuds(partielle), *pbf.parent.glob(f"{pbf.name}.*.part")):
        _effacer(reste)
    try:
        _telecharger(region["pbf"], pbf, ouvrir=ouvrir, continuer=continuer,
                     suivi=(lambda f: suivi("telechargement", f)) if suivi else None)
        date = date_des_donnees(pbf) or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        compte = _importer_a_part(pbf, partielle, _a_garder(region),
                                  date, suivi=(lambda n: suivi("import", n)) if suivi else None, continuer=continuer)
        atomique.remplacer(partielle, base)
    finally:
        _effacer(pbf)
        _effacer(partielle)
    journal.info("Extrait OSM %s installé en %.0f s : données du %s, %d voies, %d nœuds, %d itinéraires",
                 region["id"], time.monotonic() - debut, date, compte["voies"], compte["noeuds"],
                 compte["relations"])
    return {"id": region["id"], "nom": region["nom"], "date": date, **compte}


def horodatage(extrait: dict) -> float:
    """La date des données de l'extrait, en secondes : le fetched_at de ses
    tuiles, stable tant que l'extrait ne change pas."""
    return datetime.strptime(extrait["date"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()


def age_s(extrait: dict, maintenant=time.time) -> float:
    return maintenant() - horodatage(extrait)


# ------------------------------------------------------------------ tâche de fond

class Telechargements:
    """Un téléchargement d'extrait à la fois, en tâche de fond, et son état
    pour la page."""

    REESSAI_S = 3600.0      # après un échec, pas de nouvel essai pour la même région avant une heure

    def __init__(self, dossier):
        self.dossier = Path(dossier)
        self._verrou = threading.Lock()
        self._etat = None
        self._fil = None
        self._numero = 0        # tâche en cours ; une plus récente l'abandonne
        self._echecs = {}       # id de région -> instant (monotonic) du dernier échec
        self._ecartes = set()   # trop gros, ou place disque insuffisante : Overpass seul

    def etat(self) -> dict | None:
        return dict(self._etat) if self._etat else None

    def disponible(self, region_id: str) -> bool:
        """Faux pour une région écartée (trop grosse, disque trop plein) ou dont
        le téléchargement a échoué il y a moins de REESSAI_S : la région qui la
        contient prend alors sa place (le département qui échoue cède à sa
        région, Nico, 2026-10-20)."""
        return region_id not in self._ecartes and \
            time.monotonic() - self._echecs.get(region_id, -self.REESSAI_S) >= self.REESSAI_S

    def occupee(self) -> bool:
        """Vrai pendant un téléchargement ou un import ; une tâche finie, dont
        le fil s'achève encore, ne compte plus."""
        return bool(self._fil is not None and self._fil.is_alive() and self._etat
                    and self._etat["etape"] in ("telechargement", "import"))

    def lancer(self, region: dict, *, ensuite: dict | None = None, relais: bool = False,
               apres: int | None = None) -> bool:
        """Faux si cette région se télécharge déjà, si elle est écartée (trop
        grosse, disque trop plein) ou si son téléchargement a échoué il y a
        moins de REESSAI_S : le téléchargement étant automatique, une panne ne
        doit pas le relancer à chaque demande de la page. Une autre région en
        cours est abandonnée, téléchargement ou import : le dernier usage
        l'emporte (Nico, 2026-10-20 : passé du Centre à la Bretagne, il
        attendait la fin du Centre, devenu inutile).
        ensuite : la région qui part dès celle-ci installée, pour prendre son
        relais (celle de Geofabrik après un département d'OSM France) ; relais :
        celle-ci est un tel relais, la page le dit ; apres : ne partir que si
        la tâche numéro apres est toujours la dernière."""
        with self._verrou:
            if apres is not None and apres != self._numero:
                return False        # un autre usage a pris la place entre-temps
            en_cours = self.occupee()
            if en_cours and self._etat["id"] == region["id"]:
                return False
            if region["id"] in self._ecartes:
                return False
            if time.monotonic() - self._echecs.get(region["id"], -self.REESSAI_S) < self.REESSAI_S:
                return False
            if en_cours:
                journal.info("Extrait OSM %s abandonné : la région %s sert désormais", self._etat["id"],
                             region["id"])
            self._numero += 1
            self._etat = {"id": region["id"], "nom": region["nom"], "etape": "telechargement", "fraction": 0.0,
                          "voies": 0, "relais": relais}
            self._fil = threading.Thread(target=self._executer, args=(region, self._numero, ensuite), daemon=True,
                                         name=f"geofabrik-{region['id']}")
            self._fil.start()
            return True

    def _suivre(self, numero: int, etape: str, valeur) -> None:
        if numero == self._numero:
            self._etat = {**self._etat, "etape": etape,
                          **({"fraction": round(valeur, 3)} if etape == "telechargement" else {"voies": valeur})}

    def _finir(self, numero: int, **etat) -> None:
        """L'état de la page, si cette tâche est toujours celle en cours."""
        if numero == self._numero:
            self._etat = {**self._etat, **etat}

    def _executer(self, region: dict, numero: int, ensuite: dict | None = None) -> None:
        try:
            resultat = installer(self.dossier, region, suivi=lambda etape, valeur: self._suivre(numero, etape, valeur),
                                 continuer=lambda: numero == self._numero)
        except Abandon:
            return              # la région suivante a pris la place, et l'état de la page
        except Exception as exc:
            if numero != self._numero:
                # Une erreur survenue en s'arrêtant n'est pas un échec : la région
                # repartira sans attendre une heure si elle resert.
                journal.info("Extrait OSM %s abandonné (%s)", region["id"], exc)
                return
            self._echouer(region, numero, exc)
        else:
            self._finir(numero, etape="fini", date=resultat["date"])
            # Le département d'OSM France est là, la page en dispose : sa région
            # de Geofabrik part aussitôt pour prendre le relais, à moins qu'un
            # autre usage n'ait pris la place entre-temps.
            if ensuite is not None and self.lancer(ensuite, relais=True, apres=numero):
                journal.info("Extrait OSM %s : téléchargement lancé pour prendre le relais de %s", ensuite["id"],
                             region["id"])

    def _echouer(self, region: dict, numero: int, exc: Exception) -> None:
        """Une panne de la tâche en cours, dite dans la page et le journal. Une
        région écartée (trop grosse, disque trop plein) ne repart plus ; après
        toute autre panne, pas de nouvel essai avant REESSAI_S."""
        if isinstance(exc, ExtraitEcarte):
            journal.warning("Extrait OSM %s non téléchargé : %s", region["id"], exc)
            self._ecartes.add(region["id"])
            self._finir(numero, etape="erreur", erreur=str(exc))
            return
        journal.warning("Extrait OSM %s non installé : %s", region["id"], exc)
        self._echecs[region["id"]] = time.monotonic()
        reprise = time.strftime("%H:%M", time.localtime(time.time() + self.REESSAI_S))
        self._finir(numero, etape="erreur", erreur=f"{message(exc)} ; nouvel essai après {reprise}")

    def renouveler_si_perime(self, extrait: dict) -> None:
        """Lancé à chaque lecture d'un extrait trop vieux : l'ancien sert jusqu'à
        la bascule."""
        if age_s(extrait) > RENOUVELLEMENT_S and not (self._fil and self._fil.is_alive()):
            journal.info("Extrait OSM %s du %s : renouvellement en tâche de fond", extrait["id"],
                         extrait["date"])
            self.lancer(extrait)


_telechargements = {}
_verrou_telechargements = threading.Lock()


def telechargements(dossier) -> Telechargements:
    with _verrou_telechargements:
        cle = os.path.normcase(str(Path(dossier).resolve()))
        if cle not in _telechargements:
            _telechargements[cle] = Telechargements(dossier)
        return _telechargements[cle]
