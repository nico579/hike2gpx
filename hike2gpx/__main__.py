"""Ligne de commande : hike2gpx [serve | installer | analyser]."""
from __future__ import annotations

import argparse
import collections
import sys

from nico579_commons.dossiers import Dossiers

from . import __version__, brouter, franchissements

DOSSIERS = Dossiers("hike2gpx", variable_home="HIKE2GPX_HOME")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="hike2gpx", description="Tracé de randonnée qui respecte "
                                     "les clôtures, barrières et interdictions d'OpenStreetMap.")
    parser.add_argument("--version", action="version", version=f"hike2gpx {__version__}")
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
    # Import d'un extrait Geofabrik, lancé par geofabrik.installer() dans un
    # processus à part (PBF, base, région en JSON, date des données).
    parser.add_argument("--importer-extrait", nargs=4, metavar="X", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.importer_extrait:
        import json
        from pathlib import Path

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


if __name__ == "__main__":
    sys.exit(main())
