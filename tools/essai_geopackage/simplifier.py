"""Points gardés après simplification Douglas-Peucker, selon la tolérance (en degrés)."""
import gzip, json, sys
import shapely

for chemin, cle in ((sys.argv[1], "osm"), (sys.argv[2], "officiels")):
    with gzip.open(chemin, "rt", encoding="utf-8") as f:
        d = json.load(f)
    objets = d["osm"]["voies"] if cle == "osm" else d["officiels"]
    lignes = [shapely.LineString([(lo, la) for la, lo in o["pts"]]) for o in objets if len(o["pts"]) > 1]
    total = sum(len(l.coords) for l in lignes)
    for tol, metres in ((0.00001, "~1 m"), (0.00002, "~2 m"), (0.00005, "~5 m")):
        gardes = sum(len(shapely.simplify(l, tol, preserve_topology=False).coords) for l in lignes)
        print(f"{cle:9} tolérance {metres}: {gardes}/{total} points ({100 * gardes / total:.0f} %)")
