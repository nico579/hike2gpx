"""Essai : temps de lecture d'une vue, JSON gzip actuel contre GeoPackage + RTree.

python mesurer.py DOSSIER_MAILLES FICHIER.gpkg
Les vues sont celles relevées dans les journaux du service le 25 octobre.
"""
import gzip, json, sqlite3, struct, sys, time
from pathlib import Path
import shapely

dossier, gpkg = Path(sys.argv[1]), sys.argv[2]
VUES = {
    "vue 0,024 x 0,073": (43.43665, 6.18445, 43.4603, 6.25775),
    "vue 0,006 x 0,018": (43.44628, 6.21696, 43.45219, 6.23529),
    "vue 0,0015 x 0,0046": (43.44889, 6.22445, 43.45037, 6.22903),
}
REPET = 5


def dans(pts, s, w, n, e):
    return any(s <= la <= n and w <= lo <= e for la, lo in pts)


def json_actuel(source, vue):
    s, w, n, e = vue
    trouves = []
    for f in sorted((dossier / source).glob("*.json.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            d = json.load(fh)
        objets = d["officiels"] if source != "osm" else d["osm"]["voies"]
        trouves += [o for o in objets if dans(o["pts"], s, w, n, e)]
    return trouves


def wkb_gpkg(blob):
    # En-tête GeoPackage : 'GP', version, drapeaux, srs_id, puis l'enveloppe selon les drapeaux.
    taille_env = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[(blob[3] >> 1) & 7]
    return blob[8 + taille_env:]


def gpkg_rtree(con, table, vue):
    s, w, n, e = vue
    lignes = con.execute(
        f"SELECT t.* FROM {table} t JOIN rtree_{table}_geom r ON t.fid = r.id "
        "WHERE r.minx <= ? AND r.maxx >= ? AND r.miny <= ? AND r.maxy >= ?", (e, w, n, s)).fetchall()
    geoms = shapely.from_wkb([wkb_gpkg(l[1]) for l in lignes])
    boite = shapely.box(w, s, e, n)
    return [l for l, g in zip(lignes, geoms) if shapely.intersects(g, boite)]


def chrono(f):
    durees = []
    for _ in range(REPET):
        t = time.perf_counter()
        r = f()
        durees.append(time.perf_counter() - t)
    return min(durees), r


con = sqlite3.connect(gpkg)
for source, table in (("ign", "chemins_officiels"), ("osm", "chemins_osm")):
    for nom, vue in VUES.items():
        tj, rj = chrono(lambda: json_actuel(source, vue))
        tg, rg = chrono(lambda: gpkg_rtree(con, table, vue))
        print(f"{source:3} {nom:20}  JSON gzip {tj*1000:8.1f} ms {len(rj):6} objets   "
              f"GeoPackage {tg*1000:7.1f} ms {len(rg):6} objets")
