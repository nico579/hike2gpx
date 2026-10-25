#!/usr/bin/env python3
"""Fabrique une RD5 témoin depuis un PBF déjà borné ; usage SSH administré."""
from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path

from hike2gpx import brouter


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pbf", type=Path)
    parser.add_argument("dossier", type=Path)
    parser.add_argument("installation", type=Path)
    args = parser.parse_args()
    if not args.pbf.is_file():
        parser.error("PBF absent")
    if args.dossier.exists():
        parser.error("Le dossier de travail doit être neuf")
    if shutil.disk_usage(args.dossier.parent).free < 25 * 1024**3:
        parser.error("Moins de 25 Gio libres pour les intermédiaires BRouter")
    inst = brouter.Installation(args.installation)
    inst.preparer_maison()
    debut = time.monotonic()
    segments = brouter.fabriquer_tuiles(inst, args.pbf, args.dossier)
    for rd5 in sorted(segments.glob("*.rd5")):
        print(f"{rd5.name} : {rd5.stat().st_size} octets", flush=True)
    print(f"Durée : {(time.monotonic() - debut) / 60:.1f} min ; "
          f"espace libre : {shutil.disk_usage(args.dossier).free / 1024**3:.1f} Gio", flush=True)


if __name__ == "__main__":
    main()
