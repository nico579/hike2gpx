#!/usr/bin/env python3
"""Publie les calques OSM et nationaux d'une maille calculée localement."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from hike2gpx import franchissements as fr, geofabrik, mailles, providers


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_osm", type=Path)
    parser.add_argument("source_locale", type=Path)
    parser.add_argument("franchissements", type=Path)
    parser.add_argument("dossier_public", type=Path)
    parser.add_argument("sud", type=float)
    parser.add_argument("ouest", type=float)
    parser.add_argument("--source", default="ign", choices=sorted(providers.SOURCES))
    args = parser.parse_args()
    if (not args.base_osm.is_file() or not args.source_locale.is_file()
            or not args.franchissements.is_file()):
        parser.error("Source OSM, source nationale ou franchissements absents")
    i, j = round(args.sud * 4), round(args.ouest * 4)
    if abs(i / 4 - args.sud) > 1e-8 or abs(j / 4 - args.ouest) > 1e-8:
        parser.error("La maille doit commencer sur la grille de 0,25°")
    zone = (i / 4, j / 4, (i + 1) / 4, (j + 1) / 4)
    extrait = {"base": args.base_osm}
    vus, elements = set(), []
    for ti, tj in fr.tuiles_zone(*zone):
        for element in geofabrik.elements_tuile(extrait, ti, tj):
            cle = (element.get("type"), element.get("id"))
            if cle not in vus:
                vus.add(cle)
                elements.append(element)
    osm = fr.voies_elements(elements)
    fournisseur = providers.source(args.source)
    officiels = fournisseur.troncons_pour_job(zone, args.dossier_public, args.source_locale)
    franchissements = json.loads(args.franchissements.read_text(encoding="utf-8"))
    if not isinstance(franchissements, list):
        parser.error("Liste de franchissements invalide")
    vide = {"voies": [], "barrieres": []}
    osm_fichier = mailles.publier(args.dossier_public, "osm", i, j, osm=osm,
                                 officiels=[], franchissements=franchissements)
    officiel_fichier = mailles.publier(args.dossier_public, args.source, i, j, osm=vide,
                                      officiels=officiels, franchissements=franchissements)
    print(f"Maille {i}_{j} : {len(osm['voies'])} voies OSM, {len(osm['barrieres'])} barrières, "
          f"{len(officiels)} tronçons {fournisseur.nom}, {len(franchissements)} franchissements")
    print(f"OSM {osm_fichier.stat().st_size} octets ; {fournisseur.nom} "
          f"{officiel_fichier.stat().st_size} octets")


if __name__ == "__main__":
    main()
