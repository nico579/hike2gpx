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

import functools
import gzip
import hashlib
import json
import math
import sqlite3
from contextlib import closing
from pathlib import Path

import mapbox_vector_tile
import numpy as np
import shapely

# Version du format de lot, lue par le téléphone et le PC. 2 : les couches
# reprennent celles de la page (voies, barrieres, troncons, franchissements).
# 3 : plusieurs fournisseurs par lot (une case frontalière), une couche de
# tronçons chacun, troncons_<calque> (troncons_bdtopo, troncons_swisstlm3d…).
FORMAT = 3
FORMATS_LUS = (2, 3)
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
            geometrie = geometries[i]
            # La plupart des objets tiennent dans la tuile : leur découpe GEOS
            # ne servirait à rien (mesuré sur un bloc réel, 2026-11-13).
            x0, y0, x1, y1 = geometrie.bounds
            if x0 >= boite[0] and y0 >= boite[1] and x1 <= boite[2] and y1 <= boite[3]:
                morceau = geometrie
            else:
                morceau = shapely.clip_by_rect(geometrie, *boite)
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
    # mtime=0 : l'en-tête gzip ne porte pas l'heure de compression. Deux
    # fabrications d'un même lot donnent ainsi les mêmes octets, même faites
    # par morceaux sur plusieurs machines (fabrication répartie).
    return gzip.compress(brut, 6, mtime=0)


def encoder_bloc(emprise: tuple, x10: int, y10: int, couches: dict) -> tuple:
    """Les tuiles du zoom 14 d'un bloc du zoom 10, sans rien écrire : (tuiles
    [(x, y, données)], champs {calque: {attribut: type}}). Sans effet de bord,
    elle peut tourner dans un processus à part (fabrication._calques)."""
    sud, ouest, nord, est = emprise
    pretes, champs = {}, {}
    for nom, objets in couches.items():
        geometries = [g for g, _ in objets]
        proprietes = [_proprietes(p) for _, p in objets]
        for p in proprietes:
            for k, v in p.items():
                champs.setdefault(nom, {})[k] = "String" if isinstance(v, str) else "Number"
        pretes[nom] = (shapely.STRtree(geometries) if geometries else None, geometries, proprietes)
    facteur = 2 ** (ZOOM - ZOOM_BLOC)
    o, s, e, n = bornes_tuile(ZOOM_BLOC, x10, y10)
    tuiles = []
    for x, y in tuiles_emprise(ZOOM, max(s, sud), max(o, ouest), min(n, nord), min(e, est)):
        if not (x10 * facteur <= x < (x10 + 1) * facteur and y10 * facteur <= y < (y10 + 1) * facteur):
            continue
        donnees = encoder_tuile(x, y, pretes, emprise)
        if donnees is not None:
            tuiles.append((x, y, donnees))
    return tuiles, champs


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
        """Encode les tuiles du zoom 14 d'un bloc du zoom 10 et les écrit. couches :
        {nom: [(géométrie lon/lat, propriétés)]}, lues sur le bloc et sa marge.
        Rend le nombre de tuiles."""
        return self.ecrire_bloc(*encoder_bloc(self.emprise, x10, y10, couches))

    def ecrire_bloc(self, tuiles: list, champs: dict) -> int:
        """Écrit les tuiles d'un bloc déjà encodé (encoder_bloc), éventuellement
        dans un autre processus : seule l'écriture passe par cette base."""
        for nom, types in champs.items():
            self.champs.setdefault(nom, {}).update(types)
        self.base.executemany("INSERT INTO tiles VALUES (?, ?, ?, ?)",
                              [(ZOOM, x, 2 ** ZOOM - 1 - y, donnees) for x, y, donnees in tuiles])
        self.base.commit()
        self.tuiles += len(tuiles)
        return len(tuiles)

    def abandonner(self) -> None:
        """Ferme la base sans la finir (arrêt, erreur) : sous Windows, un fichier
        resté ouvert ne pourrait plus être effacé ni réécrit."""
        self.base.close()

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


def assembler_calques(parties: list, cible: Path, nom: str, emprise: tuple, attribution: str) -> int:
    """Réunit les bases de calques faites à part (fabrication._calques, part
    i/K) en une seule : leurs tuiles, et l'union des champs de chaque calque
    lus dans leurs métadonnées. Rend le nombre de tuiles."""
    calques = Calques(cible, nom, emprise, attribution)
    try:
        for partie in parties:
            with closing(sqlite3.connect(f"file:{Path(partie).resolve().as_posix()}?mode=ro", uri=True)) as base:
                ligne = base.execute("SELECT value FROM metadata WHERE name = 'json'").fetchone()
                couches = json.loads(ligne[0]).get("vector_layers", []) if ligne else []
                champs = {c["id"]: c.get("fields", {}) for c in couches}
                tuiles = [(x, 2 ** ZOOM - 1 - rang, donnees) for x, rang, donnees in base.execute(
                    "SELECT tile_column, tile_row, tile_data FROM tiles WHERE zoom_level = ?", (ZOOM,))]
            calques.ecrire_bloc(tuiles, champs)
    except BaseException:
        calques.abandonner()
        raise
    total = calques.tuiles
    calques.fermer()
    return total


def boite_case(nom: str) -> tuple:
    """(sud, ouest, nord, est) d'une case BRouter nommée comme E5_N40 ou W5_N45."""
    sep = nom.index("_")
    lon = int(nom[1:sep]) * (-1 if nom[0] == "W" else 1)
    lat = int(nom[sep + 2:]) * (-1 if nom[sep + 1] == "S" else 1)
    return lat, lon, lat + 5, lon + 5


# Calque de la page -> couches du lot qui le composent.
# « jonctions » : les chemins non raccordés ; un lot fabriqué avant cette couche n'en a pas.
CALQUES = {"osm": ("voies", "barrieres", "franchissements", "jonctions")}


def couche_officielle(calque: str) -> str:
    """La couche des tronçons d'un fournisseur national (bdtopo, atkis…)."""
    return f"troncons_{calque}"


def couches_du_calque(calque: str) -> dict:
    """Couche du lot -> clé de la page, pour un calque ; un lot de format 2
    n'a qu'une couche « troncons », celle de la BD TOPO. La page s'en sert
    aussi quand elle lit elle-même les tuiles du lot (tuiles.js)."""
    return {c: c for c in CALQUES[calque]} if calque in CALQUES \
        else {couche_officielle(calque): "troncons", "troncons": "troncons"}


def lire_tuile(mbtiles: Path, x: int, y: int) -> bytes | None:
    """Les octets d'une tuile du zoom 14 du lot, tels quels (MVT, souvent
    gzippé) : la page les décode elle-même. None si la tuile manque."""
    with closing(sqlite3.connect(f"file:{Path(mbtiles).as_posix()}?mode=ro", uri=True)) as base:
        ligne = base.execute("SELECT tile_data FROM tiles WHERE zoom_level = ? AND tile_column = ? "
                             "AND tile_row = ?", (ZOOM, x, 2 ** ZOOM - 1 - y)).fetchone()
    return ligne[0] if ligne else None


def lire_calque(mbtiles: Path, calque: str, sud: float, ouest: float, nord: float, est: float) -> dict:
    """Le calque de la vue lu dans les tuiles du lot, au format des routes de la
    page : voies, barrières et tronçons avec leurs points [lat, lon], et les
    franchissements avec leur position. Une ligne coupée par plusieurs tuiles
    revient en morceaux, que la page dessine bout à bout : chacun est recoupé
    aux bords de sa tuile, sans la marge, pour ne rien dessiner deux fois."""
    couches = couches_du_calque(calque)
    resultat = {c: [] for c in couches.values()}
    vus = set()
    chemin = Path(mbtiles).resolve()
    date = chemin.stat().st_mtime_ns         # un lot réinstallé ne sert jamais d'anciennes tuiles
    for x, y in tuiles_emprise(ZOOM, sud, ouest, nord, est):
        tuile = _tuile_decodee(str(chemin), date, x, y)
        for nom in couches:
            for objet in tuile.get(nom, ()):
                if "lat" in objet:              # un franchissement, vu une fois
                    if objet.get("cle") in vus:
                        continue
                    vus.add(objet.get("cle"))
                resultat[couches[nom]].append(dict(objet))
    return resultat


@functools.lru_cache(maxsize=512)
def _tuile_decodee(chemin: str, date: int, x: int, y: int) -> dict:
    """Les objets d'une tuile du lot, décodés et en [lat, lon], gardés en mémoire :
    un déplacement de la carte ne décode que les tuiles neuves du bord de la vue
    (sans ce cache, chaque déplacement redécodait les 49 tuiles d'une vue, 3 à 4 s).
    Une ligne est recoupée aux bords de sa tuile, sans la marge, pour ne rien
    dessiner deux fois. Toutes les couches d'un coup : les calques OSM et officiel
    lisent les mêmes tuiles. Rend {couche: (objet, …)}."""
    with closing(sqlite3.connect(f"file:{Path(chemin).as_posix()}?mode=ro", uri=True)) as base:
        ligne = base.execute("SELECT tile_data FROM tiles WHERE zoom_level = ? AND tile_column = ? "
                             "AND tile_row = ?", (ZOOM, x, 2 ** ZOOM - 1 - y)).fetchone()
    if ligne is None:
        return {}
    o, s, e, n = bornes_tuile(ZOOM, x, y)
    _, my0 = mercator(o, s)
    _, my1 = mercator(e, n)

    def lonlat(points) -> np.ndarray:
        """Les points de la tuile (unités MVT) en [lon, lat], tous d'un coup."""
        p = np.asarray(points, dtype=float).reshape(-1, 2)
        my = my1 - p[:, 1] / ETENDUE * (my1 - my0)
        lats = np.degrees(2 * np.arctan(np.exp(my / RAYON)) - np.pi / 2)
        return np.round(np.column_stack([o + p[:, 0] / ETENDUE * (e - o), lats]), 6)

    objets = {}
    tuile = mapbox_vector_tile.decode(gzip.decompress(ligne[0]), default_options={"y_coord_down": True})
    for nom, couche in tuile.items():
        objets[nom] = liste = []
        for objet in couche.get("features", []):
            g, props = objet["geometry"], dict(objet["properties"])
            if g["type"] == "Point":
                props["lon"], props["lat"] = (float(v) for v in lonlat(g["coordinates"])[0])
                liste.append(props)
                continue
            parties = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
            for partie in parties:
                brut = np.asarray(partie, dtype=float)
                if len(brut) > 1 and brut.min() >= 0 and brut.max() <= ETENDUE:
                    # Dans la tuile, hors de la marge : rien à recouper.
                    liste.append({**props, "pts": lonlat(brut)[:, ::-1].tolist()})
                    continue
                coupee = shapely.clip_by_rect(shapely.LineString(lonlat(brut)), o, s, e, n)
                for morceau in shapely.get_parts(shapely.line_merge(coupee)) if not coupee.is_empty else []:
                    if morceau.geom_type == "LineString" and len(morceau.coords) > 1:
                        points = np.round(shapely.get_coordinates(morceau), 6)
                        liste.append({**props, "pts": points[:, ::-1].tolist()})
    return {nom: tuple(liste) for nom, liste in objets.items()}


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
