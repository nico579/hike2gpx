#!/usr/bin/env python3
"""Mesure un lot BD TOPO local sur la grille de distribution de 0,25°."""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

from hike2gpx.providers import bdtopo


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gpkg", type=Path)
    parser.add_argument("sud", type=float)
    parser.add_argument("ouest", type=float)
    parser.add_argument("nord", type=float)
    parser.add_argument("est", type=float)
    parser.add_argument("sortie", type=Path)
    args = parser.parse_args()
    if not args.sud < args.nord or not args.ouest < args.est:
        parser.error("Emprise invalide")
    troncons = bdtopo.troncons_gpkg(args.gpkg, args.sud, args.ouest, args.nord, args.est)
    contenu = json.dumps({"source": "ign", "emprise": [args.sud, args.ouest, args.nord, args.est],
                          "troncons": troncons}, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    args.sortie.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.sortie, "wb", compresslevel=6) as sortie:
        sortie.write(contenu)
    print(f"{len(troncons)} tronçons, {len(contenu)} octets JSON, "
          f"{args.sortie.stat().st_size} octets gzip : {args.sortie}")


if __name__ == "__main__":
    main()
