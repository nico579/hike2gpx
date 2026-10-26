#!/usr/bin/env python3
"""Fabrique une case RD5 enrichie par la BD TOPO, maille par maille, et mesure chaque étape.

  fabriquer_case.py DOSSIER INSTALLATION_BROUTER GPKG --osm A.osm.pbf B.osm.pbf ...
      [--case E5_N40] [--emprise SUD OUEST NORD EST] [--departement 83]

1. Découpe chaque extrait OSM à la case (voies entières) et les fusionne.
2. Indexe le PBF de la case (base SQLite par tuiles de 0,05°, comme l'application).
3. Fusionne les mailles de 0,25° de l'emprise avec les tronçons BD TOPO (case.Registre).
4. Écrit le PBF enrichi, puis compile la RD5 de la case, enrichie et OSM seule.
Les mesures vont dans DOSSIER/resultats.json ; les intermédiaires sont effacés.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from hike2gpx import brouter, case, geofabrik

# brouter.py borne Java à 1 Go, assez pour une petite zone mais pas pour une
# case dense ; _JAVA_OPTIONS l'emporte sur la ligne de commande.
TAS_JAVA = "-Xmx4500m"
resultats: dict = {"etapes": {}, "mailles": []}


def journal(texte: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {texte}", flush=True)


def mesurer(nom: str):
    class Chrono:
        def __enter__(self):
            self.debut = time.monotonic()

        def __exit__(self, *exc):
            duree = round(time.monotonic() - self.debut, 1)
            resultats["etapes"][nom] = duree
            journal(f"{nom} : {duree:.0f} s, {shutil.disk_usage(Path.home()).free / 1024**3:.1f} Go libres")
    return Chrono()


def boite_case(nom: str) -> tuple:
    lon = int(nom[1:nom.index("_")]) * (-1 if nom[0] == "W" else 1)
    lat = int(nom[nom.index("_") + 2:]) * (-1 if nom[nom.index("_") + 1] == "S" else 1)
    return lat, lon, lat + 5, lon + 5


def maxid(pbf: Path, genre: str) -> int:
    sortie = subprocess.run(["osmium", "fileinfo", "-e", "-g", f"data.maxid.{genre}", str(pbf)],
                            capture_output=True, text=True, check=True).stdout
    return int(sortie.strip())


def compiler(nom: str, pbf: Path, dossier: Path, inst: brouter.Installation) -> int | None:
    os.environ["_JAVA_OPTIONS"] = TAS_JAVA
    segments = brouter.fabriquer_tuiles(inst, pbf, dossier)
    produits = {f.name: f.stat().st_size for f in segments.glob("*.rd5")}
    journal(f"  RD5 produites : {produits}")
    rd5 = segments / f"{nom}.rd5"
    return rd5.stat().st_size if rd5.exists() else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dossier", type=Path)
    parser.add_argument("installation", type=Path)
    parser.add_argument("gpkg", type=Path)
    parser.add_argument("--osm", type=Path, nargs="+", required=True)
    parser.add_argument("--case", default="E5_N40")
    parser.add_argument("--emprise", type=float, nargs=4, metavar=("SUD", "OUEST", "NORD", "EST"))
    parser.add_argument("--departement")
    args = parser.parse_args()
    sud, ouest, nord, est = boite_case(args.case)
    emprise = args.emprise or (sud, ouest, nord, est)
    args.dossier.mkdir(parents=True, exist_ok=True)
    pbf_case = args.dossier / f"{args.case}.osm.pbf"
    debut = time.monotonic()

    if not pbf_case.exists():
        with mesurer("découpe et fusion OSM"):
            morceaux = []
            for source in args.osm:
                morceau = args.dossier / f"morceau-{source.name}"
                subprocess.run(["osmium", "extract", "-b", f"{ouest},{sud},{est},{nord}", "-s", "complete_ways",
                                "--overwrite", "-o", str(morceau), str(source)], check=True)
                morceaux.append(morceau)
            subprocess.run(["osmium", "merge", "--overwrite", "-o", str(pbf_case), *map(str, morceaux)], check=True)
            for m in morceaux:
                m.unlink()
    resultats["pbf_case_octets"] = pbf_case.stat().st_size

    base = args.dossier / f"{args.case}.sqlite"
    if not base.exists():
        with mesurer("index OSM"):
            subprocess.run([sys.executable, __file__, "--indexer", str(pbf_case), str(base),
                            *map(str, (sud, ouest, nord, est))], check=True)
    extrait = {"base": base}

    registre = case.Registre(maxid(pbf_case, "nodes") + 1, maxid(pbf_case, "ways") + 1)
    with mesurer("fusion des mailles"):
        for m_sud, m_ouest in case.mailles(*emprise):
            t0 = time.monotonic()
            troncons = case.troncons_gpkg(args.gpkg, m_sud, m_ouest, m_sud + case.MAILLE_DEG,
                                          m_ouest + case.MAILLE_DEG, args.departement)
            if not troncons:
                continue
            t1 = time.monotonic()
            elements = case.elements_osm(extrait, m_sud, m_ouest)
            t2 = time.monotonic()
            comptes = registre.fusionner(elements, troncons, m_sud, m_ouest)
            del elements
            comptes.update(maille=[m_sud, m_ouest], lecture_ign_s=round(t1 - t0, 1),
                           lecture_osm_s=round(t2 - t1, 1), fusion_s=round(time.monotonic() - t2, 1))
            resultats["mailles"].append(comptes)
            journal(f"maille {m_sud:.2f} {m_ouest:.2f} : {comptes}")
            (args.dossier / "resultats.json").write_text(json.dumps(resultats, indent=1, ensure_ascii=False))

    pbf_enrichi = args.dossier / f"{args.case}-enrichi.osm.pbf"
    with mesurer("écriture du PBF enrichi"):
        registre.ecrire_pbf(pbf_case, pbf_enrichi)
    resultats["pbf_enrichi_octets"] = pbf_enrichi.stat().st_size
    franchissements = args.dossier / "franchissements.json.gz"
    with gzip.open(franchissements, "wt", encoding="utf-8") as f:
        json.dump(list(registre.franchissements.values()), f, ensure_ascii=False)
    resultats.update(voies_ajoutees=len(registre.voies), noeuds_ajoutes=len(registre.noeuds),
                     voies_osm_raccordees=len(registre.raccords),
                     franchissements=len(registre.franchissements),
                     franchissements_gz_octets=franchissements.stat().st_size)
    base.unlink()

    inst = brouter.Installation(args.installation)
    inst.preparer_maison()
    for nom_etape, pbf, cle in (("compilation RD5 enrichie", pbf_enrichi, "rd5_enrichie_octets"),
                                ("compilation RD5 OSM seule", pbf_case, "rd5_osm_octets")):
        construction = args.dossier / "construction"
        with mesurer(nom_etape):
            resultats[cle] = compiler(args.case, pbf, construction, inst)
        if resultats[cle]:
            nom = "enrichie" if pbf is pbf_enrichi else "osm"
            shutil.move(construction / "segments" / f"{args.case}.rd5", args.dossier / f"{args.case}-{nom}.rd5")
        shutil.rmtree(construction)
        (args.dossier / "resultats.json").write_text(json.dumps(resultats, indent=1, ensure_ascii=False))
    pbf_enrichi.unlink()
    resultats["duree_totale_s"] = round(time.monotonic() - debut, 1)
    (args.dossier / "resultats.json").write_text(json.dumps(resultats, indent=1, ensure_ascii=False))
    journal(f"FIN : {json.dumps({k: v for k, v in resultats.items() if k != 'mailles'}, ensure_ascii=False)}")


def indexer(pbf: str, base: str, sud: str, ouest: str, nord: str, est: str) -> None:
    """Processus à part : pyosmium garde son index de positions jusqu'à la sortie."""
    s, o, n, e = map(float, (sud, ouest, nord, est))
    region = {"id": Path(base).stem, "nom": Path(base).stem, "pbf": Path(pbf).resolve().as_uri(),
              "bornes": [s, o, n, e], "polygones": [[[(o, s), (e, s), (e, n), (o, n), (o, s)]]]}
    part = Path(base).with_name(Path(base).name + ".part")
    geofabrik.importer(Path(pbf), part, region, datetime.now(timezone.utc).isoformat())
    geofabrik.stockage_des_noeuds(part).unlink(missing_ok=True)
    os.replace(part, base)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--indexer":
        indexer(*sys.argv[2:])
    else:
        main()
