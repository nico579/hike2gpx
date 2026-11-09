"""La BDOT10k par powiats, pour toute la Pologne : les cases du serveur et,
powiat par powiat, le calque de la page (providers/bdot10k.py).

Le GUGiK publie la BDOT10k par powiat (l'équivalent d'un arrondissement), en
GeoPackage, avec un index officiel, sur le modèle de la BD TOPO régionale
(bdtopo_regions) :

1. les powiats qui touchent une case, leur code TERYT et leur date de mise à
   jour : une requête à l'index de téléchargement du GUGiK (WFS
   PobieranieBDOT10k, couche BDOT10k_powiaty) ;
2. l'archive zip du powiat (quelques dizaines de Mo), à l'adresse
   …/schemat2021/GPKG/<voïvodie>/<TERYT>_GPKG.zip ;
3. de ses GeoPackage (un par classe d'objets), seul celui des voies piétonnes
   et cyclables (OT_SKRP_L) est gardé, en cache, avec son index RTree ;
4. les sentiers d'une emprise, lus par l'index RTree (en_bloc.lignes_gpkg),
   avec le filtre du lecteur en ligne : rodzaj « ścieżka », en service.

Jusqu'au 2026-11-09, seule la Basse-Silésie (voïvodie 02) était lue, celle du
service ArcGIS régional dont dépendait le mode en ligne. Les seize voïvodies
le sont désormais (décision de Nico) : une case comme E15_N50 touche 233
powiats, d'où des téléchargements parallèles (FILS).
"""
from __future__ import annotations

import logging
import re
import shutil
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from contextlib import closing
from pathlib import Path

from . import __version__, en_bloc
from .en_bloc import ErreurArchive

journal = logging.getLogger(__name__)
INDEX = "https://mapy.geoportal.gov.pl/wss/service/PZGIK/BDOT/WFS/PobieranieBDOT10k"
TELECHARGEMENT = "https://opendata.geoportal.gov.pl/bdot10k/schemat2021/GPKG/{voivodie}/{teryt}_GPKG.zip"
MS = "{http://mapserver.gis.umn.edu/mapserver}"
AGENT = {"User-Agent": f"hike2gpx/{__version__} (BDOT10k par powiats)"}
VOIVODIES = tuple(f"{v:02d}" for v in range(2, 33, 2))     # les seize, codes TERYT pairs de 02 à 32
INDEX_TTL_S = 6 * 86400             # l'index d'une case, relu au plus tard chaque semaine
FILS = 6                            # powiats téléchargés en même temps (quelques dizaines de Mo chacun)
EPSG = 2180
TABLE, GEOMETRIE, CLE = "OT_SKRP_L", "geometria", "id"
DOSSIER = "bdot10k-powiaty"
FILTRE = "t.RODZAJ = 'ścieżka' AND (t.KATEGORIAISTNIENIA IS NULL OR t.KATEGORIAISTNIENIA = 'eksploatowany')"


def _xml(url: str, essais: int = 4, pause=time.sleep) -> ET.Element:
    """L'index du GUGiK, quatre essais espacés de 10, 20 puis 40 s : il a
    laissé passer une fois le délai de 120 s (essai 42705418372, une part
    des calques d'E20_N45 perdue sur une seule requête)."""
    for essai in range(essais):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=120) as reponse:
                return ET.fromstring(reponse.read())
        except (OSError, ET.ParseError) as exc:
            if essai == essais - 1:
                raise
            journal.info("index BDOT10k : %s, nouvel essai", exc)
            pause(10 * 2 ** essai)


def powiats_de_zone(sud: float, ouest: float, nord: float, est: float, lire=_xml) -> list:
    """[{"teryt", "date", "url"}] des powiats lus (VOIVODIES) qui touchent
    l'emprise, d'après l'index officiel du GUGiK."""
    parametres = {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
                  "TYPENAMES": "ms:BDOT10k_powiaty", "PROPERTYNAME": "TERYT,Data_aktualizacji",
                  "BBOX": f"{sud},{ouest},{nord},{est},urn:ogc:def:crs:EPSG::4326", "COUNT": 1000}
    powiats = {}
    for objet in lire(INDEX + "?" + urllib.parse.urlencode(parametres)).iter(MS + "BDOT10k_powiaty"):
        teryt = (objet.findtext(MS + "TERYT") or "").strip()
        date = (objet.findtext(MS + "Data_aktualizacji") or "")[:10]
        if re.fullmatch(r"\d{4}", teryt) and teryt[:2] in VOIVODIES and re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            powiats[teryt] = {"teryt": teryt, "date": date,
                              "url": TELECHARGEMENT.format(voivodie=teryt[:2], teryt=teryt)}
    return [powiats[t] for t in sorted(powiats)]


def _taille(url: str) -> int:
    demande = urllib.request.Request(url, headers=AGENT, method="HEAD")
    with urllib.request.urlopen(demande, timeout=60) as reponse:
        return int(reponse.headers.get("Content-Length") or 0)


_verrou_global = threading.Lock()
_verrous = {}


def _verrou(teryt: str) -> threading.Lock:
    with _verrou_global:
        return _verrous.setdefault(teryt, threading.Lock())


def geopackage(dossier, powiat: dict) -> Path:
    """Les voies piétonnes du powiat à sa date de mise à jour, téléchargées une
    fois et gardées dans dossier/bdot10k-powiaty ; les versions plus anciennes
    du powiat sont effacées. Un seul téléchargement à la fois par powiat :
    deux vues de la page voisines le demandent parfois ensemble, et deux
    téléchargements dans le même dossier de travail s'écraseraient."""
    with _verrou(powiat["teryt"]):
        return _geopackage(dossier, powiat)


def _geopackage(dossier, powiat: dict) -> Path:
    racine = Path(dossier) / DOSSIER
    base = racine / f"{powiat['teryt']}_{powiat['date']}.sciezki.sqlite"
    if base.is_file():
        return base
    travail = racine / f".{powiat['teryt']}"
    try:
        travail.mkdir(parents=True, exist_ok=True)
        archive = travail / f"{powiat['teryt']}_GPKG.zip"
        fichier = {"url": powiat["url"], "octets": _taille(powiat["url"]), "md5": None}
        journal.info("BDOT10k : téléchargement de %s (%.0f Mo)", archive.name, fichier["octets"] / 1e6)
        en_bloc.telecharger(fichier, archive)
        try:
            with zipfile.ZipFile(archive) as z:
                membres = [m for m in z.infolist() if m.filename.endswith(f"__{TABLE}.gpkg")]
                if not membres:
                    raise ErreurArchive(f"Pas de {TABLE} dans {archive.name}.")
                gpkg = travail / f"{TABLE}.gpkg"
                with z.open(membres[0]) as source, open(gpkg, "wb") as f:
                    shutil.copyfileobj(source, f, en_bloc.BLOC)
        except zipfile.BadZipFile as exc:
            raise ErreurArchive(f"{archive.name} : archive altérée ({exc}).") from exc
        mince = travail / "sciezki.sqlite"
        _garder_les_voies(gpkg, mince)
        mince.replace(base)
    finally:
        shutil.rmtree(travail, ignore_errors=True)
    for ancien in racine.glob(f"{powiat['teryt']}_*.sciezki.sqlite"):
        if ancien != base:
            ancien.unlink()
    return base


def _garder_les_voies(gpkg: Path, cible: Path) -> None:
    """La table des voies piétonnes et cyclables et son index RTree, avec les
    seules colonnes que lisent le filtre et la fusion ; id reste la clé."""
    with closing(sqlite3.connect(str(cible), uri=True)) as base:     # uri : ATTACH en lecture seule
        base.execute("ATTACH DATABASE ? AS complet", (f"file:{gpkg.resolve().as_posix()}?mode=ro",))
        base.execute(f'CREATE TABLE "{TABLE}" ({CLE} INTEGER PRIMARY KEY, LOKALNYID TEXT, RODZAJ TEXT, '
                     f'KATEGORIAISTNIENIA TEXT, {GEOMETRIE} BLOB)')
        base.execute(f'INSERT INTO "{TABLE}" SELECT {CLE}, LOKALNYID, RODZAJ, KATEGORIAISTNIENIA, {GEOMETRIE} '
                     f'FROM complet."{TABLE}"')
        rtree = f"rtree_{TABLE}_{GEOMETRIE}"
        base.execute(f'CREATE VIRTUAL TABLE "{rtree}" USING rtree(id, minx, maxx, miny, maxy)')
        base.execute(f'INSERT INTO "{rtree}" SELECT id, minx, maxx, miny, maxy FROM complet."{rtree}"')
        base.commit()
        base.execute("DETACH DATABASE complet")


class Lecteur:
    """Lecture des sentiers BDOT10k d'une emprise dans les GeoPackage des
    powiats, pour fabrication.fabriquer(troncons={"bdot10k_ds": ...}). Les
    powiats d'une case ne sont cherchés qu'une fois, et chaque archive n'est
    téléchargée qu'à la première emprise qui en a besoin.

    par_case faux, pour la page : les powiats de l'emprise elle-même, et non
    de toute sa case de 5°, pour ne télécharger que ceux de la vue."""

    def __init__(self, dossier, *, par_case: bool = True):
        self.dossier = dossier
        self.par_case = par_case
        self._powiats = {}          # case (sud, ouest), ou emprise -> powiats
        self._gpkg = {}             # TERYT -> chemin
        self._bornes = {}           # TERYT -> (xmin, ymin, xmax, ymax) en EPSG 2180, None si vide

    def powiats(self, sud: float, ouest: float, nord: float, est: float) -> list:
        if not self.par_case:
            emprise = (sud, ouest, nord, est)
            if emprise not in self._powiats:
                self._powiats[emprise] = powiats_de_zone(*emprise)
            return self._powiats[emprise]
        # Le centre de l'emprise : ses bords débordent un peu sur la case voisine.
        case = ((sud + nord) / 2 // 5 * 5, (ouest + est) / 2 // 5 * 5)
        if case not in self._powiats:
            self._powiats[case] = self._index_de_case(*case)
        return self._powiats[case]

    def _index_de_case(self, sud: float, ouest: float) -> list:
        """Les powiats de la case, gardés sur disque INDEX_TTL_S : l'étape
        « données » les écrit dans son artefact, et le calcul, les calques et la
        fin les relisent sans redemander l'index au GUGiK."""
        from nico579_commons import atomique
        chemin = Path(self.dossier) / DOSSIER / f"index_{sud:g}_{ouest:g}.json"
        lu = atomique.lire_json(chemin, None)
        if isinstance(lu, dict) and isinstance(lu.get("powiats"), list) \
                and time.time() - lu.get("lu", 0) < INDEX_TTL_S:
            return lu["powiats"]
        powiats = powiats_de_zone(sud, ouest, sud + 5, ouest + 5)
        atomique.ecrire_json(chemin, {"lu": time.time(), "powiats": powiats})
        return powiats

    def date(self, sud: float, ouest: float, nord: float, est: float) -> str | None:
        """L'édition de la BDOT10k pour le manifeste : la mise à jour la plus
        récente des powiats de la case."""
        return max((p["date"] for p in self.powiats(sud, ouest, nord, est)), default=None)

    def preparer(self, sud: float, ouest: float, nord: float, est: float) -> None:
        """Télécharge d'avance les powiats de l'emprise, sans rien lire, comme
        bdtopo_regions.Lecteur.preparer : l'étape « données » du serveur les
        range dans son artefact, et la fusion en damier (fabrication._lecteur)
        ne s'active que si chaque lecteur de la case sait le faire. Sans elle,
        E10_N50 et E15_N50, tchèques et polonaises, repassaient maille par
        maille. Plusieurs powiats à la fois (FILS) : chacun a son dossier de
        travail, et une case de toute la Pologne en compte jusqu'à 233."""
        from concurrent.futures import ThreadPoolExecutor
        manquants = [p for p in self.powiats(sud, ouest, nord, est) if p["teryt"] not in self._gpkg]
        if manquants:
            with ThreadPoolExecutor(min(FILS, len(manquants))) as groupe:
                for powiat, chemin in zip(manquants, groupe.map(lambda p: geopackage(self.dossier, p), manquants)):
                    self._gpkg[powiat["teryt"]] = chemin

    def _emprise(self, teryt: str):
        """L'emprise des voies du powiat en EPSG 2180, lue une fois à la racine
        de son index RTree ; None si le powiat n'a aucune voie."""
        if teryt not in self._bornes:
            with closing(sqlite3.connect(f"file:{Path(self._gpkg[teryt]).resolve().as_posix()}?mode=ro",
                                         uri=True)) as base:
                xmin, xmax, ymin, ymax = base.execute(
                    f'SELECT MIN(minx), MAX(maxx), MIN(miny), MAX(maxy) FROM "rtree_{TABLE}_{GEOMETRIE}"').fetchone()
            self._bornes[teryt] = None if xmin is None else (xmin, ymin, xmax, ymax)
        return self._bornes[teryt]

    def __call__(self, sud: float, ouest: float, nord: float, est: float) -> list:
        from rasterio.warp import transform_bounds
        vus, resultat = set(), []
        self.preparer(sud, ouest, nord, est)
        # L'emprise en EPSG 2180, un peu élargie : seuls les powiats qu'elle
        # touche sont lus, et non les 233 d'une case à chaque maille.
        x0, y0, x1, y1 = transform_bounds("EPSG:4326", f"EPSG:{EPSG}", ouest, sud, est, nord)
        x0, y0, x1, y1 = x0 - 100, y0 - 100, x1 + 100, y1 + 100
        for powiat in self.powiats(sud, ouest, nord, est):
            bornes = self._emprise(powiat["teryt"])
            if bornes is None or bornes[0] > x1 or bornes[2] < x0 or bornes[1] > y1 or bornes[3] < y0:
                continue
            # Une voie qui passe la limite de deux powiats peut être dans les deux.
            for (lokalny,), k, pts in en_bloc.lignes_gpkg(self._gpkg[powiat["teryt"]], TABLE, ("LOKALNYID",), EPSG,
                                                           sud, ouest, nord, est, geometrie=GEOMETRIE, cle=CLE,
                                                           filtre=FILTRE):
                identifiant = f"{lokalny}:{k}"
                if identifiant not in vus:
                    vus.add(identifiant)
                    resultat.append({"id": identifiant, "nature": "ścieżka", "pts": pts})
        return resultat
