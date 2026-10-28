"""Le lot d'une case, fabriqué n'importe où dans le monde : la seule fabrication,
appelée par la page (GUI) comme par la ligne de commande (CLI, hike2gpx bundles).

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
import logging
import shutil
import time
from pathlib import Path

import shapely

from . import brouter, case as cases, franchissements as fr, geofabrik, lot, providers, relief

journal = logging.getLogger(__name__)
ATTRIBUTION = "© contributeurs OpenStreetMap (ODbL) ; itinéraires BRouter (brouter.de)"
MARGE_LECTURE = 0.001       # degrés lus autour d'un bloc, plus que la marge d'une tuile du zoom 14
BORD_DEG = 1e-6             # rogné au nord et à l'est d'une tuile pour ne pas lire ses voisines
# Mémoire de Java pour compiler : 1 Go suffit à une vue, une case de 5° dense
# en demande quatre ou cinq.
TAS_CASE, AIRE_VUE = "4500m", 1.0       # au-delà d'1 degré carré, le tas d'une case


class Abandon(Exception):
    pass


def _tuiles(zone: tuple) -> list:
    """Tuiles de 0,05° qui touchent la zone (sud, ouest, nord, est)."""
    return fr.tuiles_zone(*zone)


def regions_a_installer(dossier, zone: tuple) -> list:
    """Extraits Geofabrik qui couvrent les tuiles de la zone et manquent encore,
    parmi les seules régions sans sous-régions : une tuile en mer ne réclame
    plus la France, l'Italie ni l'Europe."""
    regions = geofabrik.feuilles(geofabrik.regions_attendues(dossier))
    installes = {r["id"] for r in geofabrik.installes(dossier)}
    besoins = {}
    for i, j in _tuiles(zone):
        if geofabrik.extraits_de_tuile(dossier, i, j):
            continue
        # Une tuile frontalière demande les deux régions voisines, pas le
        # grand extrait qui les contient (geofabrik.regions_de_tuile).
        for region in geofabrik.regions_de_tuile(regions, i, j):
            if region["id"] not in installes:
                besoins[region["id"]] = region
    return list(besoins.values())


def troncons_du_fournisseur(source: str, dossier):
    """Lecture des tronçons officiels d'une emprise par le service national, tuile
    par tuile avec son cache, comme pour le calque de la page."""
    module = providers.source(source).module
    return lambda sud, ouest, nord, est: module.troncons_zone(sud, ouest, nord, est, dossier)


def couvertures(dossier) -> dict:
    """Ce que couvre chaque fournisseur national : le contour de son pays dans
    l'index Geofabrik (PAYS_CARTES), réduit à sa borne s'il est régional."""
    pays = {code: nom for nom, code in providers.PAYS_CARTES.items()}
    regions = {r["id"]: r for r in geofabrik.regions_attendues(dossier)}
    resultat = {}
    for cle, fournisseur in providers.SOURCES.items():
        region = regions.get(pays.get(fournisseur.pays))
        if region is None:
            continue
        contour = shapely.MultiPolygon([shapely.Polygon(p[0], p[1:]) for p in region["polygones"]])
        if fournisseur.borne:
            s, o, n, e = fournisseur.borne
            contour = contour.intersection(shapely.box(o, s, e, n))
        resultat[cle] = contour
    return resultat


def fournisseurs_de_zone(dossier, zone: tuple) -> list:
    """Les fournisseurs nationaux qui touchent la zone (sud, ouest, nord, est) :
    une case frontalière en a plusieurs. Règle de Nico : s'il en existe un, il
    entre au lot."""
    boite = shapely.box(zone[1], zone[0], zone[3], zone[2])
    return [cle for cle, contour in couvertures(dossier).items() if contour.intersects(boite)]


def nom_case(sud: int, ouest: int) -> str:
    """Le nom BRouter de la case de 5° dont le coin sud-ouest est donné (E5_N40)."""
    return f"{'W' if ouest < 0 else 'E'}{abs(ouest)}_{'S' if sud < 0 else 'N'}{abs(sud)}"


def cases_des_fournisseurs(dossier, fournisseurs=None) -> list:
    """Les cases de 5° que touche le pays d'au moins un de ces fournisseurs (tous
    par défaut) : la liste que le serveur fabrique, tirée des contours, jamais
    écrite à la main. Un fournisseur ajouté entre ainsi de lui-même au serveur."""
    cases = set()
    for cle, contour in couvertures(dossier).items():
        if fournisseurs is not None and cle not in fournisseurs or contour.is_empty:
            continue
        o, s, e, n = contour.bounds
        for sud in range(int(s // 5 * 5), int(n // 5 * 5) + 5, 5):
            for ouest in range(int(o // 5 * 5), int(e // 5 * 5) + 5, 5):
                if contour.intersects(shapely.box(ouest, sud, ouest + 5, sud + 5)):
                    cases.add(nom_case(sud, ouest))
    return sorted(cases)


# Fournisseurs qui savent lire une case entière en bloc (archives, GeoPackage
# national…) plutôt que tuile par tuile : seuls ceux-là sont fabriqués en case
# entière sur le serveur (essais du 2026-10-27 : par le WFS, 3 h de fusion).
EN_BLOC = ("ign",)


def lecteurs_en_bloc(dossier) -> tuple:
    """({fournisseur: lecture(sud, ouest, nord, est)}, {fournisseur: édition(…)})
    des lecteurs en bloc, pour fabriquer(troncons=…, editions=…)."""
    from . import bdtopo_regions
    ign = bdtopo_regions.Lecteur(dossier)
    return {"ign": ign}, {"ign": ign.date}


def _lecteur(dossier, fournisseurs: list, troncons: dict):
    """Lecture commune des tronçons de plusieurs fournisseurs : chacun n'est
    interrogé que sur son pays, et chaque tronçon porte sa source."""
    contours = couvertures(dossier)
    lecteurs = {s: troncons.get(s) or troncons_du_fournisseur(s, dossier) for s in fournisseurs}

    def lire(sud, ouest, nord, est):
        boite = shapely.box(ouest, sud, est, nord)
        troncons_lus = [{**t, "source": s} for s, lecteur in lecteurs.items()
                        if s not in contours or contours[s].intersects(boite)
                        for t in lecteur(sud, ouest, nord, est)]
        lire.apportes.update(t["source"] for t in troncons_lus)
        return troncons_lus
    # Les fournisseurs qui ont rendu au moins un tronçon : un contour de pays
    # déborde en mer (la France au-dessus du Cotentin touche W5_N50, anglaise).
    lire.apportes = set()
    return lire


def fabriquer(dossier, installation: brouter.Installation, case: str, sortie: Path, *, zone: tuple | None = None,
              fournisseurs: list | None = None, troncons: dict | None = None, editions: dict | None = None,
              suivi=None, continuer=None) -> Path:
    """Fabrique le lot de la case dans sortie (vide ou absent) et rend le chemin
    du manifeste. zone : une partie de la case (par défaut la case entière).
    fournisseurs : les fournisseurs nationaux à fusionner, par défaut tous
    ceux qui touchent la zone ; aucun, c'est un lot OSM. troncons : {source:
    lecture(sud, ouest, nord, est)} pour remplacer celle du service (le
    GeoPackage du serveur), editions : {source: édition} pour le manifeste.
    suivi(etape, faites, total) ; continuer() faux arrête (Abandon)."""
    suivi = suivi or (lambda etape, faites, total: None)
    continuer = continuer or (lambda: True)
    boite = lot.boite_case(case)
    zone = boite if zone is None else (max(zone[0], boite[0]), max(zone[1], boite[1]),
                                       min(zone[2], boite[2]), min(zone[3], boite[3]))
    sortie = Path(sortie)
    sortie.mkdir(parents=True, exist_ok=True)
    if fournisseurs is None:
        fournisseurs = fournisseurs_de_zone(dossier, zone)
    editions = editions or {}

    if not fournisseurs:
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
        except geofabrik.ExtraitEcarte as exc:
            # Une région transversale sans sous-régions (les Alpes, 2,2 Go) peut
            # encore être trop grosse : ses tuiles, en mer, restent sans données.
            # Le message de l'exception parle d'Overpass, qui ne sert pas aux lots.
            journal.warning("Lot %s : extrait %s écarté (%s), ses tuiles restent vides", case, region["id"],
                            str(exc).split(",")[0])
    suivi("extraits", len(manquantes), len(manquantes))

    if not fournisseurs:
        tous, dates = _calques(dossier, case, boite, zone, sortie, ATTRIBUTION, suivi, continuer)
        franchissements = list(tous.values())
        sources, autres = {"osm": max((d for d in dates if d), default=None), "rd5": "brouter.de"}, \
            {"type": "osm", "zone": list(zone), "attribution": ATTRIBUTION}
    else:
        lire = _lecteur(dossier, fournisseurs, troncons or {})
        noms = ", ".join(providers.source(s).nom for s in fournisseurs)
        attribution = (f"© contributeurs OpenStreetMap (ODbL) ; chemins {noms} ; "
                       f"{relief.ATTRIBUTION} ; itinéraires BRouter")
        franchissements, dates = _enrichir(dossier, installation, case, boite, zone, sortie, fournisseurs[0], lire,
                                           suivi, continuer)
        _calques(dossier, case, boite, zone, sortie, attribution, suivi, continuer,
                 franchissements=franchissements, troncons=lire)
        # Le manifeste ne déclare que les fournisseurs qui ont réellement apporté
        # des tronçons ; les demandés restent notés, pour savoir si le lot est à jour.
        apportes = [s for s in fournisseurs if s in lire.apportes]
        if apportes != list(fournisseurs):
            noms = ", ".join(providers.source(s).nom for s in apportes) or "aucun"
            attribution = (f"© contributeurs OpenStreetMap (ODbL) ; chemins {noms} ; "
                           f"{relief.ATTRIBUTION} ; itinéraires BRouter")
        sources = {"osm": max((d for d in dates if d), default=None),
                   **{providers.source(s).calque: editions.get(s) or time.strftime("%Y-%m-%d") for s in apportes},
                   "relief": "Mapterhorn, zoom 12"}
        autres = {"type": "enrichi", "fournisseurs": apportes, "fournisseurs_demandes": list(fournisseurs),
                  "zone": list(zone), "emprise_enrichie": list(zone), "attribution": attribution}

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
            extraits = geofabrik.extraits_de_tuile(dossier, i, j)
            if extraits:
                dates.update(e.get("date") for e in extraits)
                stock.ajouter(geofabrik.elements_des_extraits(extraits, i, j))
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
                    extraits = geofabrik.extraits_de_tuile(dossier, i, j)
                    if extraits:
                        elements += geofabrik.elements_des_extraits(extraits, i, j)
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
    # Le relief d'une case entière ne change jamais : gardé (et publié par le
    # serveur) une fois pour toutes ; une vue garde son relief partiel.
    bef_garde = relief.fichier_bef(dossier, boite) if tuple(zone) == tuple(boite) else None
    if bef_garde is not None and bef_garde.is_file():
        bef = bef_garde.parent
    else:
        try:
            bef = relief.fabriquer(installation, boite, travail / "relief", relief.cache(dossier),
                                   zone=zone, suivi=suivi_relief, continuer=continuer)
        except relief.Abandon as exc:
            raise Abandon() from exc
        if bef_garde is not None:
            bef_garde.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bef / bef_garde.name, bef_garde)
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
        # Les bords nord et est d'une tuile sont ceux de ses voisines : rognés,
        # pour ne lire qu'elle. Sinon chaque tuile en lisait quatre, et une
        # voisine en mer partait vers Overpass (essai GitHub Actions, HTTP 502).
        # en_ligne=False : un lot ne lit que les extraits, jamais Overpass, trop
        # instable pour une fabrication en série (Nico, 2026-10-27).
        sud, ouest, nord, est = fr.bornes_tuile(i, j)
        return (fr.voies_affichables(sud, ouest, nord - BORD_DEG, est - BORD_DEG, dossier, en_ligne=False),
                fr.franchissements_tuile(i, j, dossier, en_ligne=False) if franchissements is None else [])
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
                extraits = geofabrik.extraits_de_tuile(dossier, i, j)
                if not extraits:            # mer, ou région sans extrait : rien à lire sans réseau
                    continue
                dates.update(e.get("date") for e in extraits)
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
                for t in troncons(*lecture):
                    if (t["source"], t["id"]) not in vus and len(t["pts"]) > 1:
                        vus.add((t["source"], t["id"]))
                        # Une couche par fournisseur : le calque IGN ne montre pas les chemins suisses.
                        couche = lot.couche_officielle(providers.source(t["source"]).calque)
                        couches.setdefault(couche, []).append(
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


# ------------------------------------------------------------------ par lots (serveur)

def date_osm(dossier, zone: tuple) -> str | None:
    """L'édition la plus récente des extraits installés qui couvrent la zone."""
    dates = {e.get("date") for i, j in _tuiles(zone) for e in geofabrik.extraits_de_tuile(dossier, i, j)}
    return max((d for d in dates if d), default=None)


def renouveler_extraits(dossier, zone: tuple) -> list:
    """Réinstalle les extraits de la zone plus vieux que le délai de
    renouvellement des réglages ; rend leurs identifiants."""
    limite = geofabrik.jours_renouvellement(dossier) * 86400
    vieux = {}
    for i, j in _tuiles(zone):
        for extrait in geofabrik.extraits_de_tuile(dossier, i, j):
            if geofabrik.age_s(extrait) > limite:
                vieux[extrait["id"]] = extrait
    for extrait in vieux.values():
        geofabrik.installer(dossier, extrait)
    return list(vieux)


def lot_a_jour(chemin: Path, *, osm: str | None, fournisseurs: list = (), editions: dict | None = None) -> bool:
    """Le lot déjà fabriqué dans chemin suffit-il ? Même format, mêmes
    fournisseurs, données OSM au moins aussi récentes que les extraits, même
    édition des tronçons quand elle est connue (un GeoPackage ; le WFS n'en a pas)."""
    try:
        m = json.loads((Path(chemin) / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    sources = m.get("sources", {})
    demandes = m.get("fournisseurs_demandes", m.get("fournisseurs", []))
    apportes = m.get("fournisseurs", [])
    # Un fournisseur demandé mais sans tronçon (sa case est hors de son pays) n'a
    # pas d'édition au manifeste : seule celle des fournisseurs apportés compte.
    return (m.get("format") == lot.FORMAT and sorted(demandes) == sorted(fournisseurs)
            and osm is not None and (sources.get("osm") or "") >= osm
            and all(sources.get(providers.source(s).calque) == edition for s, edition in (editions or {}).items()
                    if s in apportes))


def _mettre_en_place(travail: Path, cible: Path) -> None:
    """Remplace le lot cible par celui de travail : un lecteur (le téléphone qui
    télécharge) ne voit jamais un lot à moitié écrit."""
    ancien = cible.with_name(f".{cible.name}.ancien")
    shutil.rmtree(ancien, ignore_errors=True)
    if cible.exists():
        cible.replace(ancien)
    travail.replace(cible)
    shutil.rmtree(ancien, ignore_errors=True)


def fabriquer_lots(dossier, installation: brouter.Installation, cases: list, racine: Path, *,
                   zone: tuple | None = None, fournisseurs: list | None = None, troncons: dict | None = None,
                   editions: dict | None = None, forcer: bool = False, ecrire=print) -> dict:
    """Fabrique les lots de plusieurs cases dans racine/CASE, l'une après
    l'autre ; rend {case: "fabriqué" | "à jour" | "hors zone" | "erreur : …"}.
    Un lot à jour est sauté (forcer le refait), une erreur n'arrête pas les
    cases suivantes. zone limite chaque case (le GeoPackage d'une seule région) ;
    fournisseurs, troncons et editions comme pour fabriquer."""
    racine = Path(racine)
    racine.mkdir(parents=True, exist_ok=True)
    bilan = {}
    for case in cases:
        debut = time.monotonic()
        boite = lot.boite_case(case)
        utile = boite if zone is None else (max(zone[0], boite[0]), max(zone[1], boite[1]),
                                            min(zone[2], boite[2]), min(zone[3], boite[3]))
        if utile[0] >= utile[2] or utile[1] >= utile[3]:
            bilan[case] = "hors zone"
            ecrire(f"{case} : hors zone")
            continue
        travail = racine / f".{case}.part"
        try:
            renouveles = renouveler_extraits(dossier, utile)
            if renouveles:
                ecrire(f"{case} : extraits renouvelés {', '.join(renouveles)}")
            de_la_case = fournisseurs_de_zone(dossier, utile) if fournisseurs is None \
                else [s for s in fournisseurs if s in fournisseurs_de_zone(dossier, utile)]
            # Une édition peut dépendre de la case (les régions de la BD TOPO
            # qu'elle touche) : donnée alors comme édition(sud, ouest, nord, est).
            editions_case = {s: e(*utile) if callable(e) else e for s, e in (editions or {}).items()
                             if s in de_la_case}
            if not forcer and lot_a_jour(racine / case, osm=date_osm(dossier, utile), fournisseurs=de_la_case,
                                         editions=editions_case):
                bilan[case] = "à jour"
                ecrire(f"{case} : à jour")
                continue
            nettoyer(travail)
            derniere = [None, 0]        # étape, dixième déjà annoncé

            def suivi(etape, faites, total):
                # Chaque étape, puis chaque dixième d'une longue étape : une fusion
                # de case entière dure près d'une heure.
                dixieme = faites * 10 // total if total else 0
                if etape != derniere[0] or dixieme > derniere[1]:
                    ecrire(f"{case} : {etape} {faites}/{total} ({time.monotonic() - debut:.0f} s)")
                    derniere[:] = [etape, dixieme]
            fabriquer(dossier, installation, case, travail, zone=None if utile == boite else utile,
                      fournisseurs=de_la_case, troncons=troncons, editions=editions_case, suivi=suivi)
            _mettre_en_place(travail, racine / case)
            octets = sum(f.stat().st_size for f in (racine / case).iterdir())
            bilan[case] = "fabriqué"
            ecrire(f"{case} : fabriqué, {octets / 1e6:.1f} Mo en {time.monotonic() - debut:.0f} s")
        except Exception as exc:        # réseau, disque, BRouter : la case suivante part quand même
            bilan[case] = f"erreur : {exc}"
            ecrire(f"{case} : erreur après {time.monotonic() - debut:.0f} s : {exc}")
        finally:
            nettoyer(travail)
    return bilan
