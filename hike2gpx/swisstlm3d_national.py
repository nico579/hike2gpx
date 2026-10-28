"""swissTLM3D en un seul GeoPackage national, pour fabriquer les cases suisses
sur le serveur.

L'API identify de geo.admin.ch convient à une vue ; une case entière en
demanderait des milliers de requêtes. swisstopo publie swissTLM3D entier, en
GeoPackage, sur le modèle de la BD TOPO régionale (bdtopo_regions) :

1. l'édition la plus récente : le catalogue STAC de data.geo.admin.ch (une
   archive zip par édition, EPSG 2056, environ 4,8 Go pour 2026-02) ;
2. l'archive, reprise si coupée, contrôlée par l'empreinte SHA-256 que donne
   le catalogue (checksum:multihash) ;
3. du GeoPackage décompressé (10,8 Go), seuls les chemins que lit la fusion
   sont gardés, avec leur index RTree, dans une petite base, pour les cases et
   les semaines suivantes ;
4. les chemins d'une emprise, lus par l'index RTree (en_bloc.lignes_gpkg).

Même filtre que le lecteur en ligne (providers/swisstlm3d.py) : objektart 15 à
18, sans restriction de circulation (verkehrsbeschraenkung 100). Le service en
ligne donne des codes, le fichier des libellés : leur correspondance a été
relevée en rapprochant les mêmes objets (essai GitHub Actions du 2026-10-28).
Conditions d'utilisation de swisstopo (OGD, version du 1.3.2021) : usage,
diffusion et traitement permis, usage commercial compris, avec mention de la
source.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import sqlite3
import urllib.request
import zipfile
from contextlib import closing
from pathlib import Path

from . import __version__, en_bloc
from .en_bloc import ErreurArchive

journal = logging.getLogger(__name__)
CATALOGUE = "https://data.geo.admin.ch/api/stac/v0.9/collections/ch.swisstopo.swisstlm3d/items?limit=100"
AGENT = {"User-Agent": f"hike2gpx/{__version__} (swissTLM3D national)"}
EPSG = 2056
DOSSIER = "swisstlm3d-national"     # « swisstlm3d » est le cache des tuiles du service en ligne
TABLE, GEOMETRIE, CLE = "tlm_strassen_strasse", "geom", "id"
# Libellé du fichier -> code du service en ligne (la nature « Weg <code> »).
CHEMINS = {"2m Weg": 15, "1m Weg": 16, "1m Wegfragment": 17, "2m Wegfragment": 18}
SANS_RESTRICTION = "Keine"          # verkehrsbeschraenkung 100 du service en ligne


def _json(url: str):
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=60) as reponse:
        return json.loads(reponse.read())


def _taille(url: str) -> int:
    demande = urllib.request.Request(url, headers=AGENT, method="HEAD")
    with urllib.request.urlopen(demande, timeout=60) as reponse:
        return int(reponse.headers.get("Content-Length") or 0)


def derniere_edition(lire=_json) -> dict:
    """{"nom", "date", "fichiers": [{"url", "octets", "sha256"}]} de la
    dernière édition GeoPackage, d'après le catalogue STAC."""
    editions = []
    for item in lire(CATALOGUE).get("features", []):
        for nom, asset in (item.get("assets") or {}).items():
            empreinte = (asset.get("checksum:multihash") or "").lower()
            if nom.endswith(".gpkg.zip") and re.fullmatch(r"1220[0-9a-f]{64}", empreinte):
                editions.append((item.get("properties", {}).get("datetime", "")[:10], nom, asset["href"],
                                 empreinte[4:]))
    if not editions:
        raise ErreurArchive("Aucune édition swissTLM3D GeoPackage dans le catalogue STAC.")
    date, nom, url, sha256 = max(editions)
    return {"nom": nom.removesuffix(".gpkg.zip"), "date": date,
            "fichiers": [{"url": url, "octets": None, "sha256": sha256}]}


def geopackage(dossier, edition: dict | None = None) -> Path:
    """Les chemins swissTLM3D de l'édition, téléchargés une fois et gardés dans
    dossier/swisstlm3d-national ; les éditions plus anciennes sont effacées."""
    edition = edition or derniere_edition()
    racine = Path(dossier) / DOSSIER
    base = racine / f"{edition['nom']}.chemins.sqlite"
    if base.is_file():
        return base
    travail = racine / f".{edition['nom']}"
    try:
        travail.mkdir(parents=True, exist_ok=True)
        fichier = dict(edition["fichiers"][0])
        fichier["octets"] = fichier["octets"] or _taille(fichier["url"])
        archive = travail / fichier["url"].rsplit("/", 1)[-1]
        journal.info("swissTLM3D : téléchargement de %s (%.0f Mo)", archive.name, fichier["octets"] / 1e6)
        en_bloc.telecharger(fichier, archive)
        gpkg = _extraire(archive, travail / "extrait")
        archive.unlink()                # de la place pour la réduction
        mince = travail / "chemins.sqlite"
        _garder_les_chemins(gpkg, mince)
        mince.replace(base)
    finally:
        shutil.rmtree(travail, ignore_errors=True)
    for ancien in racine.glob("*.chemins.sqlite"):
        if ancien != base:
            ancien.unlink()
    return base


def _extraire(archive: Path, dossier: Path) -> Path:
    """Le GeoPackage de l'archive (le plus gros s'il y en a plusieurs),
    décompressé dans dossier."""
    try:
        with zipfile.ZipFile(archive) as z:
            membres = [m for m in z.infolist() if m.filename.lower().endswith(".gpkg")]
            if not membres:
                raise ErreurArchive(f"Pas de GeoPackage dans {archive.name}.")
            membre = max(membres, key=lambda m: m.file_size)
            dossier.mkdir(parents=True, exist_ok=True)
            cible = dossier / Path(membre.filename).name
            journal.info("swissTLM3D : décompression de %s (%.0f Mo)", cible.name, membre.file_size / 1e6)
            with z.open(membre) as source, open(cible, "wb") as f:
                shutil.copyfileobj(source, f, en_bloc.BLOC)
    except zipfile.BadZipFile as exc:
        raise ErreurArchive(f"{archive.name} : archive altérée ({exc}).") from exc
    return cible


def _garder_les_chemins(gpkg: Path, cible: Path) -> None:
    """Les seuls chemins retenus (CHEMINS, sans restriction) et leur index RTree,
    copiés du GeoPackage national dans une base à part : 2,1 millions de
    routes et chemins au départ. id reste la clé, que l'index RTree renvoie."""
    rtree = f"rtree_{TABLE}_{GEOMETRIE}"
    marques = ", ".join("?" * len(CHEMINS))
    with closing(sqlite3.connect(str(cible), uri=True)) as base:     # uri : ATTACH en lecture seule
        base.execute("ATTACH DATABASE ? AS complet", (f"file:{gpkg.resolve().as_posix()}?mode=ro",))
        base.execute(f'CREATE TABLE "{TABLE}" ({CLE} INTEGER PRIMARY KEY, uuid TEXT, objektart TEXT, '
                     f'{GEOMETRIE} BLOB)')
        base.execute(f'INSERT INTO "{TABLE}" SELECT {CLE}, uuid, objektart, {GEOMETRIE} FROM complet."{TABLE}" '
                     f"WHERE objektart IN ({marques}) AND verkehrsbeschraenkung = ?",
                     (*CHEMINS, SANS_RESTRICTION))
        base.execute(f'CREATE VIRTUAL TABLE "{rtree}" USING rtree(id, minx, maxx, miny, maxy)')
        base.execute(f'INSERT INTO "{rtree}" SELECT r.id, r.minx, r.maxx, r.miny, r.maxy '
                     f'FROM complet."{rtree}" r JOIN "{TABLE}" t ON t.{CLE} = r.id')
        base.commit()
        base.execute("DETACH DATABASE complet")


class Lecteur:
    """Lecture des chemins swissTLM3D d'une emprise dans le GeoPackage national,
    pour fabrication.fabriquer(troncons={"swisstlm3d": ...}). L'archive n'est
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
        """L'édition de swissTLM3D pour le manifeste."""
        return self.edition()["date"]

    def __call__(self, sud: float, ouest: float, nord: float, est: float) -> list:
        if self._base is None:
            self._base = geopackage(self.dossier, self.edition())
        return [{"id": f"{uuid}:{k}", "nature": f"Weg {CHEMINS[objektart]}", "pts": pts}
                for (uuid, objektart), k, pts in en_bloc.lignes_gpkg(self._base, TABLE, ("uuid", "objektart"), EPSG,
                                                                      sud, ouest, nord, est, geometrie=GEOMETRIE,
                                                                      cle=CLE)]
