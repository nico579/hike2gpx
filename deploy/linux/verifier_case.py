#!/usr/bin/env python3
"""Épreuve d'une RD5 enrichie : des itinéraires BRouter qui empruntent des chemins IGN ajoutés.

  verifier_case.py RD5_ENRICHIE RD5_OSM INSTALLATION_BROUTER GPKG SUD OUEST [--departement 83]

Pour des chemins BD TOPO de la maille [SUD, OUEST] (500 m à 2 km), on demande
le trajet entre leurs deux extrémités à deux serveurs BRouter, l'un sur la RD5
enrichie, l'autre sur la RD5 OSM seule, et on lit dans les messages la part de
distance parcourue sur hike2gpx=ign.
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import shutil
import tempfile
from pathlib import Path

from pyproj import Geod
from shapely import LineString

from hike2gpx import brouter, case


def part_ign(trace: dict) -> float:
    messages = trace["properties"]["messages"]
    i_dist, i_tags = messages[0].index("Distance"), messages[0].index("WayTags")
    total = sum(int(m[i_dist]) for m in messages[1:]) or 1
    return sum(int(m[i_dist]) for m in messages[1:] if "hike2gpx=ign" in m[i_tags]) / total


def traverse(trace: dict, coupe) -> bool:
    """Le tracé BRouter coupe-t-il le segment de la coupe ?"""
    points = [c[:2] for c in trace["geometry"]["coordinates"]]
    if len(points) < 2:         # deux points accrochés au même endroit
        return False
    ligne = LineString(points)
    return ligne.intersects(LineString([tuple(p[:2]) for p in coupe]))


def eprouver_franchissements(port: int, franchissements: list, nombre: int) -> dict:
    """Pour des franchissements bloquants : deux points à 25 m de part et
    d'autre de l'obstacle, en travers de la coupe. Le cas compte si le trajet
    direct traverse la coupe ; avec elle (mode strict), le trajet ne doit plus
    la traverser, quitte à devenir impossible. Rend les comptes."""
    comptes = {"respectes": 0, "ignores": 0, "hors_sujet": 0}
    for f in franchissements:
        if sum(comptes.values()) - comptes["hors_sujet"] >= nombre:
            break
        (lo1, la1), (lo2, la2) = f["coupes"][0][:2]
        echelle = math.cos(math.radians(la1))
        dx, dy = (lo2 - lo1) * echelle, la2 - la1
        norme = math.hypot(dx, dy) or 1
        # 25 m de part et d'autre, perpendiculairement à la coupe
        px, py = -dy / norme * 25 / 111195, dx / norme * 25 / 111195
        points = [(f["lat"] - py, f["lon"] - px / echelle), (f["lat"] + py, f["lon"] + px / echelle)]
        try:
            direct = brouter.calculer(port, points)
        except brouter.ErreurBRouter:
            comptes["hors_sujet"] += 1
            continue
        if not any(traverse(direct, c) for c in f["coupes"]):   # les points se sont accrochés ailleurs
            comptes["hors_sujet"] += 1
            continue
        try:
            avec = brouter.calculer(port, points, [f], strict=True)
        except brouter.ErreurBRouter:
            avec = None
        respecte = avec is None or not any(traverse(avec, c) for c in f["coupes"])
        comptes["respectes" if respecte else "ignores"] += 1
        longueur = "impossible" if avec is None else f"{int(avec['properties']['track-length'])} m"
        print(f"  {f['nature'] or f.get('barriere')} : direct {int(direct['properties']['track-length'])} m "
              f"à travers l'obstacle, avec la coupe {longueur} -> {'respecté' if respecte else 'IGNORÉ'}", flush=True)
    return comptes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("enrichie", type=Path)
    parser.add_argument("osm", type=Path)
    parser.add_argument("installation", type=Path)
    parser.add_argument("gpkg", type=Path)
    parser.add_argument("sud", type=float)
    parser.add_argument("ouest", type=float)
    parser.add_argument("--departement")
    parser.add_argument("--nombre", type=int, default=5)
    parser.add_argument("--franchissements", type=Path, help="franchissements.json.gz de la case")
    parser.add_argument("--premiere-voie-ajoutee", type=int, help="au-delà : voies IGN ajoutées")
    args = parser.parse_args()
    nom = args.enrichie.name.split("-")[0].removesuffix(".rd5")
    inst = brouter.Installation(args.installation)
    inst.ecrire_profil_maison()
    geod = Geod(ellps="WGS84")
    with tempfile.TemporaryDirectory() as tmp:
        serveurs = {}
        for cle, rd5 in (("enrichie", args.enrichie), ("osm", args.osm)):
            (Path(tmp) / cle).mkdir()
            shutil.copy2(rd5, Path(tmp) / cle / f"{nom}.rd5")
            serveurs[cle] = brouter.Serveur(inst, segments=Path(tmp) / cle, profils=inst.profils_maison)
            serveurs[cle].demarrer(60)
        try:
            candidats = [t for t in case.troncons_gpkg(args.gpkg, args.sud, args.ouest, args.sud + case.MAILLE_DEG,
                                                       args.ouest + case.MAILLE_DEG, args.departement)
                         if t["nature"] in ("Chemin", "Sentier")
                         and 500 <= geod.line_length([p[1] for p in t["pts"]], [p[0] for p in t["pts"]]) <= 2000]
            print(f"{len(candidats)} chemins IGN de 500 m à 2 km dans la maille", flush=True)
            trouves = 0
            for t in candidats[::max(1, len(candidats) // 40)]:
                points = [tuple(t["pts"][0]), tuple(t["pts"][-1])]
                enrichie = brouter.calculer(serveurs["enrichie"].port, points)
                if part_ign(enrichie) < 0.5:
                    continue
                try:
                    osm = brouter.calculer(serveurs["osm"].port, points)
                    detour = f"{int(osm['properties']['track-length'])} m"
                except brouter.ErreurBRouter as exc:
                    detour = f"échec ({exc})"
                print(f"{t['id']} ({t['nature']}) : RD5 enrichie {int(enrichie['properties']['track-length'])} m "
                      f"dont {part_ign(enrichie):.0%} sur IGN ; RD5 OSM seule {detour}", flush=True)
                trouves += 1
                if trouves == args.nombre:
                    break
            if args.franchissements:
                with gzip.open(args.franchissements, "rt", encoding="utf-8") as f:
                    bloquants = [x for x in json.load(f) if x["statut"] == "blocked" and x.get("coupes")
                                 and args.sud <= x["lat"] < args.sud + case.MAILLE_DEG
                                 and args.ouest <= x["lon"] < args.ouest + case.MAILLE_DEG]
                seuil = args.premiere_voie_ajoutee or float("inf")
                for libelle, groupe in (("chemins IGN ajoutés", [x for x in bloquants if max(x["voies"]) >= seuil]),
                                        ("voies OSM", [x for x in bloquants if max(x["voies"]) < seuil])):
                    print(f"Franchissements bloquants sur des {libelle} : {len(groupe)} dans la maille", flush=True)
                    comptes = eprouver_franchissements(serveurs["enrichie"].port, groupe[::max(1, len(groupe) // 60)],
                                                       args.nombre * 2)
                    print(f"  bilan : {comptes}", flush=True)
                    if comptes["ignores"]:
                        raise SystemExit(f"{comptes['ignores']} franchissements ignorés par BRouter.")
        finally:
            for s in serveurs.values():
                s.arreter()
    if trouves < args.nombre:
        raise SystemExit(f"Seulement {trouves} itinéraires surtout IGN sur {args.nombre} attendus.")


if __name__ == "__main__":
    main()
