#!/usr/bin/env python3
"""Indexe un PBF déjà borné pour relire ses mailles OSM sans réseau."""
from __future__ import annotations

import argparse
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from hike2gpx import geofabrik


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pbf", type=Path)
    parser.add_argument("base", type=Path)
    parser.add_argument("sud", type=float)
    parser.add_argument("ouest", type=float)
    parser.add_argument("nord", type=float)
    parser.add_argument("est", type=float)
    args = parser.parse_args()
    if not args.pbf.is_file() or not args.sud < args.nord or not args.ouest < args.est:
        parser.error("PBF ou emprise invalide")
    if args.base.exists() or args.base.with_suffix(".sqlite.part").exists():
        parser.error("La base cible doit être neuve")
    if shutil.disk_usage(args.base.parent).free < 20 * 1024**3:
        parser.error("Moins de 20 Gio libres pour l'index temporaire")
    contour = [(args.ouest, args.sud), (args.est, args.sud),
               (args.est, args.nord), (args.ouest, args.nord),
               (args.ouest, args.sud)]
    region = {"id": args.base.stem, "nom": args.base.stem,
              "pbf": args.pbf.resolve().as_uri(),
              "bornes": [args.sud, args.ouest, args.nord, args.est],
              "polygones": [[contour]]}
    part = args.base.with_name(args.base.name + ".part")
    dernier = 0

    def suivi(compte):
        nonlocal dernier
        if compte["voies"] >= dernier + 100_000:
            dernier = compte["voies"]
            print(f"{dernier} voies ; {shutil.disk_usage(args.base.parent).free / 1024**3:.1f} Gio libres",
                  flush=True)

    debut = time.monotonic()
    compte = geofabrik.importer(args.pbf, part, region,
                                datetime.now(timezone.utc).isoformat(), suivi=suivi)
    stockage = geofabrik.stockage_des_noeuds(part)
    stockage.unlink(missing_ok=True)
    os.replace(part, args.base)
    print(f"Index : {args.base.stat().st_size / 1024**3:.2f} Gio, {compte} ; "
          f"durée {(time.monotonic() - debut) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
