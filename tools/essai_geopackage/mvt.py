"""Essai : calques d'une maille en tuiles vectorielles MVT (un seul zoom), taille totale.

python mvt.py ZOOM OSM.json.gz IGN.json.gz
Chaque tuile du zoom couvrant la maille reçoit les objets découpés à ses bords
(avec une marge), quantifiés sur une grille de 4096, puis compressée en gzip
comme dans un MBTiles. Les attributs gardés sont ceux des calques actuels.
"""
import gzip, json, math, sys
import mapbox_vector_tile
import shapely

zoom = int(sys.argv[1])
couches = {"chemins_osm": [], "barrieres": [], "franchissements": [], "chemins_officiels": []}
for chemin in sys.argv[2:]:
    with gzip.open(chemin, "rt", encoding="utf-8") as f:
        d = json.load(f)
    couches["chemins_osm"] += d["osm"].get("voies", [])
    couches["barrieres"] += d["osm"].get("barrieres", [])
    couches["franchissements"] += d.get("franchissements", [])
    couches["chemins_officiels"] += d.get("officiels", [])


def geometrie(o):
    if "pts" in o:
        pts = [(lo, la) for la, lo in o["pts"]]
        return shapely.LineString(pts) if len(pts) > 1 else shapely.Point(pts[0])
    return shapely.Point(o["lon"], o["lat"])


def proprietes(o):
    return {k: v if isinstance(v, (str, int, float)) else json.dumps(v, ensure_ascii=False)
            for k, v in o.items() if k not in ("pts", "lat", "lon") and v is not None}


def tuile(lon, lat):
    n = 2 ** zoom
    return int((lon + 180) / 360 * n), int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)


def bornes(x, y):
    n = 2 ** zoom
    lon = lambda x: x / n * 360 - 180
    lat = lambda y: math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lon(x), lat(y + 1), lon(x + 1), lat(y)


objets = {nom: [(geometrie(o), proprietes(o)) for o in liste] for nom, liste in couches.items()}
toutes = [g for liste in objets.values() for g, _ in liste]
w, s, e, n = shapely.total_bounds(toutes)
x0, y0 = tuile(w, n)
x1, y1 = tuile(e, s)
arbres = {nom: shapely.STRtree([g for g, _ in liste]) for nom, liste in objets.items() if liste}
total_brut = total_gz = nb = 0
for x in range(x0, x1 + 1):
    for y in range(y0, y1 + 1):
        bw, bs, be, bn = bornes(x, y)
        marge = (be - bw) * 64 / 4096
        boite = shapely.box(bw - marge, bs - marge, be + marge, bn + marge)
        calques = []
        for nom, arbre in arbres.items():
            feats = []
            for i in arbre.query(boite, predicate="intersects"):
                g, p = objets[nom][i]
                feats.append({"geometry": shapely.intersection(g, boite).wkt, "properties": p})
            if feats:
                calques.append({"name": nom, "features": feats})
        if not calques:
            continue
        brut = mapbox_vector_tile.encode(calques, default_options={"quantize_bounds": (bw, bs, be, bn), "extents": 4096})
        nb += 1
        total_brut += len(brut)
        total_gz += len(gzip.compress(brut, 9))
print(f"zoom {zoom} : {nb} tuiles, {total_brut} octets bruts, {total_gz} octets gzip "
      f"(tuile moyenne {total_gz / nb / 1024:.1f} Ko)")
