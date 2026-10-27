"""Le lot d'une case, fabriqué n'importe où dans le monde : la seule fabrication,
appelée par le PC comme par le serveur (deploy/linux/fabriquer_case.py).

OSM vient toujours des extraits Geofabrik installés, comme l'application le
lit déjà : tuile de 0,05° après tuile, voies entières. Deux lots possibles :

- sans fournisseur national, le lot OSM ne compile rien : la RD5 est celle que
  brouter.de publie chaque nuit, et calques et franchissements viennent du
  code du mode en ligne (franchissements.voies_affichables, franchissements_tuile) ;
- avec un fournisseur national (BD TOPO, ATKIS…), le lot enrichi fusionne ses
  tronçons dans OSM maille par maille (case.Registre), réécrit le PBF de la
  zone depuis un stock sur disque (case.StockOSM), y ajoute le relief
  Mapterhorn (relief.py) et compile la RD5 avec le profil maison.

Le lot contient ainsi ce que la page montre ; il sert au calcul sans réseau
(hors_ligne.py), au téléphone, qui n'a ni extrait ni index, et au partage.
"""
from __future__ import annotations

import functools
import gzip
import json
import shutil
import time
from pathlib import Path

import shapely

from . import brouter, case as cases, franchissements as fr, geofabrik, lot, providers, relief

ATTRIBUTION = "© contributeurs OpenStreetMap (ODbL) ; itinéraires BRouter (brouter.de)"
MARGE_LECTURE = 0.001       # degrés lus autour d'un bloc, plus que la marge d'une tuile du zoom 14
# Mémoire de Java pour compiler : 1 Go suffit à une vue, une case de 5° dense
# en demande quatre ou cinq.
TAS_CASE, AIRE_VUE = "4500m", 1.0       # au-delà d'1 degré carré, le tas d'une case


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


def troncons_du_fournisseur(source: str, dossier):
    """Lecture des tronçons officiels d'une emprise par le service national, tuile
    par tuile avec son cache, comme pour le calque de la page."""
    module = providers.source(source).module
    return lambda sud, ouest, nord, est: module.troncons_zone(sud, ouest, nord, est, dossier)


def fabriquer(dossier, installation: brouter.Installation, case: str, sortie: Path, *, zone: tuple | None = None,
              source: str | None = None, troncons=None, edition: str | None = None,
              suivi=None, continuer=None) -> Path:
    """Fabrique le lot de la case dans sortie (vide ou absent) et rend le chemin
    du manifeste. zone : une partie de la case (par défaut la case entière).
    source : le fournisseur national à inclure (lot enrichi), sinon lot OSM.
    troncons(sud, ouest, nord, est) : autre lecture de ses tronçons (le
    GeoPackage du serveur), edition : leur édition pour le manifeste.
    suivi(etape, faites, total) ; continuer() faux arrête (Abandon)."""
    suivi = suivi or (lambda etape, faites, total: None)
    continuer = continuer or (lambda: True)
    boite = lot.boite_case(case)
    zone = boite if zone is None else (max(zone[0], boite[0]), max(zone[1], boite[1]),
                                       min(zone[2], boite[2]), min(zone[3], boite[3]))
    sortie = Path(sortie)
    sortie.mkdir(parents=True, exist_ok=True)

    if source is None:
        suivi("rd5", 0, 1)
        installation.telecharger_segment(case, vers=sortie)
        suivi("rd5", 1, 1)

    manquantes = regions_a_installer(dossier, zone)
    for k, region in enumerate(manquantes):
        if not continuer():
            raise Abandon()
        suivi("extraits", k, len(manquantes))
        try:
            geofabrik.installer(dossier, region, continuer=continuer)
        except geofabrik.Abandon as exc:    # l'arrêt demandé pendant l'extrait arrête le lot
            raise Abandon() from exc
    suivi("extraits", len(manquantes), len(manquantes))

    if source is None:
        tous, dates = _calques(dossier, case, boite, zone, sortie, ATTRIBUTION, suivi, continuer)
        franchissements = list(tous.values())
        sources, autres = {"osm": max((d for d in dates if d), default=None), "rd5": "brouter.de"}, \
            {"type": "osm", "zone": list(zone), "attribution": ATTRIBUTION}
    else:
        fournisseur = providers.source(source)
        troncons = troncons or troncons_du_fournisseur(source, dossier)
        attribution = (f"© contributeurs OpenStreetMap (ODbL) ; chemins {fournisseur.nom} ; "
                       f"{relief.ATTRIBUTION} ; itinéraires BRouter")
        franchissements, dates = _enrichir(dossier, installation, case, boite, zone, sortie, source, troncons,
                                           suivi, continuer)
        _calques(dossier, case, boite, zone, sortie, attribution, suivi, continuer,
                 franchissements=franchissements, troncons=troncons)
        sources = {"osm": max((d for d in dates if d), default=None),
                   fournisseur.calque: edition or time.strftime("%Y-%m-%d"), "relief": "Mapterhorn, zoom 12"}
        autres = {"type": "enrichi", "source": source, "zone": list(zone), "emprise_enrichie": list(zone),
                  "attribution": attribution}

    with gzip.open(sortie / "franchissements.json.gz", "wt", encoding="utf-8") as f:
        json.dump(franchissements, f, ensure_ascii=False)
    return lot.ecrire_manifeste(
        sortie, case, [sortie / f"{case}.rd5", sortie / "franchissements.json.gz", sortie / "calques.mbtiles"],
        sources, **autres)


def _enrichir(dossier, installation, case, boite, zone, sortie, source, troncons, suivi, continuer):
    """La RD5 enrichie de la zone dans sortie ; rend (franchissements, dates OSM)."""
    travail = sortie / "travail"
    travail.mkdir(exist_ok=True)
    mailles = cases.mailles(*zone)
    # Le PBF couvre les mailles entières : un tronçon ajouté par une maille du
    # bord se raccorde aux voies OSM de toute la maille.
    etendue = (min(s for s, _ in mailles), min(o for _, o in mailles),
               max(s for s, _ in mailles) + cases.MAILLE_DEG, max(o for _, o in mailles) + cases.MAILLE_DEG)
    stock, dates = cases.StockOSM(travail / "osm.sqlite"), set()
    try:
        tuiles = _tuiles(etendue)
        for k, (i, j) in enumerate(tuiles):
            if not continuer():
                raise Abandon()
            suivi("osm", k, len(tuiles))
            extrait = geofabrik.extrait_de_tuile(dossier, i, j)
            if extrait is not None:
                dates.add(extrait.get("date"))
                stock.ajouter(geofabrik.elements_tuile(extrait, i, j))
        noeud, voie = stock.maxima()
        registre = cases.Registre(noeud + 1, voie + 1)

        for k, (m_sud, m_ouest) in enumerate(mailles):
            if not continuer():
                raise Abandon()
            suivi("fusion", k, len(mailles))
            a_fusionner = troncons(m_sud, m_ouest, m_sud + cases.MAILLE_DEG, m_ouest + cases.MAILLE_DEG)
            if a_fusionner:
                elements = []
                for i, j in fr.tuiles_zone(m_sud - cases.HALO_DEG, m_ouest - cases.HALO_DEG,
                                           m_sud + cases.MAILLE_DEG + cases.HALO_DEG,
                                           m_ouest + cases.MAILLE_DEG + cases.HALO_DEG):
                    extrait = geofabrik.extrait_de_tuile(dossier, i, j)
                    if extrait is not None:
                        elements += geofabrik.elements_tuile(extrait, i, j)
                registre.fusionner(elements, a_fusionner, m_sud, m_ouest, source=source)
        suivi("fusion", len(mailles), len(mailles))

        suivi("compilation", 0, 1)
        stock.ecrire_pbf(travail / "osm.osm.pbf")
    finally:
        stock.fermer()
    registre.ecrire_pbf(travail / "osm.osm.pbf", travail / "enrichi.osm.pbf")
    (travail / "osm.osm.pbf").unlink()
    (travail / "osm.sqlite").unlink()

    def suivi_relief(etape, faites, total):
        suivi("relief", faites, total)
    try:
        bef = relief.fabriquer(installation, boite, travail / "relief", relief.cache(dossier),
                               zone=zone, suivi=suivi_relief, continuer=continuer)
    except relief.Abandon as exc:
        raise Abandon() from exc
    suivi("compilation", 0, 1)
    installation.preparer_maison()
    aire = (zone[2] - zone[0]) * (zone[3] - zone[1])
    segments = brouter.fabriquer_tuiles(installation, travail / "enrichi.osm.pbf", travail / "construction",
                                        relief=bef, tas=TAS_CASE if aire > AIRE_VUE else "1g")
    rd5 = segments / f"{case}.rd5"
    if not rd5.is_file():
        raise brouter.ErreurBRouter(f"La compilation n'a pas produit {case}.rd5.")
    shutil.move(rd5, sortie / f"{case}.rd5")
    shutil.rmtree(travail, ignore_errors=True)
    suivi("compilation", 1, 1)
    # Un franchissement d'une maille du bord peut tomber hors de la zone : il
    # reste, BRouter le connaît.
    return list(registre.franchissements.values()), dates


def _calques(dossier, case, boite, zone, sortie, attribution, suivi, continuer, *, franchissements=None,
             troncons=None):
    """Les calques de la zone dans sortie/calques.mbtiles. Voies et barrières
    viennent du code du mode en ligne ; les franchissements de la fusion s'ils
    sont donnés, sinon de l'analyse en ligne ; troncons ajoute la couche des
    chemins officiels. Rend (franchissements de l'analyse en ligne, dates OSM)."""
    calques = lot.Calques(sortie / "calques.mbtiles", case, boite, attribution)
    tous, dates = {}, set()
    a_montrer = None
    if franchissements is not None:
        a_montrer = [(shapely.Point(f["lon"], f["lat"]), {c: f.get(c) for c in ("cle", "statut", "raison", "nature",
                                                                                 "osm")})
                     for f in franchissements if f.get("statut") in ("blocked", "uncertain")]
        arbre = shapely.STRtree([g for g, _ in a_montrer]) if a_montrer else None

    # Deux blocs voisins se partagent les tuiles de leur bord : les dernières
    # lues restent en mémoire, sans garder toute la case.
    @functools.lru_cache(maxsize=256)
    def lire(i, j):
        return (fr.voies_affichables(*fr.bornes_tuile(i, j), dossier),
                fr.franchissements_tuile(i, j, dossier) if franchissements is None else [])
    blocs = lot.blocs(*zone)
    try:
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
                                      {"id": x["id"], "genre": x["genre"]}) for x in v["voies"]
                                     if len(x["pts"]) > 1]
                couches["barrieres"] += [(shapely.LineString([(lo, la) for la, lo in x["pts"]]),
                                          {"id": x["id"], "nature": x["nature"]}) for x in v["barrieres"]
                                         if len(x["pts"]) > 1]
                for f in franchissements_tuile:
                    tous[f["cle"]] = f
                    if f["statut"] in ("blocked", "uncertain"):
                        couches["franchissements"].append(
                            (shapely.Point(f["lon"], f["lat"]),
                             {c: f.get(c) for c in ("cle", "statut", "raison", "nature", "osm")}))
            if a_montrer:
                boite_lecture = shapely.box(lecture[1], lecture[0], lecture[3], lecture[2])
                couches["franchissements"] += [a_montrer[r] for r in arbre.query(boite_lecture)]
            if troncons is not None:
                vus = set()
                couches["troncons"] = []
                for t in troncons(*lecture):
                    if t["id"] not in vus and len(t["pts"]) > 1:
                        vus.add(t["id"])
                        couches["troncons"].append(
                            (shapely.LineString([(lo, la) for la, lo in t["pts"]]),
                             {"id": t["id"], "nature": t.get("nature"), "acces_pieton": t.get("acces_pieton"),
                              "prive": t.get("prive")}))
            calques.ajouter_bloc(x10, y10, couches)
    except BaseException:
        calques.abandonner()        # sous Windows, la base ouverte bloquerait le prochain essai
        raise
    suivi("calques", len(blocs), len(blocs))
    calques.fermer()
    return tous, dates


def nettoyer(sortie: Path) -> None:
    shutil.rmtree(sortie, ignore_errors=True)
