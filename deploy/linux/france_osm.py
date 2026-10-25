#!/usr/bin/env python3
"""Mesure la couverture française et prépare l'extrait OSM local sans Overpass massif."""
from __future__ import annotations

import argparse
import os
import shutil
from collections import Counter
from pathlib import Path

from hike2gpx import brouter, franchissements, geofabrik
from shapely.geometry import Polygon, box
from shapely.ops import unary_union


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installer", action="store_true", help="télécharger et indexer l'extrait OSM France")
    parser.add_argument("--dossier", type=Path,
                        default=Path(os.environ.get("HIKE2GPX_HOME", "/var/lib/hike2gpx")))
    args = parser.parse_args(argv)
    region = next((r for r in geofabrik._batir() if r["id"] == "france"), None)
    if region is None:
        parser.error("La région France est absente de l'index Geofabrik.")
    contour = unary_union([Polygon(anneaux[0], anneaux[1:]) for anneaux in region["polygones"]])
    rd5 = brouter.segments_zone(*region["bornes"])
    touchees = []
    for nom in rd5:
        lon0 = int(nom.split("_")[0][1:]) * (-1 if nom.startswith("W") else 1)
        latitude = nom.split("_")[1]
        lat0 = int(latitude[1:]) * (-1 if latitude.startswith("S") else 1)
        if contour.intersection(box(lon0, lat0, lon0 + 5, lat0 + 5)).area > 0:
            touchees.append(nom)
    candidates = franchissements.tuiles_zone(*region["bornes"])
    par_rd5 = Counter()
    for i, j in candidates:
        if geofabrik.contient_tuile(region, i, j):
            sud, ouest, _, _ = franchissements.bornes_tuile(i, j)
            par_rd5[brouter.nom_segment(sud, ouest)] += 1
    couvertes = sum(par_rd5.values())
    print(f"France Geofabrik : {len(touchees)} RD5 touchées ({len(rd5)} dans le rectangle), "
          f"{len(candidates)} tuiles 0,05° dans le rectangle, "
          f"{couvertes} entièrement dans le contour.", flush=True)
    print(f"OSM : {region['pbf']}", flush=True)
    for nom in touchees:
        print(f"  {nom} : {par_rd5[nom]} tuiles entièrement couvertes", flush=True)
    if args.installer:
        args.dossier.mkdir(parents=True, exist_ok=True)
        libres = shutil.disk_usage(args.dossier).free
        if libres < 40 * 1024**3:
            parser.error(f"Moins de 40 Gio libres ({libres / 1024**3:.1f} Gio) : import national refusé.")
        # La limite habituelle de 2 Gio protège les téléchargements automatiques
        # déclenchés par la carte. Ce job administré par SSH porte son plafond
        # explicite dans les métadonnées, y compris pour les renouvellements.
        region["taille_max_octets"] = 10 * 1024**3
        print(f"Espace disponible avant import : {libres / 1024**3:.1f} Gio", flush=True)
        dernier = {"telechargement": -1, "import": -1}

        def progression(phase, valeur):
            palier = int(valeur * 20) if phase == "telechargement" else valeur // 100000
            if palier > dernier[phase]:
                dernier[phase] = palier
                etape = f"{palier * 5} %" if phase == "telechargement" else f"{valeur} voies"
                libres = shutil.disk_usage(args.dossier).free / 1024**3
                print(f"{phase} : {etape}, {libres:.1f} Gio libres", flush=True)

        compte = geofabrik.installer(args.dossier, region, suivi=progression)
        print(f"Extrait France installé : {compte}", flush=True)
        print(f"Espace disponible après import : {shutil.disk_usage(args.dossier).free / 1024**3:.1f} Gio",
              flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
