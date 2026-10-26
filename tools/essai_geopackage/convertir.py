"""Essai : calques JSON gzip d'une maille -> GeoPackage (une table par nature d'objet).

python convertir.py SORTIE.gpkg MAILLE.json.gz [MAILLE.json.gz ...]
"""
import gzip, json, sys
import numpy as np
import pyogrio.raw
import shapely

sortie, entrees = sys.argv[1], sys.argv[2:]
tables = {"chemins_osm": [], "barrieres": [], "chemins_officiels": [], "franchissements": []}
for chemin in entrees:
    with gzip.open(chemin, "rt", encoding="utf-8") as f:
        d = json.load(f)
    tables["chemins_osm"] += d["osm"].get("voies", [])
    tables["barrieres"] += d["osm"].get("barrieres", [])
    tables["chemins_officiels"] += d.get("officiels", [])
    tables["franchissements"] += d.get("franchissements", [])


def geometrie(o):
    if "pts" in o:
        pts = o["pts"]
        return shapely.LineString([(lon, lat) for lat, lon in pts]) if len(pts) > 1 else shapely.Point(pts[0][1], pts[0][0])
    return shapely.Point(o["lon"], o["lat"])


ajout = False
for nom, objets in tables.items():
    if not objets:
        continue
    cles = sorted({k for o in objets for k in o} - {"pts", "lat", "lon"})
    valeurs = []
    for k in cles:
        col = [o.get(k) for o in objets]
        if all(v is None or isinstance(v, (int, bool)) and not isinstance(v, bool) for v in col) and any(v is not None for v in col):
            valeurs.append(np.array([v if v is not None else -1 for v in col], dtype=np.int64))
        else:
            valeurs.append(np.array(["" if v is None else v if isinstance(v, str) else json.dumps(v, ensure_ascii=False) for v in col], dtype=object))
    geoms = [geometrie(o) for o in objets]
    types = {g.geom_type for g in geoms}
    pyogrio.raw.write(sortie, shapely.to_wkb(geoms), valeurs, cles, layer=nom, driver="GPKG",
                      geometry_type=types.pop() if len(types) == 1 else "Unknown", crs="EPSG:4326",
                      append=ajout, layer_options={"SPATIAL_INDEX": "YES"})
    ajout = True
    print(f"{nom}: {len(objets)} objets, champs {cles}")
