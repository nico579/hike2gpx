"""La BDOT10k par powiats, pour fabriquer des cases polonaises sur le serveur.

Le service ArcGIS de Basse-Silésie (providers/bdot10k.py) convient à une vue ;
une case entière en demanderait des milliers de requêtes. Le GUGiK publie la
BDOT10k par powiat (l'équivalent d'un arrondissement), en GeoPackage, avec un
index officiel, sur le modèle de la BD TOPO régionale (bdtopo_regions) :

1. les powiats qui touchent une case, leur code TERYT et leur date de mise à
   jour : une requête à l'index de téléchargement du GUGiK (WFS
   PobieranieBDOT10k, couche BDOT10k_powiaty) ;
2. l'archive zip du powiat (quelques dizaines de Mo), à l'adresse
   …/schemat2021/GPKG/<voïvodie>/<TERYT>_GPKG.zip ;
3. de ses GeoPackage (un par classe d'objets), seul celui des voies piétonnes
   et cyclables (OT_SKRP_L) est gardé, en cache, avec son index RTree ;
4. les sentiers d'une emprise, lus par l'index RTree (en_bloc.lignes_gpkg),
   avec le filtre du lecteur en ligne : rodzaj « ścieżka », en service.

Seule la Basse-Silésie (voïvodie 02) est lue : c'est le périmètre du
fournisseur bdot10k_ds, le seul que lise aussi le service en ligne. Étendre
la lecture à toute la Pologne est une question ouverte (voir la PR).
"""
from __future__ import annotations

import logging
import re
import shutil
import sqlite3
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
VOIVODIES = ("02",)                 # Basse-Silésie : le périmètre de bdot10k_ds
EPSG = 2180
TABLE, GEOMETRIE, CLE = "OT_SKRP_L", "geometria", "id"
DOSSIER = "bdot10k-powiaty"
FILTRE = "t.RODZAJ = 'ścieżka' AND (t.KATEGORIAISTNIENIA IS NULL OR t.KATEGORIAISTNIENIA = 'eksploatowany')"


def _xml(url: str) -> ET.Element:
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=120) as reponse:
        return ET.fromstring(reponse.read())


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


def geopackage(dossier, powiat: dict) -> Path:
    """Les voies piétonnes du powiat à sa date de mise à jour, téléchargées une
    fois et gardées dans dossier/bdot10k-powiaty ; les versions plus anciennes
    du powiat sont effacées."""
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
    téléchargée qu'à la première emprise qui en a besoin."""

    def __init__(self, dossier):
        self.dossier = dossier
        self._powiats = {}          # case (sud, ouest) -> powiats
        self._gpkg = {}             # TERYT -> chemin

    def powiats(self, sud: float, ouest: float, nord: float, est: float) -> list:
        # Le centre de l'emprise : ses bords débordent un peu sur la case voisine.
        case = ((sud + nord) / 2 // 5 * 5, (ouest + est) / 2 // 5 * 5)
        if case not in self._powiats:
            self._powiats[case] = powiats_de_zone(case[0], case[1], case[0] + 5, case[1] + 5)
        return self._powiats[case]

    def date(self, sud: float, ouest: float, nord: float, est: float) -> str | None:
        """L'édition de la BDOT10k pour le manifeste : la mise à jour la plus
        récente des powiats de la case."""
        return max((p["date"] for p in self.powiats(sud, ouest, nord, est)), default=None)

    def __call__(self, sud: float, ouest: float, nord: float, est: float) -> list:
        vus, resultat = set(), []
        for powiat in self.powiats(sud, ouest, nord, est):
            if powiat["teryt"] not in self._gpkg:
                self._gpkg[powiat["teryt"]] = geopackage(self.dossier, powiat)
            # Une voie qui passe la limite de deux powiats peut être dans les deux.
            for (lokalny,), k, pts in en_bloc.lignes_gpkg(self._gpkg[powiat["teryt"]], TABLE, ("LOKALNYID",), EPSG,
                                                           sud, ouest, nord, est, geometrie=GEOMETRIE, cle=CLE,
                                                           filtre=FILTRE):
                identifiant = f"{lokalny}:{k}"
                if identifiant not in vus:
                    vus.add(identifiant)
                    resultat.append({"id": identifiant, "nature": "ścieżka", "pts": pts})
        return resultat
