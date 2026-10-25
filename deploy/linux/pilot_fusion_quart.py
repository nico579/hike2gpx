#!/usr/bin/env python3
"""Fabrique une maille témoin OSM + BD TOPO depuis les sources locales."""
from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path

from hike2gpx import brouter, franchissements as fr, fusion, geofabrik, providers
from nico579_commons import atomique

from rd5_quarts import decouper


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_osm", type=Path)
    parser.add_argument("source_locale", type=Path)
    parser.add_argument("dossier", type=Path)
    parser.add_argument("installation", type=Path)
    parser.add_argument("sud", type=float)
    parser.add_argument("ouest", type=float)
    parser.add_argument("--halo", type=float, default=0.05)
    parser.add_argument("--source", default="ign", choices=sorted(providers.SOURCES))
    args = parser.parse_args()
    nord, est = args.sud + 0.25, args.ouest + 0.25
    if args.dossier.exists() or not args.base_osm.is_file() or not args.source_locale.is_file():
        parser.error("Le dossier doit être neuf et les deux sources locales présentes")
    if shutil.disk_usage(args.dossier.parent).free < 15 * 1024**3:
        parser.error("Moins de 15 Gio libres pour BRouter")
    args.dossier.mkdir()
    debut = time.monotonic()
    extrait = {"base": args.base_osm}
    zone = (args.sud - args.halo, args.ouest - args.halo,
            nord + args.halo, est + args.halo)
    reseau = fusion.Reseau()
    tuiles = fr.tuiles_zone(*zone)
    for numero, (i, j) in enumerate(tuiles, 1):
        reseau.ajouter_osm(geofabrik.elements_tuile(extrait, i, j))
        if numero % 10 == 0:
            print(f"OSM : {numero}/{len(tuiles)} tuiles de 0,05°", flush=True)
    fournisseur = providers.source(args.source)
    troncons = fournisseur.troncons_pour_job(zone, args.dossier, args.source_locale)
    ajoutes = reseau.ajouter_ign(troncons, source=args.source)
    print(f"Fusion : {len(reseau.voies)} voies OSM, {len(troncons)} tronçons {fournisseur.nom}, "
          f"{ajoutes} chemins {fournisseur.nom} ajoutés", flush=True)
    liste = [f for f in fr.analyser(reseau.elements())
             if args.sud <= f["lat"] < nord and args.ouest <= f["lon"] < est]
    atomique.ecrire_json(args.dossier / "franchissements.json", liste, indent=None)
    pbf = args.dossier / "fusion.osm.pbf"
    reseau.ecrire_pbf(pbf)
    del reseau
    inst = brouter.Installation(args.installation)
    inst.preparer_maison()
    segments = brouter.fabriquer_tuiles(inst, pbf, args.dossier / "construction")
    pbf.unlink(missing_ok=True)
    nom = brouter.nom_segment(args.sud, args.ouest) + ".rd5"
    resultat = decouper(segments / nom, args.dossier / "fragments")
    print(f"RD5 {nom} : {(segments / nom).stat().st_size} octets ; "
          f"{sum(bool(f['nom']) for f in resultat['fragments'])} quarts non vides ; "
          f"{len(liste)} franchissements ; {(time.monotonic() - debut) / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
