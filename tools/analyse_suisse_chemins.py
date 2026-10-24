"""Auditer restrictions et raccordements OSM des chemins swissTLM3D locaux.

Lit trois tuiles de 0,05° via l'API geo.admin.ch et reprend le même critère
de recouvrement que ``essai_sources_chemins.py``. Le graphe d'extrémités est
un diagnostic, pas une simulation de trajet BRouter.
"""

import collections
import math
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import essai_sources_chemins as essai
from hike2gpx import fusion, franchissements as fr

for name, i, j in (("Val Onsernone", 924, 172), ("Vallemaggia", 926, 172), ("Schachental", 937, 174)):
    s, w, n, e = fr.bornes_tuile(i, j)
    rows, seen = [], set()
    for offset in range(0, 20000, 200):
        q = {"geometry": f"{w},{s},{e},{n}", "geometryType": "esriGeometryEnvelope", "sr": 4326,
             "layers": "all:ch.swisstopo.swisstlm3d-strassen", "tolerance": 0, "returnGeometry": "true",
             "geometryFormat": "geojson", "limit": 200, "offset": offset,
             "mapExtent": f"{w},{s},{e},{n}", "imageDisplay": "1024,1024,96"}
        data = essai.lire_json("https://api3.geo.admin.ch/rest/services/api/MapServer/identify?" + urllib.parse.urlencode(q))
        new = 0
        for feature in data.get("results", []):
            if feature["id"] in seen:
                continue
            seen.add(feature["id"])
            new += 1
            props = feature.get("properties") or feature.get("attributes") or {}
            for pts in essai.fr_lignes(feature.get("geometry")):
                for part in essai.decouper(pts, s, w, n, e):
                    rows.append((part, props))
        if not new:
            break
    elements = essai.en_cache(f"osm_{i}_{j}", lambda: fr.interroger(fr.requete(s - essai.MARGE, w - essai.MARGE, n + essai.MARGE, e + essai.MARGE)))
    network = fusion.Reseau()
    network.ajouter_osm(elements)
    covered = fusion.parts_couvertes([p for p, _ in rows], network.segments_osm())
    candidates = [(p, a) for (p, a), x in zip(rows, covered) if x < fusion.PART_COUVERTE_MAX]
    by_access = collections.defaultdict(float)
    by_type = collections.defaultdict(float)
    connection = collections.defaultdict(float)
    index = network.index()
    parent = list(range(2 * len(candidates)))
    def find(v):
        while parent[v] != v:
            parent[v] = parent[parent[v]]
            v = parent[v]
        return v
    def join(a, b):
        parent[find(a)] = find(b)
    cells = collections.defaultdict(list)
    anchored = []
    for points, attrs in candidates:
        length = essai.longueur_km(points)
        by_access[attrs.get("verkehrsbeschraenkung")] += length
        by_type[attrs.get("objektart")] += length
        ends = sum(index.plus_proche(*point, 15) is not None for point in (points[0], points[-1]))
        connection[ends] += length
        anchored.append(ends > 0)
    for k, (points, _) in enumerate(candidates):
        join(2 * k, 2 * k + 1)
        for side, (lat, lon) in enumerate((points[0], points[-1])):
            cell = (round(lat / 0.00002), round(lon / 0.00002))
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for other, la, lo in cells.get((cell[0] + dx, cell[1] + dy), []):
                        metres = fr.M_PAR_DEGRE * math.hypot(lat - la, (lon - lo) * math.cos(math.radians(lat)))
                        if metres <= 1.5:
                            join(2 * k + side, other)
            cells[cell].append((2 * k + side, lat, lon))
    component_km = collections.defaultdict(float)
    component_anchor = collections.defaultdict(bool)
    for k, (points, _) in enumerate(candidates):
        root = find(2 * k)
        component_km[root] += essai.longueur_km(points)
        component_anchor[root] |= anchored[k]
    linked_km = sum(length for root, length in component_km.items() if component_anchor[root])
    print(name, "features", len(seen), "source_parts", len(rows), "candidate_parts", len(candidates),
          "km", round(sum(by_access.values()), 1),
          "access", {str(k): round(v, 1) for k, v in by_access.items()},
          "classes", {str(k): round(v, 1) for k, v in by_type.items()},
          "ends_15m", {str(k): round(v, 1) for k, v in connection.items()},
          "components", len(component_km), "linked_to_osm_km", round(linked_km, 1), flush=True)
