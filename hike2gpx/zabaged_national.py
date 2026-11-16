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
import xml.etree.ElementTree as ET
from pathlib import Path

from . import __version__, en_bloc
from .en_bloc import ErreurArchive

journal = logging.getLogger(__name__)
FLUX = "https://atom.cuzk.gov.cz/ZABAGED-GPKG/datasetFeeds/CZ-00025712-CUZK_ZABAGED-GPKG_1.xml"
ATOM = "{http://www.w3.org/2005/Atom}"
AGENT = {"User-Agent": f"hike2gpx/{__version__} (ZABAGED national)"}
EPSG = 3045
# Plages parallèles du téléchargement : le serveur bride chaque connexion (en_bloc._par_plages).
PLAGES = 8
DOSSIER = "zabaged-national"        # « zabaged » est le cache des tuiles du service en ligne
# Table du GeoPackage -> nature du tronçon, celle du lecteur en ligne. Relevé
# sur l'édition du 2026-10-04 (essai GitHub Actions du 2026-10-28) : 74 514
# sentiers, 1 191 886 chemins, géométrie « Shape » et clé OBJECTID.
COUCHES = {"Pesina": "Pěšina", "Cesta": "Cesta"}
COLONNES = ("fid_zbg",)
GEOMETRIE, CLE = "Shape", "OBJECTID"


def _atom(url: str) -> ET.Element:
    return en_bloc.lire(url, ET.fromstring, entetes=AGENT, nom="ZABAGED : flux des éditions")


def derniere_edition(lire=_atom, taille=None) -> dict:
    """{"nom", "date", "fichiers": [{"url", "octets", "md5": None}]} de
    l'édition la plus récente en EPSG 3045, d'après le flux du jeu de données.
    La plus récente, pas la première : rien ne garantit l'ordre du flux
    (audit A06, 2026-11-13), et les trois autres fournisseurs prennent déjà le
    maximum. Sans attribut length, la taille se demande au serveur (A04)."""
    editions = []
    for entree in lire(FLUX).findall(ATOM + "entry"):
        for lien in entree.findall(ATOM + "link"):
            url = lien.get("href", "")
            trouve = re.fullmatch(r"https://[\w.-]+/[\w/.-]*/epsg-3045/(ZABAGED-3045-gpkg-(\d{4})(\d{2})(\d{2}))\.zip",
                                  url)
            if trouve:
                editions.append(("-".join(trouve.group(2, 3, 4)), trouve.group(1), url, lien.get("length")))
    if not editions:
        raise ErreurArchive("Aucune édition ZABAGED GeoPackage en EPSG 3045 dans le flux de l'ČÚZK.")
    date, nom, url, longueur = max(editions)
    octets = int(longueur) if longueur and longueur.isdigit() and int(longueur) > 0 \
        else (taille or en_bloc.taille)(url)
    return {"nom": nom, "date": date, "fichiers": [{"url": url, "octets": octets, "md5": None}]}


def geopackage(dossier, edition: dict | None = None) -> Path:
    """Les sentiers et chemins ZABAGED de l'édition, téléchargés une fois et
    gardés dans dossier/zabaged-national ; les éditions plus anciennes sont
    effacées."""
    edition = edition or derniere_edition()

    def fabriquer(travail: Path, cible: Path) -> None:
        fichier = edition["fichiers"][0]
        archive = travail / fichier["url"].rsplit("/", 1)[-1]
        journal.info("ZABAGED : téléchargement de %s (%.0f Mo)", archive.name, fichier["octets"] / 1e6)
        en_bloc.telecharger(fichier, archive, essais=8, plages=PLAGES)
        gpkg = _extraire(archive, travail / "extrait")
        archive.unlink()                # de la place pour la réduction
        _garder_les_chemins(gpkg, cible)
    return en_bloc.base_reduite(Path(dossier) / DOSSIER / f"{edition['nom']}.chemins.sqlite",
                                "ZABAGED-*.chemins.sqlite", fabriquer)


def _extraire(archive: Path, dossier: Path) -> Path:
    """Le GeoPackage de l'archive (le plus gros s'il y en a plusieurs),
    décompressé dans dossier."""
    def choisir(membres: dict) -> list:
        gpkg = [m for nom, m in membres.items() if nom.lower().endswith(".gpkg")]
        if not gpkg:
            raise ErreurArchive(f"Pas de GeoPackage dans {archive.name}.")
        membre = max(gpkg, key=lambda m: m.file_size)
        journal.info("ZABAGED : décompression de %s (%.0f Mo)", Path(membre.filename).name, membre.file_size / 1e6)
        return [membre]
    return en_bloc.extraire(archive, dossier, choisir)[0]


def _garder_les_chemins(gpkg: Path, cible: Path) -> None:
    """Les tables des sentiers et des chemins et leurs index RTree, avec la
    seule colonne que lit la fusion. OBJECTID reste la clé primaire."""
    en_bloc.garder_couches(gpkg, cible, [(table, table, "fid_zbg TEXT", "", ()) for table in COUCHES],
                           geometrie=GEOMETRIE, cle=CLE)


class Lecteur(en_bloc.LecteurEdition):
    """Lecture des chemins ZABAGED d'une emprise dans le GeoPackage national,
    pour fabrication.fabriquer(troncons={"zabaged": ...})."""

    def __init__(self, dossier):
        # Les lambdas relisent les fonctions du module à chaque appel : les essais les remplacent.
        super().__init__(dossier, lambda: derniere_edition(), lambda d, e: geopackage(d, e))

    def __call__(self, sud: float, ouest: float, nord: float, est: float) -> list:
        self.preparer(sud, ouest, nord, est)
        return [{"id": f"{nature}:{fid_zbg}:{k}", "nature": nature, "pts": pts}
                for table, nature in COUCHES.items()
                for (fid_zbg,), k, pts in en_bloc.lignes_gpkg(self._base, table, COLONNES, EPSG, sud, ouest, nord,
                                                               est, geometrie=GEOMETRIE, cle=CLE)]
