"""swissTLM3D en un seul téléchargement national, pour fabriquer les cases
suisses sur le serveur.

L'API de swisstopo (providers/swisstlm3d.py) convient à une vue ; une case
entière en demanderait des milliers de requêtes. swisstopo publie aussi
swissTLM3D entier, sur le modèle de ZABAGED (zabaged_national) :

1. l'édition courante : la collection ch.swisstopo.swisstlm3d du catalogue
   STAC fédéral, une édition par an (swisstlm3d_2026-02…) ;
2. son archive Shapefile (3,6 Go, servie par S3), en plages parallèles,
   contrôlée par sa taille puis par le CRC du zip ;
3. de l'archive, seule la couche des routes et chemins (TLM_STRASSE, 2,1
   millions de tronçons) est lue, et seuls les chemins y sont gardés, dans
   une petite base au format GeoPackage avec son index RTree ;
4. les chemins d'une emprise, lus par l'index RTree (en_bloc.lignes_gpkg).

Même filtre que le lecteur en ligne (codes objektart 15 à 18, sans
restriction de circulation), que le Shapefile écrit en toutes lettres :
« 2m Weg », « 1m Weg » et leurs fragments, restriction « Keine ». Relevé sur
l'édition 2026-02 : 967 234 tronçons gardés.

Licence : géodonnées gratuites de swisstopo, utilisables, transformables et
redistribuables, source à citer (« © swisstopo »).
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import sqlite3
import struct
import urllib.request
import zipfile
from contextlib import closing
from pathlib import Path

from . import __version__, en_bloc
from .en_bloc import ErreurArchive

journal = logging.getLogger(__name__)
STAC = "https://data.geo.admin.ch/api/stac/v0.9/collections/ch.swisstopo.swisstlm3d/items"
AGENT = {"User-Agent": f"hike2gpx/{__version__} (swissTLM3D national)"}
EPSG = 2056                         # CH1903+ / LV95, celui de l'archive
DOSSIER = "swisstlm3d-national"     # « swisstlm3d » est le cache des tuiles de l'API
PLAGES = 8
COUCHE = "TLM_STRASSEN/swissTLM3D_TLM_STRASSE"
# Libellé du Shapefile -> code de l'API, pour nommer les tronçons comme le
# lecteur en ligne (« Weg 16 »).
CHEMINS = {"2m Weg": 15, "1m Weg": 16, "1m Wegfragment": 17, "2m Wegfragment": 18}
SANS_RESTRICTION = "Keine"
TABLE, GEOMETRIE, CLE = "Weg", "geom", "fid"


def _json(url: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=60) as reponse:
        return json.loads(reponse.read())


def _taille(url: str) -> int:
    return en_bloc.taille(url)      # une seule copie, qui échoue sans Content-Length (audit A04)


def derniere_edition(lire=_json, taille=_taille) -> dict:
    """{"nom", "date", "fichiers": [{"url", "octets", "md5": None}]} de la
    dernière édition, d'après le catalogue STAC (toutes les pages)."""
    editions, url = {}, STAC
    while url:
        page = lire(url)
        for item in page.get("features", []):
            for asset in item.get("assets", {}).values():
                href = asset.get("href", "")
                trouve = re.fullmatch(r"https://[\w.-]+/[\w./-]*/(swisstlm3d_(\d{4})-(\d{2}))_2056_5728\.shp\.zip",
                                      href)
                if trouve:
                    editions[trouve.group(1)] = (f"{trouve.group(2)}-{trouve.group(3)}", href)
        url = next((l["href"] for l in page.get("links", []) if l.get("rel") == "next"), None)
    if not editions:
        raise ErreurArchive("Aucune édition Shapefile de swissTLM3D dans le catalogue STAC.")
    nom = max(editions)
    date, href = editions[nom]
    return {"nom": nom, "date": date, "fichiers": [{"url": href, "octets": taille(href), "md5": None}]}


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
        fichier = edition["fichiers"][0]
        archive = travail / fichier["url"].rsplit("/", 1)[-1]
        journal.info("swissTLM3D : téléchargement de %s (%.0f Mo)", archive.name, fichier["octets"] / 1e6)
        en_bloc.telecharger(fichier, archive, essais=8, plages=PLAGES)
        shp = _extraire(archive, travail / "extrait")
        archive.unlink()
        mince = travail / "chemins.sqlite"
        gardes = _garder_les_chemins(shp, mince)
        journal.info("swissTLM3D : %d chemins gardés", gardes)
        mince.replace(base)
    finally:
        shutil.rmtree(travail, ignore_errors=True)
    for ancien in racine.glob("swisstlm3d_*.chemins.sqlite"):
        if ancien != base:
            ancien.unlink()
    return base


def _extraire(archive: Path, dossier: Path) -> Path:
    """Les trois fichiers de la couche des routes (.shp, .shx, .dbf),
    décompressés dans dossier ; zipfile contrôle le CRC en lisant. Rend le
    chemin du .shp.

    L'archive de swisstopo est faite sous Windows : ses noms gardent des
    barres obliques inverses (TLM_STRASSEN\\swissTLM3D_…). zipfile ne les
    convertit qu'en lisant sous Windows ; sous Linux, sur le serveur, le nom
    avec « / » n'existait pas (essai 42644919578). Les noms sont donc
    comparés une fois normalisés."""
    dossier.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive) as z:
            par_nom = {m.filename.replace("\\", "/"): m for m in z.infolist()}
            for extension in (".shp", ".shx", ".dbf"):
                membre = COUCHE + extension
                if membre not in par_nom:
                    raise ErreurArchive(f"Pas de {membre} dans {archive.name}.")
                with z.open(par_nom[membre]) as source, open(dossier / Path(membre).name, "wb") as f:
                    shutil.copyfileobj(source, f, en_bloc.BLOC)
    except zipfile.BadZipFile as exc:
        raise ErreurArchive(f"{archive.name} : archive altérée ({exc}).") from exc
    return dossier / (Path(COUCHE).name + ".shp")


def _blob(srs: int, parties: list) -> bytes:
    """Une géométrie GeoPackage (en-tête « GP » sans enveloppe, puis WKB) :
    LineString pour une partie, MultiLineString sinon ; x, y seulement."""
    def ligne(points):
        return struct.pack("<BII", 1, 2, len(points)) + b"".join(struct.pack("<dd", x, y) for x, y in points)
    if len(parties) == 1:
        wkb = ligne(parties[0])
    else:
        wkb = struct.pack("<BII", 1, 5, len(parties)) + b"".join(ligne(p) for p in parties)
    return b"GP\x00\x01" + struct.pack("<i", srs) + wkb


def _garder_les_chemins(shp: Path, cible: Path) -> int:
    """Les chemins de la couche, filtrés comme le lecteur en ligne, dans une
    base au format GeoPackage (table Weg et son index RTree, pour
    en_bloc.lignes_gpkg). Rend le nombre de tronçons gardés."""
    import shapefile                # pyshp, lu seulement sur le serveur des lots

    gardes = 0
    with shapefile.Reader(str(shp), encoding="utf-8") as lecteur, \
            closing(sqlite3.connect(str(cible))) as base:
        base.execute(f'CREATE TABLE "{TABLE}" ({CLE} INTEGER PRIMARY KEY, uuid TEXT, code INTEGER, {GEOMETRIE} BLOB)')
        base.execute(f'CREATE VIRTUAL TABLE "rtree_{TABLE}_{GEOMETRIE}" USING rtree(id, minx, maxx, miny, maxy)')
        champs = ["OBJEKTART", "VERKEHRSBE", "UUID"]
        for rang, enregistrement in enumerate(lecteur.iterRecords(fields=champs)):
            code = CHEMINS.get(enregistrement["OBJEKTART"])
            if code is None or enregistrement["VERKEHRSBE"] != SANS_RESTRICTION:
                continue
            forme = lecteur.shape(rang)
            debuts = list(forme.parts) + [len(forme.points)]
            parties = [[(x, y) for x, y, *_ in forme.points[a:b]] for a, b in zip(debuts, debuts[1:])]
            parties = [p for p in parties if len(p) >= 2]
            if not parties:
                continue
            gardes += 1
            base.execute(f'INSERT INTO "{TABLE}" VALUES (?, ?, ?, ?)',
                         (gardes, enregistrement["UUID"].strip("{}"), code, _blob(EPSG, parties)))
            xmin, ymin, xmax, ymax = forme.bbox
            base.execute(f'INSERT INTO "rtree_{TABLE}_{GEOMETRIE}" VALUES (?, ?, ?, ?, ?)',
                         (gardes, xmin, xmax, ymin, ymax))
        base.commit()
    return gardes


class Lecteur:
    """Lecture des chemins swissTLM3D d'une emprise dans la base nationale,
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

    def preparer(self, sud: float, ouest: float, nord: float, est: float) -> None:
        """Télécharge d'avance l'édition, sans rien lire : l'étape « données »
        la range dans son artefact, et la fusion en damier ne s'active que si
        chaque lecteur de la case sait le faire (fabrication._lecteur)."""
        if self._base is None:
            self._base = geopackage(self.dossier, self.edition())

    def __call__(self, sud: float, ouest: float, nord: float, est: float) -> list:
        self.preparer(sud, ouest, nord, est)
        return [{"id": f"{uuid}:{k}", "nature": f"Weg {code}", "pts": pts}
                for (uuid, code), k, pts in en_bloc.lignes_gpkg(self._base, TABLE, ("uuid", "code"), EPSG, sud,
                                                                 ouest, nord, est, geometrie=GEOMETRIE, cle=CLE)]
