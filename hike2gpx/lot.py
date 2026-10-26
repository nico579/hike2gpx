"""Le lot d'une case RD5 : calques en tuiles vectorielles et manifeste.

Une case de 5° se livre en un lot : la RD5 enrichie, les franchissements, les
calques affichés sur la carte et un manifeste qui les décrit. Le même code le
fabrique sur le PC (Windows) et sur le serveur (Linux) : les calques sont donc
encodés en Python, avec mapbox-vector-tile, et non par tippecanoe, absent de
Windows.

Les calques sont des tuiles vectorielles MVT du zoom 14, rangées dans un
MBTiles (spécification 1.3 : SQLite, rangées TMS, tuiles gzip). Les objets sont
coupés aux bords de la case : une tuile de bord appartient à deux cases, et
l'application affiche un calque par case, sans fusionner les fichiers.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import sqlite3
from pathlib import Path

import mapbox_vector_tile
import numpy as np
import shapely

# Version du format de lot, lue par le téléphone et le PC. 2 : les couches
# reprennent celles de la page (voies, barrieres, troncons, franchissements).
FORMAT = 2
ZOOM = 14
ZOOM_BLOC = 10                  # lecture des sources par blocs : 256 tuiles du zoom 14
ETENDUE = 4096
MARGE = 64 / ETENDUE            # marge d'une tuile, en fraction de tuile (convention de tippecanoe)
RAYON = 6378137.0


def mercator(lon, lat):
    """Lon/lat (degrés) vers Mercator sphérique (mètres), EPSG:3857."""
    lon, lat = np.asarray(lon, dtype=float), np.asarray(lat, dtype=float)
    return RAYON * np.radians(lon), RAYON * np.log(np.tan(math.pi / 4 + np.radians(lat) / 2))


def bornes_tuile(z: int, x: int, y: int) -> tuple:
    """(ouest, sud, est, nord) en degrés d'une tuile XYZ."""
    n = 2 ** z
    lat = lambda yy: math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yy / n))))
    return x / n * 360 - 180, lat(y + 1), (x + 1) / n * 360 - 180, lat(y)


def tuile_du_point(z: int, lon: float, lat: float) -> tuple:
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def tuiles_emprise(z: int, sud: float, ouest: float, nord: float, est: float) -> list:
    """Tuiles (x, y) du zoom z qui touchent l'emprise."""
    x0, y0 = tuile_du_point(z, ouest, nord - 1e-9)
    x1, y1 = tuile_du_point(z, est - 1e-9, sud)
    return [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]


def _proprietes(p: dict) -> dict:
    """Attributs acceptés par MVT : chaînes, nombres et booléens, sans valeur vide."""
    return {k: v for k, v in p.items() if isinstance(v, (str, int, float, bool)) and v != ""}


def encoder_tuile(x: int, y: int, couches: dict, emprise: tuple) -> bytes | None:
    """Tuile MVT (gzip) du zoom 14 ; couches : {nom: (arbre STRtree, géométries, propriétés)}.
    Les objets sont coupés à la tuile, marge comprise, et aux bords de la case
    (emprise : sud, ouest, nord, est). None si la tuile est vide."""
    o, s, e, n = bornes_tuile(ZOOM, x, y)
    marge_lon, marge_lat = (e - o) * MARGE, (n - s) * MARGE
    sud, ouest, nord, est = emprise
    boite = (max(o - marge_lon, ouest), max(s - marge_lat, sud), min(e + marge_lon, est), min(n + marge_lat, nord))
    rectangle = shapely.box(*boite)
    calques = []
    for nom, (arbre, geometries, proprietes) in couches.items():
        if arbre is None:
            continue
        objets = []
        for i in arbre.query(rectangle):
            morceau = shapely.clip_by_rect(geometries[i], *boite)
            if morceau.is_empty:
                continue
            objets.append({"geometry": shapely.transform(morceau, _vers_mercator), "properties": proprietes[i]})
        if objets:
            calques.append({"name": nom, "features": objets})
    if not calques:
        return None
    mx0, my0 = mercator(o, s)
    mx1, my1 = mercator(e, n)
    brut = mapbox_vector_tile.encode(calques, default_options={
        "quantize_bounds": (float(mx0), float(my0), float(mx1), float(my1)), "extents": ETENDUE})
    return gzip.compress(brut, 6)


def _vers_mercator(xy):
    mx, my = mercator(xy[:, 0], xy[:, 1])
    return np.column_stack([mx, my])


class Calques:
    """MBTiles des calques d'une case, écrit bloc par bloc."""

    def __init__(self, chemin: Path, nom: str, emprise: tuple, attribution: str):
        self.chemin, self.emprise = Path(chemin), emprise
        self.chemin.unlink(missing_ok=True)
        self.base = sqlite3.connect(self.chemin)
        self.base.executescript(
            "CREATE TABLE metadata (name TEXT, value TEXT);"
            "CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB);"
            "CREATE UNIQUE INDEX tile_index ON tiles (zoom_level, tile_column, tile_row);")
        self.champs: dict = {}
        self.nom, self.attribution = nom, attribution
        self.tuiles = 0

    def ajouter_bloc(self, x10: int, y10: int, couches: dict) -> int:
        """Encode les tuiles du zoom 14 d'un bloc du zoom 10. couches : {nom: [(géométrie
        lon/lat, propriétés)]}, lues sur le bloc et sa marge. Rend le nombre de tuiles."""
        sud, ouest, nord, est = self.emprise
        pretes = {}
        for nom, objets in couches.items():
            geometries = [g for g, _ in objets]
            proprietes = [_proprietes(p) for _, p in objets]
            for p in proprietes:
                for k, v in p.items():
                    self.champs.setdefault(nom, {})[k] = "String" if isinstance(v, str) else "Number"
            pretes[nom] = (shapely.STRtree(geometries) if geometries else None, geometries, proprietes)
        facteur = 2 ** (ZOOM - ZOOM_BLOC)
        o, s, e, n = bornes_tuile(ZOOM_BLOC, x10, y10)
        dedans = tuiles_emprise(ZOOM, max(s, sud), max(o, ouest), min(n, nord), min(e, est))
        ecrites = 0
        for x, y in dedans:
            if not (x10 * facteur <= x < (x10 + 1) * facteur and y10 * facteur <= y < (y10 + 1) * facteur):
                continue
            donnees = encoder_tuile(x, y, pretes, self.emprise)
            if donnees is not None:
                self.base.execute("INSERT INTO tiles VALUES (?, ?, ?, ?)", (ZOOM, x, 2 ** ZOOM - 1 - y, donnees))
                ecrites += 1
        self.base.commit()
        self.tuiles += ecrites
        return ecrites

    def fermer(self) -> None:
        sud, ouest, nord, est = self.emprise
        vector_layers = [{"id": nom, "fields": champs, "minzoom": ZOOM, "maxzoom": ZOOM}
                         for nom, champs in sorted(self.champs.items())]
        metadata = {"name": self.nom, "format": "pbf", "type": "overlay", "version": str(FORMAT),
                    "minzoom": str(ZOOM), "maxzoom": str(ZOOM), "bounds": f"{ouest},{sud},{est},{nord}",
                    "center": f"{(ouest + est) / 2},{(sud + nord) / 2},{ZOOM}",
                    "attribution": self.attribution, "json": json.dumps({"vector_layers": vector_layers})}
        self.base.executemany("INSERT INTO metadata VALUES (?, ?)", metadata.items())
        self.base.commit()
        self.base.execute("VACUUM")
        self.base.close()


class Sources:
    """Ce que montrent les calques d'une case, lu bloc par bloc, avec les règles
    de la page (franchissements.voies_affichables) : les voies praticables OSM
    et leur genre, les barrières linéaires qui gênent un piéton, les
    franchissements bloquants ou à vérifier de la fusion, et les tronçons BD
    TOPO de l'emprise enrichie. Les calques d'un lot s'affichent ainsi comme
    ceux que l'application lit en ligne."""

    def __init__(self, base_osm: Path, gpkg: Path | None = None, departement: str | None = None,
                 emprise_officielle: tuple | None = None, franchissements: list = ()):
        from . import franchissements as fr, regles
        self._fr, self._regles = fr, regles
        self.base = sqlite3.connect(f"file:{Path(base_osm).resolve().as_posix()}?mode=ro", uri=True)
        self.gpkg, self.departement, self.emprise_officielle = gpkg, departement, emprise_officielle
        self.franchissements = self._index(
            [(shapely.Point(f["lon"], f["lat"]), {c: f.get(c) for c in ("cle", "statut", "raison", "nature", "osm")})
             for f in franchissements if f.get("statut") in ("blocked", "uncertain")])

    @staticmethod
    def _index(objets: list) -> tuple:
        return objets, shapely.STRtree([g for g, _ in objets]) if objets else None

    @staticmethod
    def _dans(index: tuple, boite) -> list:
        objets, arbre = index
        return [] if arbre is None else [objets[i] for i in arbre.query(boite)]

    def bloc(self, sud: float, ouest: float, nord: float, est: float) -> dict:
        fr, regles = self._fr, self._regles
        (i0, j0), (i1, j1) = fr.tuile_du_point(sud, ouest), fr.tuile_du_point(nord, est)
        voies, barrieres = [], []
        for ident, tags, points in self.base.execute(
                "SELECT DISTINCT v.id, v.tags, v.points FROM tuiles t JOIN voies v ON v.id = t.voie "
                "WHERE t.i BETWEEN ? AND ? AND t.j BETWEEN ? AND ?", (i0, i1, j0, j1)):
            tags = json.loads(tags)
            latlon = np.frombuffer(points, "<i4").reshape(-1, 2) / 1e7
            if len(latlon) < 2:
                continue
            ligne = shapely.LineString(latlon[:, ::-1])
            if fr._praticable(tags):
                voies.append((ligne, {"id": ident, "genre": fr.GENRES.get(tags["highway"], "route")}))
            elif "barrier" in tags and "highway" not in tags and regles.status(tags, fr.MODE)[0] != "passable":
                barrieres.append((ligne, {"id": ident, "nature": regles.LABELS.get(tags["barrier"], "Barrière")}))
        officiels = []
        if self.gpkg and self.emprise_officielle:
            es, eo, en, ee = self.emprise_officielle
            if not (en <= sud or es >= nord or ee <= ouest or eo >= est):
                from .case import troncons_gpkg
                vus = set()
                for t in troncons_gpkg(self.gpkg, max(sud, es), max(ouest, eo), min(nord, en), min(est, ee),
                                       self.departement):
                    if t["id"] not in vus:
                        vus.add(t["id"])
                        officiels.append((shapely.LineString([(lo, la) for la, lo in t["pts"]]),
                                          {"id": t["id"], "nature": t["nature"],
                                           "acces_pieton": t.get("acces_pieton"), "prive": t.get("prive")}))
        return {"voies": voies, "barrieres": barrieres, "troncons": officiels,
                "franchissements": self._dans(self.franchissements, shapely.box(ouest, sud, est, nord))}

    def fermer(self) -> None:
        self.base.close()


def boite_case(nom: str) -> tuple:
    """(sud, ouest, nord, est) d'une case BRouter nommée comme E5_N40 ou W5_N45."""
    sep = nom.index("_")
    lon = int(nom[1:sep]) * (-1 if nom[0] == "W" else 1)
    lat = int(nom[sep + 2:]) * (-1 if nom[sep + 1] == "S" else 1)
    return lat, lon, lat + 5, lon + 5


# Calque de la page -> couches du lot qui le composent.
CALQUES = {"osm": ("voies", "barrieres", "franchissements"), "bdtopo": ("troncons",)}


def lire_calque(mbtiles: Path, calque: str, sud: float, ouest: float, nord: float, est: float) -> dict:
    """Le calque de la vue lu dans les tuiles du lot, au format des routes de la
    page : voies, barrières et tronçons avec leurs points [lat, lon], et les
    franchissements avec leur position. Une ligne coupée par plusieurs tuiles
    revient en morceaux, que la page dessine bout à bout : chacun est recoupé
    aux bords de sa tuile, sans la marge, pour ne rien dessiner deux fois."""
    couches = CALQUES[calque]
    resultat = {c: [] for c in couches}
    vus = set()
    with sqlite3.connect(f"file:{Path(mbtiles).resolve().as_posix()}?mode=ro", uri=True) as base:
        for x, y in tuiles_emprise(ZOOM, sud, ouest, nord, est):
            ligne = base.execute("SELECT tile_data FROM tiles WHERE zoom_level = ? AND tile_column = ? "
                                 "AND tile_row = ?", (ZOOM, x, 2 ** ZOOM - 1 - y)).fetchone()
            if ligne is None:
                continue
            o, s, e, n = bornes_tuile(ZOOM, x, y)
            mx0, my0 = mercator(o, s)
            mx1, my1 = mercator(e, n)

            def latlon(p):
                my = my1 - p[1] / ETENDUE * (my1 - my0)
                lat = math.degrees(2 * math.atan(math.exp(my / RAYON)) - math.pi / 2)
                return [round(lat, 6), round(o + p[0] / ETENDUE * (e - o), 6)]

            tuile = mapbox_vector_tile.decode(gzip.decompress(ligne[0]), default_options={"y_coord_down": True})
            for nom in couches:
                for objet in tuile.get(nom, {}).get("features", []):
                    g, props = objet["geometry"], dict(objet["properties"])
                    if g["type"] == "Point":
                        if props.get("cle") in vus:
                            continue
                        vus.add(props.get("cle"))
                        props["lat"], props["lon"] = latlon(g["coordinates"])
                        resultat[nom].append(props)
                        continue
                    parties = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
                    for partie in parties:
                        ligne = shapely.LineString([latlon(p)[::-1] for p in partie])
                        coupee = shapely.clip_by_rect(ligne, o, s, e, n)
                        for morceau in shapely.get_parts(shapely.line_merge(coupee)) if not coupee.is_empty else []:
                            if morceau.geom_type == "LineString" and len(morceau.coords) > 1:
                                resultat[nom].append({**props, "pts": [[round(la, 6), round(lo, 6)]
                                                                       for lo, la in morceau.coords]})
    return resultat


def blocs(sud: float, ouest: float, nord: float, est: float) -> list:
    """Blocs (x, y) du zoom 10 qui touchent la case."""
    return tuiles_emprise(ZOOM_BLOC, sud, ouest, nord, est)


def empreinte(chemin: Path) -> str:
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        while bloc := f.read(1 << 20):
            h.update(bloc)
    return h.hexdigest()


def ecrire_manifeste(dossier: Path, case: str, fichiers: list, sources: dict, **autres) -> Path:
    """manifest.json du lot : chaque fichier avec sa taille et son SHA-256, la
    version du format et l'édition des sources. Le même, quel que soit le
    producteur (PC ou serveur)."""
    from . import __version__
    from .brouter import VERSION as VERSION_BROUTER
    manifeste = {"format": FORMAT, "case": case, "producteur": f"hike2gpx {__version__}",
                 "brouter": VERSION_BROUTER, "sources": sources, **autres,
                 "fichiers": [{"nom": Path(f).name, "octets": Path(f).stat().st_size, "sha256": empreinte(f)}
                              for f in fichiers]}
    chemin = Path(dossier) / "manifest.json"
    chemin.write_text(json.dumps(manifeste, indent=1, ensure_ascii=False), encoding="utf-8")
    return chemin
