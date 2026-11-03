"""ZABAGED en un seul GeoPackage national, pour fabriquer les cases tchèques
sur le serveur.

Le service ArcGIS de l'ČÚZK convient à une vue ; une case entière en
demanderait des milliers de requêtes. L'ČÚZK publie aussi ZABAGED entier, en
GeoPackage, sur le modèle de la BD TOPO régionale (bdtopo_regions) :

1. l'édition courante : le flux ATOM du jeu de données (une archive zip par
   projection ; on prend ETRS89/TM33, EPSG 3045, environ 6,7 Go) ;
2. l'archive, reprise si coupée (vu de GitHub Actions, le serveur débite vers
   1 Mo/s, soit 1 h 45, et coupe parfois), contrôlée par sa taille puis par
   le CRC du zip ;
3. du GeoPackage décompressé, seules les tables des sentiers (Pěšina) et des
   chemins (Cesta) et leurs index RTree sont gardés, dans une petite base, pour
   les cases et les semaines suivantes ;
4. les chemins d'une emprise, lus par l'index RTree (en_bloc.lignes_gpkg).

Mêmes classes que le lecteur en ligne (providers/zabaged.py, couches 82 et 83
du service) : toutes les Pěšina et toutes les Cesta, sans autre filtre.
Licence du flux : « žádné podmínky neplatí » (aucune condition).
"""
from __future__ import annotations

import logging
import re
import shutil
import sqlite3
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from contextlib import closing
from pathlib import Path

from . import __version__, en_bloc
from .en_bloc import ErreurArchive

journal = logging.getLogger(__name__)
FLUX = "https://atom.cuzk.gov.cz/ZABAGED-GPKG/datasetFeeds/CZ-00025712-CUZK_ZABAGED-GPKG_1.xml"
ATOM = "{http://www.w3.org/2005/Atom}"
AGENT = {"User-Agent": f"hike2gpx/{__version__} (ZABAGED national)"}
EPSG = 3045
DOSSIER = "zabaged-national"        # « zabaged » est le cache des tuiles du service en ligne
# Table du GeoPackage -> nature du tronçon, celle du lecteur en ligne. Relevé
# sur l'édition du 2026-10-04 (essai GitHub Actions du 2026-10-28) : 74 514
# sentiers, 1 191 886 chemins, géométrie « Shape » et clé OBJECTID.
COUCHES = {"Pesina": "Pěšina", "Cesta": "Cesta"}
COLONNES = ("fid_zbg",)
GEOMETRIE, CLE = "Shape", "OBJECTID"


def _atom(url: str) -> ET.Element:
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=60) as reponse:
        return ET.fromstring(reponse.read())


def derniere_edition(lire=_atom) -> dict:
    """{"nom", "date", "fichiers": [{"url", "octets", "md5": None}]} de
    l'édition courante en EPSG 3045, d'après le flux du jeu de données."""
    for entree in lire(FLUX).findall(ATOM + "entry"):
        for lien in entree.findall(ATOM + "link"):
            url = lien.get("href", "")
            trouve = re.fullmatch(r"https://[\w.-]+/[\w/.-]*/epsg-3045/(ZABAGED-3045-gpkg-(\d{4})(\d{2})(\d{2}))\.zip",
                                  url)
            if trouve:
                return {"nom": trouve.group(1), "date": "-".join(trouve.group(2, 3, 4)),
                        "fichiers": [{"url": url, "octets": int(lien.get("length", "0")), "md5": None}]}
    raise ErreurArchive("Aucune édition ZABAGED GeoPackage en EPSG 3045 dans le flux de l'ČÚZK.")


def geopackage(dossier, edition: dict | None = None) -> Path:
    """Les sentiers et chemins ZABAGED de l'édition, téléchargés une fois et
    gardés dans dossier/zabaged-national ; les éditions plus anciennes sont
    effacées."""
    edition = edition or derniere_edition()
    racine = Path(dossier) / DOSSIER
    base = racine / f"{edition['nom']}.chemins.sqlite"
    if base.is_file():
        return base
    travail = racine / f".{edition['nom']}"
    try:
        travail.mkdir(parents=True, exist_ok=True)
        fichier = edition["fichiers"][0]
        archive = travail / fichier["url"].rsplit("/", 1)[-1]
        journal.info("ZABAGED : téléchargement de %s (%.0f Mo)", archive.name, fichier["octets"] / 1e6)
        en_bloc.telecharger(fichier, archive, essais=8)
        gpkg = _extraire(archive, travail / "extrait")
        archive.unlink()                # de la place pour la réduction
        mince = travail / "chemins.sqlite"
        _garder_les_chemins(gpkg, mince)
        mince.replace(base)
    finally:
        shutil.rmtree(travail, ignore_errors=True)
    for ancien in racine.glob("ZABAGED-*.chemins.sqlite"):
        if ancien != base:
            ancien.unlink()
    return base


def _extraire(archive: Path, dossier: Path) -> Path:
    """Le GeoPackage de l'archive (le plus gros s'il y en a plusieurs),
    décompressé dans dossier ; zipfile contrôle le CRC en lisant."""
    try:
        with zipfile.ZipFile(archive) as z:
            membres = [m for m in z.infolist() if m.filename.lower().endswith(".gpkg")]
            if not membres:
                raise ErreurArchive(f"Pas de GeoPackage dans {archive.name}.")
            membre = max(membres, key=lambda m: m.file_size)
            dossier.mkdir(parents=True, exist_ok=True)
            cible = dossier / Path(membre.filename).name
            journal.info("ZABAGED : décompression de %s (%.0f Mo)", cible.name, membre.file_size / 1e6)
            with z.open(membre) as source, open(cible, "wb") as f:
                shutil.copyfileobj(source, f, en_bloc.BLOC)
    except zipfile.BadZipFile as exc:
        raise ErreurArchive(f"{archive.name} : archive altérée ({exc}).") from exc
    return cible


def _garder_les_chemins(gpkg: Path, cible: Path) -> None:
    """Les tables des sentiers et des chemins et leurs index RTree, copiées du
    GeoPackage national dans une base à part, avec la seule colonne que lit la
    fusion. OBJECTID reste la clé primaire, que l'index RTree renvoie."""
    with closing(sqlite3.connect(str(cible), uri=True)) as base:     # uri : ATTACH en lecture seule
        base.execute("ATTACH DATABASE ? AS complet", (f"file:{gpkg.resolve().as_posix()}?mode=ro",))
        for table in COUCHES:
            base.execute(f'CREATE TABLE "{table}" ({CLE} INTEGER PRIMARY KEY, fid_zbg TEXT, {GEOMETRIE} BLOB)')
            base.execute(f'INSERT INTO "{table}" SELECT {CLE}, fid_zbg, {GEOMETRIE} FROM complet."{table}"')
            rtree = f"rtree_{table}_{GEOMETRIE}"
            base.execute(f'CREATE VIRTUAL TABLE "{rtree}" USING rtree(id, minx, maxx, miny, maxy)')
            base.execute(f'INSERT INTO "{rtree}" SELECT id, minx, maxx, miny, maxy FROM complet."{rtree}"')
        base.commit()
        base.execute("DETACH DATABASE complet")


class Lecteur:
    """Lecture des chemins ZABAGED d'une emprise dans le GeoPackage national,
    pour fabrication.fabriquer(troncons={"zabaged": ...}). L'archive n'est
    téléchargée qu'à la première emprise qui en a besoin."""

    def __init__(self, dossier):
        self.dossier = dossier
        self._edition = None
        self._base = None

    def edition(self) -> dict:
        if self._edition is None:
            self._edition = derniere_edition()
        return self._edition

    def date(self, sud: float, ouest: float, nord: float, est: float) -> str:
        """L'édition de ZABAGED pour le manifeste."""
        return self.edition()["date"]

    def __call__(self, sud: float, ouest: float, nord: float, est: float) -> list:
        if self._base is None:
            self._base = geopackage(self.dossier, self.edition())
        return [{"id": f"{nature}:{fid_zbg}:{k}", "nature": nature, "pts": pts}
                for table, nature in COUCHES.items()
                for (fid_zbg,), k, pts in en_bloc.lignes_gpkg(self._base, table, COLONNES, EPSG, sud, ouest, nord,
                                                               est, geometrie=GEOMETRIE, cle=CLE)]
