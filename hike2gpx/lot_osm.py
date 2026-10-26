"""Le lot OSM d'une case, fabriqué sur le PC, n'importe où dans le monde.

Il ne compile rien : la RD5 est celle que brouter.de publie chaque nuit, et
les calques et franchissements viennent du code du mode en ligne
(franchissements.voies_affichables, franchissements_tuile), tuile de 0,05°
après tuile, sur les extraits Geofabrik installés comme l'application le fait
déjà. Le lot contient donc exactement ce que la page montre en ligne ; il sert
surtout au téléphone, qui n'a ni extrait ni index, et au partage depuis le PC.
"""
from __future__ import annotations

import functools
import gzip
import json
import shutil
from pathlib import Path

import shapely

from . import brouter, franchissements as fr, geofabrik, lot

ATTRIBUTION = "© contributeurs OpenStreetMap (ODbL) ; itinéraires BRouter (brouter.de)"
MARGE_LECTURE = 0.001       # degrés lus autour d'un bloc, plus que la marge d'une tuile du zoom 14


class Abandon(Exception):
    pass


def _tuiles(zone: tuple) -> list:
    """Tuiles de 0,05° qui touchent la zone (sud, ouest, nord, est)."""
    return fr.tuiles_zone(*zone)


def regions_a_installer(dossier, zone: tuple) -> list:
    """Extraits Geofabrik qui couvrent les tuiles de la zone et manquent encore."""
    regions = geofabrik.regions(dossier)
    installes = {r["id"] for r in geofabrik.installes(dossier)}
    besoins = {}
    for i, j in _tuiles(zone):
        if geofabrik.extrait_de_tuile(dossier, i, j):
            continue
        region = geofabrik.region_de_tuile(regions, i, j)
        if region and region["id"] not in installes:
            besoins[region["id"]] = region
    return list(besoins.values())


def fabriquer(dossier, installation: brouter.Installation, case: str, sortie: Path, *, zone: tuple | None = None,
              suivi=None, continuer=None) -> Path:
    """Fabrique le lot OSM de la case dans sortie (vide ou absent) et rend le
    chemin du manifeste. zone : une partie de la case pour les calques et
    franchissements (par défaut la case entière) ; la RD5 couvre toujours la
    case. suivi(etape, faites, total) ; continuer() faux arrête (Abandon)."""
    suivi = suivi or (lambda etape, faites, total: None)
    continuer = continuer or (lambda: True)
    boite = lot.boite_case(case)
    zone = boite if zone is None else (max(zone[0], boite[0]), max(zone[1], boite[1]),
                                       min(zone[2], boite[2]), min(zone[3], boite[3]))
    sortie = Path(sortie)
    sortie.mkdir(parents=True, exist_ok=True)

    suivi("rd5", 0, 1)
    installation.telecharger_segment(case, vers=sortie)
    suivi("rd5", 1, 1)

    manquantes = regions_a_installer(dossier, zone)
    for k, region in enumerate(manquantes):
        if not continuer():
            raise Abandon()
        suivi("extraits", k, len(manquantes))
        geofabrik.installer(dossier, region, continuer=continuer)
    suivi("extraits", len(manquantes), len(manquantes))

    calques = lot.Calques(sortie / "calques.mbtiles", case, boite, ATTRIBUTION)
    tous, dates = {}, set()

    # Deux blocs voisins se partagent les tuiles de leur bord : les dernières
    # lues restent en mémoire, sans garder toute la case.
    @functools.lru_cache(maxsize=256)
    def lire(i, j):
        return fr.voies_affichables(*fr.bornes_tuile(i, j), dossier), fr.franchissements_tuile(i, j, dossier)
    blocs = lot.blocs(*zone)
    for k, (x10, y10) in enumerate(blocs):
        if not continuer():
            raise Abandon()
        suivi("calques", k, len(blocs))
        o, s, e, n = lot.bornes_tuile(lot.ZOOM_BLOC, x10, y10)
        lecture = (max(s, zone[0]) - MARGE_LECTURE, max(o, zone[1]) - MARGE_LECTURE,
                   min(n, zone[2]) + MARGE_LECTURE, min(e, zone[3]) + MARGE_LECTURE)
        couches = {"voies": [], "barrieres": [], "franchissements": []}
        for i, j in _tuiles(lecture):
            extrait = geofabrik.extrait_de_tuile(dossier, i, j)
            if extrait is None:         # mer, ou région sans extrait : rien à lire sans réseau
                continue
            dates.add(extrait.get("date"))
            v, franchissements_tuile = lire(i, j)
            couches["voies"] += [(shapely.LineString([(lo, la) for la, lo in x["pts"]]),
                                  {"id": x["id"], "genre": x["genre"]}) for x in v["voies"] if len(x["pts"]) > 1]
            couches["barrieres"] += [(shapely.LineString([(lo, la) for la, lo in x["pts"]]),
                                      {"id": x["id"], "nature": x["nature"]}) for x in v["barrieres"]
                                     if len(x["pts"]) > 1]
            for f in franchissements_tuile:
                tous[f["cle"]] = f
                if f["statut"] in ("blocked", "uncertain"):
                    couches["franchissements"].append(
                        (shapely.Point(f["lon"], f["lat"]),
                         {c: f.get(c) for c in ("cle", "statut", "raison", "nature", "osm")}))
        calques.ajouter_bloc(x10, y10, couches)
    suivi("calques", len(blocs), len(blocs))
    calques.fermer()

    with gzip.open(sortie / "franchissements.json.gz", "wt", encoding="utf-8") as f:
        json.dump(list(tous.values()), f, ensure_ascii=False)
    return lot.ecrire_manifeste(
        sortie, case, [sortie / f"{case}.rd5", sortie / "franchissements.json.gz", sortie / "calques.mbtiles"],
        {"osm": max((d for d in dates if d), default=None), "rd5": "brouter.de"},
        type="osm", zone=list(zone), attribution=ATTRIBUTION)


def nettoyer(sortie: Path) -> None:
    shutil.rmtree(sortie, ignore_errors=True)
