#!/usr/bin/env python3
"""Fabrique le lot d'une case sur le serveur, par la fabrication même du PC.

  fabriquer_case.py DONNEES SORTIE [--case E5_N40] [--zone SUD OUEST NORD EST]
      [--source ign] [--gpkg BDT_3-5_GPKG_….gpkg --departement 83]

DONNEES est un dossier de données de hike2gpx : extraits Geofabrik installés
(les manquants s'installent d'eux-mêmes), BRouter dans DONNEES/brouter, cache
des tuiles de relief. Sans --source, le lot OSM ; avec, le lot enrichi.

Le serveur ne diffère du PC que par la lecture des tronçons : --gpkg lit le
GeoPackage régional de la BD TOPO par son index RTree (case.troncons_gpkg),
bien plus vite que le WFS tuile par tuile pour une case entière ; son édition
(…ED2026-09-15…) va au manifeste.
"""
from __future__ import annotations

import argparse
import re
import time
from pathlib import Path

from hike2gpx import brouter, case, fabrication


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("donnees", type=Path)
    parser.add_argument("sortie", type=Path)
    parser.add_argument("--case", default="E5_N40")
    parser.add_argument("--zone", type=float, nargs=4, metavar=("SUD", "OUEST", "NORD", "EST"))
    parser.add_argument("--source", help="fournisseur national inclus au lot (ign, atkis…)")
    parser.add_argument("--gpkg", type=Path, help="GeoPackage BD TOPO régional, au lieu du WFS")
    parser.add_argument("--departement", help="avec --gpkg : ne garder que ce département (83)")
    args = parser.parse_args()
    if args.gpkg and args.source != "ign":
        parser.error("--gpkg ne sert qu'à --source ign")

    troncons = edition = None
    if args.gpkg:
        def troncons(sud, ouest, nord, est):
            return case.troncons_gpkg(args.gpkg, sud, ouest, nord, est, args.departement)
        trouvee = re.search(r"ED(\d{4}-\d{2}-\d{2})", args.gpkg.name)
        edition = trouvee.group(1) if trouvee else args.gpkg.name

    debut, derniere = time.monotonic(), [None]

    def suivi(etape, faites, total):
        if etape != derniere[0] or faites == total or faites % 50 == 0:
            print(f"{time.monotonic() - debut:7.0f} s  {etape} {faites}/{total}", flush=True)
            derniere[0] = etape

    fabrication.nettoyer(args.sortie)
    manifeste = fabrication.fabriquer(args.donnees, brouter.Installation(args.donnees), args.case, args.sortie,
                                      zone=tuple(args.zone) if args.zone else None, source=args.source,
                                      troncons=troncons, edition=edition, suivi=suivi)
    octets = sum(f.stat().st_size for f in args.sortie.iterdir())
    print(f"Lot {args.case} : {args.sortie} ({octets / 1e6:.1f} Mo) en {time.monotonic() - debut:.0f} s, "
          f"manifeste {manifeste.name}", flush=True)


if __name__ == "__main__":
    main()
