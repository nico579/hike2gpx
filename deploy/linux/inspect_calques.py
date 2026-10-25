#!/usr/bin/env python3
"""Mesure le contenu d'une maille de calques publiée."""
from __future__ import annotations

import argparse
import collections
import gzip
import json
from pathlib import Path

from hike2gpx import mailles


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dossier", type=Path)
    parser.add_argument("source")
    parser.add_argument("i", type=int)
    parser.add_argument("j", type=int)
    args = parser.parse_args()
    fichier = mailles.chemin(args.dossier, args.source, args.i, args.j)
    with gzip.open(fichier, "rb") as entree:
        contenu = json.load(entree)
    print(f"{fichier.name} : {fichier.stat().st_size} octets gzip")
    for cle in ("osm", "officiels", "franchissements"):
        groupe = contenu[cle]
        if isinstance(groupe, dict):
            for sous, liste in groupe.items():
                print(f"  {sous}: {len(liste)} objets, {len(json.dumps(liste).encode())} octets JSON")
                print("   ", collections.Counter(v.get("genre", v.get("nature")) for v in liste).most_common(15))
        else:
            print(f"  {cle}: {len(groupe)} objets, {len(json.dumps(groupe).encode())} octets JSON")
            print("   ", collections.Counter(v.get("nature", v.get("statut")) for v in groupe).most_common(15))


if __name__ == "__main__":
    main()
