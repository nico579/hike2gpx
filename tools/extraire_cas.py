"""Extrait du cache Overpass un petit cas réel, figé pour les tests : les voies
et barrières qui ont un nœud dans un rectangle, leurs nœuds étiquetés, et les
itinéraires balisés qui passent par elles (réduits à ces voies).

    python tools/extraire_cas.py 43.3225 6.0390 43.3250 6.0435 tests/donnees/gareoult_cloture.json

Les tuiles doivent être dans le cache (HIKE2GPX_HOME), ou Overpass répondre.
"""
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hike2gpx import franchissements as fr  # noqa: E402
from hike2gpx.__main__ import DOSSIERS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for nom in ("sud", "ouest", "nord", "est"):
        parser.add_argument(nom, type=float)
    parser.add_argument("sortie", type=Path)
    a = parser.parse_args()
    dossier = DOSSIERS.dossier_etat()
    elements, lu_le = {}, []
    for i, j in fr.tuiles_zone(a.sud, a.ouest, a.nord, a.est):
        donnees = fr.charger_tuile(i, j, dossier)
        lu_le.append(donnees["fetched_at"])
        for e in donnees["elements"]:
            elements[e["type"], e["id"]] = e

    def dedans(p):
        return a.sud <= p["lat"] <= a.nord and a.ouest <= p["lon"] <= a.est

    voies = [e for e in elements.values() if e["type"] == "way" and any(dedans(p) for p in e.get("geometry", ()))]
    ids = {w["id"] for w in voies}
    noeuds_voies = {n for w in voies for n in w["nodes"]}
    noeuds = [e for e in elements.values() if e["type"] == "node" and e["id"] in noeuds_voies]
    relations = []
    for e in elements.values():
        membres = [m for m in e.get("members", ()) if m.get("type") == "way" and m.get("ref") in ids]
        if e["type"] == "relation" and membres:
            relations.append({**e, "members": membres})
    cas = {"source": "OpenStreetMap, par Overpass", "licence": "© contributeurs OpenStreetMap, ODbL 1.0",
           "zone": [a.sud, a.ouest, a.nord, a.est],
           "lu_le": dt.datetime.fromtimestamp(min(lu_le), dt.timezone.utc).date().isoformat(),
           "elements": noeuds + voies + relations}
    a.sortie.write_text(json.dumps(cas, ensure_ascii=False), encoding="utf-8")
    print(f"{a.sortie} : {len(noeuds)} nœuds, {len(voies)} voies, {len(relations)} relations, "
          f"{a.sortie.stat().st_size // 1024} Ko")
    return 0


if __name__ == "__main__":
    sys.exit(main())
