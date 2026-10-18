"""Inventaire d'une zone : voies, barrières qu'OpenStreetMap connaît, et
franchissements par catégorie, avec les temps de lecture.

    python tools/essai_zone.py 43.25 5.95 43.3999 6.0999

Données dans HIKE2GPX_HOME (ou le dossier d'état standard) ; une tuile absente
du cache est lue sur Overpass (25 à 40 s).
"""
import argparse
import collections
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hike2gpx import franchissements as fr  # noqa: E402
from hike2gpx.__main__ import DOSSIERS  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for nom in ("sud", "ouest", "nord", "est"):
        parser.add_argument(nom, type=float)
    a = parser.parse_args()
    dossier = DOSSIERS.dossier_etat()
    tuiles = fr.tuiles_zone(a.sud, a.ouest, a.nord, a.est)
    voies = lignes = noeuds = 0
    natures, liste = collections.Counter(), []
    debut = time.time()
    for i, j in tuiles:
        t = time.time()
        elements = fr.charger_tuile(i, j, dossier)["elements"]
        voies += sum(1 for e in elements if e["type"] == "way" and fr._praticable(e.get("tags", {})))
        for e in elements:
            if e["type"] == "way" and "barrier" in e.get("tags", {}):
                lignes += 1
                natures[e["tags"]["barrier"]] += 1
            elif e["type"] == "node" and "barrier" in e.get("tags", {}):
                noeuds += 1
        liste.extend(fr.franchissements_tuile(i, j, dossier))
        print(f"tuile {i}_{j} : {time.time() - t:5.1f} s", flush=True)
    print(f"\n{len(tuiles)} tuiles en {time.time() - debut:.0f} s : {voies} voies praticables, "
          f"{lignes} barrières en ligne, {noeuds} nœuds barrière")
    print("barrières en ligne :", ", ".join(f"{n} {nature}" for nature, n in natures.most_common()))
    print(f"{len(liste)} franchissements :", dict(collections.Counter(f["statut"] for f in liste)))
    for (statut, nature, raison), n in collections.Counter(
            (f["statut"], f["nature"], f["raison"]) for f in liste).most_common():
        print(f"  {n:4d}  {statut:9s}  {nature:18s}  {raison}")
    print("coupes :", sum(len(f["coupes"]) for f in liste))
    return 0


if __name__ == "__main__":
    sys.exit(main())
