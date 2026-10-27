"""Ligne de commande : hike2gpx [serve | installer | analyser | bundles]."""
from __future__ import annotations

import argparse
import collections
import re
import sys
from pathlib import Path

from nico579_commons import environnement
from nico579_commons.dossiers import Dossiers

from . import __version__, brouter, franchissements, providers

DOSSIERS = Dossiers("hike2gpx", variable_home="HIKE2GPX_HOME")


def main(argv=None) -> int:
    # Figé sous Linux, rend aux programmes lancés (Java, navigateur) le
    # LD_LIBRARY_PATH du système au lieu des bibliothèques de _internal.
    environnement.retablir_environnement_systeme()
    parser = argparse.ArgumentParser(prog="hike2gpx", description="Tracé de randonnée qui respecte "
                                     "les clôtures, barrières et interdictions d'OpenStreetMap.")
    parser.add_argument("--version", action="version", version=f"hike2gpx {__version__}")
    parser.add_argument("--self-test-version", metavar="VERSION", help=argparse.SUPPRESS)
    sous = parser.add_subparsers(dest="commande")
    serve = sous.add_parser("serve", help="ouvre la page de tracé (par défaut)")
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--sans-navigateur", action="store_true", help="ne pas ouvrir le navigateur")
    serve.add_argument("--sans-icone", action="store_true", help="pas d'icône dans la zone de notification")
    installer = sous.add_parser("installer", help="installe BRouter et des tuiles de données (E5_N40...)")
    installer.add_argument("segments", nargs="*", help="tuiles BRouter à télécharger")
    analyser = sous.add_parser("analyser", help="compte les franchissements d'une zone")
    for nom in ("sud", "ouest", "nord", "est"):
        analyser.add_argument(nom, type=float)
    # Les lots hors ligne en série, sur un serveur : la fabrication même de la
    # page (fabrication.py), options en anglais (Nico, 2026-10-27).
    bundles = sous.add_parser("bundles", help="build offline bundles of BRouter cells, one after the other",
                              description="Build the offline bundle of each BRouter cell into OUTPUT/CELL, "
                                          "the same way the page does. Up-to-date bundles are skipped, a "
                                          "failing cell does not stop the next ones (exit code 1).")
    bundles.add_argument("cells", nargs="+", help="BRouter cells, e.g. E5_N40 E5_N45")
    bundles.add_argument("--output", type=Path, required=True, help="directory receiving one bundle per cell")
    bundles.add_argument("--source", choices=sorted(providers.SOURCES),
                         help="national paths provider to merge (enriched bundle); OSM bundle without it")
    bundles.add_argument("--gpkg", type=Path, help="BD TOPO GeoPackage read instead of the WFS (with --source ign)")
    bundles.add_argument("--department", help="with --gpkg: keep this department only, e.g. 83")
    bundles.add_argument("--zone", type=float, nargs=4, metavar=("SOUTH", "WEST", "NORTH", "EAST"),
                         help="limit every cell to this area, e.g. the region covered by --gpkg")
    bundles.add_argument("--force", action="store_true", help="rebuild bundles that are up to date")
    # Import d'un extrait Geofabrik, lancé par geofabrik.installer() dans un
    # processus à part (PBF, base, région en JSON, date des données).
    parser.add_argument("--importer-extrait", nargs=4, metavar="X", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.commande == "bundles":
        for cellule in args.cells:
            if not re.fullmatch(r"[EW]\d{1,3}_[NS]\d{1,2}", cellule):
                parser.error(f"invalid BRouter cell: {cellule}")
        if args.gpkg and args.source != "ign":
            parser.error("--gpkg requires --source ign")
        if args.department and not args.gpkg:
            parser.error("--department requires --gpkg")
    if args.self_test_version:      # avant tout dossier : ne touche pas aux données
        from . import autotest
        return autotest.verifier(args.self_test_version)
    if args.importer_extrait:
        import json

        from . import geofabrik
        pbf, base, region, date = args.importer_extrait
        compte = geofabrik.importer(Path(pbf), Path(base), json.loads(Path(region).read_text(encoding="utf-8")),
                                    date, suivi=lambda c: print("voies", c["voies"], flush=True))
        print("fini", json.dumps(compte), flush=True)
        return 0
    dossier = DOSSIERS.dossier_etat()

    if args.commande == "installer":
        installation = brouter.Installation(dossier)
        installation.installer()
        for nom in args.segments:
            installation.telecharger_segment(nom)
        print(f"BRouter {brouter.VERSION} installé dans {installation.racine}")
        return 0
    if args.commande == "bundles":
        return lots(dossier, args)
    if args.commande == "analyser":
        liste = franchissements.franchissements_zone(args.sud, args.ouest, args.nord, args.est, dossier)
        compte = collections.Counter((f["statut"], f["nature"], f["raison"]) for f in liste)
        print(f"{len(liste)} franchissements")
        for (statut, nature, raison), n in compte.most_common():
            print(f"{n:6d}  {statut:9s}  {nature:18s}  {raison}")
        return 0
    from . import web
    web.servir(dossier, getattr(args, "port", None) or web.PORT, not getattr(args, "sans_navigateur", False),
               icone=not getattr(args, "sans_icone", False))
    return 0


def lots(dossier, args) -> int:
    """hike2gpx bundles : les lots des cases demandées, dans --output."""
    from . import case, fabrication
    installation = brouter.Installation(dossier)
    if not installation.installee():
        installation.installer()
    troncons = edition = None
    if args.gpkg:
        # Seule différence permise avec le PC : la lecture des tronçons, ici le
        # GeoPackage régional par son index RTree, bien plus vite que le WFS.
        def troncons(sud, ouest, nord, est):
            return case.troncons_gpkg(args.gpkg, sud, ouest, nord, est, args.department)
        trouvee = re.search(r"ED(\d{4}-\d{2}-\d{2})", args.gpkg.name)
        edition = trouvee.group(1) if trouvee else args.gpkg.name
    bilan = fabrication.fabriquer_lots(dossier, installation, args.cells, args.output,
                                       zone=tuple(args.zone) if args.zone else None, source=args.source,
                                       troncons=troncons, edition=edition, forcer=args.force,
                                       ecrire=lambda texte: print(texte, flush=True))
    return 1 if any(etat.startswith("erreur") for etat in bilan.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
