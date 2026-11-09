"""Le Basis-DLM des seize Länder, pour fabriquer les cases allemandes sur le
serveur.

En ligne, le lecteur ATKIS (providers/atkis.py) interroge par petite emprise
les WFS de Bavière et de Thuringe et les tuiles vectorielles de basemap.de ;
une case entière en demanderait des dizaines de milliers. basemap.de publie
aussi le Basis-DLM de chaque Land en un GeoPackage, au modèle de données de
ses tuiles, en WGS 84, refait chaque jour (« basisviews ») : une seule source,
un seul format pour toute l'Allemagne.

1. les Länder qui touchent l'emprise (BORNES) et le fichier du jour de
   chacun, d'après la liste du dossier de téléchargement ;
2. le GeoPackage du Land (de 38 Mo pour Brême à 3,6 Go pour la Bavière), en
   plages parallèles ;
3. de sa table verkehrslinie_bdlm, seules les classes de chemins que garde le
   lecteur en ligne (basemap_atkis.CLASSES) sont gardées, dans une petite
   base avec son index RTree ;
4. les chemins d'une emprise, lus par l'index RTree (en_bloc.lignes_gpkg).

Les tronçons portent leur Land et leur niveau, comme ceux des tuiles de
basemap.de, mais pas de « bords » : ce sont les objets entiers, non coupés
en tuiles. Licence : celle de chaque Land, le plus souvent la Datenlizenz
Deutschland (dl-de/by-2-0 ou zero-2-0), liée depuis basemap.de/open-data.
"""
from __future__ import annotations

import logging
import re
import shutil
import sqlite3
import urllib.request
from contextlib import closing
from pathlib import Path

from . import __version__, en_bloc
from .en_bloc import ErreurArchive
from .providers.basemap_atkis import CLASSES

journal = logging.getLogger(__name__)
LISTE = "https://basemap.de/dienste/opendata/basisviews/"
AGENT = {"User-Agent": f"hike2gpx/{__version__} (Basis-DLM des Länder)"}
EPSG = 4326
DOSSIER = "atkis-laender"           # « atkis » est le cache des tuiles du mode en ligne
PLAGES = 8
SOURCE, TABLE, GEOMETRIE, CLE = "verkehrslinie_bdlm", "Weg", "geom", "fid"
# Emprise de chaque Land (sud, ouest, nord, est), un peu élargie : un Land de
# trop ne coûte qu'un téléchargement, un Land oublié laisserait un trou.
BORNES = {
    "BW": (47.45, 7.45, 49.85, 10.55), "BY": (47.2, 8.9, 50.65, 13.9), "BE": (52.3, 13.05, 52.7, 13.8),
    "BB": (51.3, 11.2, 53.6, 14.8), "HB": (53.0, 8.45, 53.65, 9.0), "HH": (53.35, 8.1, 54.0, 10.35),
    "HE": (49.35, 7.75, 51.7, 10.3), "MV": (53.1, 10.55, 54.7, 14.45), "NI": (51.25, 6.6, 53.95, 11.65),
    "NW": (50.3, 5.85, 52.55, 9.5), "RP": (48.95, 6.1, 50.95, 8.55), "SL": (49.1, 6.35, 49.65, 7.45),
    "SN": (50.15, 11.85, 51.7, 15.05), "ST": (50.9, 10.55, 53.05, 13.2), "SH": (53.35, 7.85, 55.1, 11.35),
    "TH": (50.2, 9.85, 51.65, 12.65),
}
_FICHIER = re.compile(r'href="(basisviews_bdlm_([A-Z]{2})_EPSG4326_(\d{4}-\d{2}-\d{2})\.gpkg)"')


def _texte(url: str) -> str:
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=60) as reponse:
        return reponse.read().decode("utf-8", "replace")


def _taille(url: str) -> int:
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT, method="HEAD"), timeout=60) as reponse:
        return int(reponse.headers.get("Content-Length") or 0)


def fichiers(lire=_texte) -> dict:
    """{Land: {"date", "url"}} : le fichier le plus récent de chaque Land."""
    resultat = {}
    for nom, land, date in _FICHIER.findall(lire(LISTE)):
        if land in BORNES and date > resultat.get(land, {}).get("date", ""):
            resultat[land] = {"date": date, "url": LISTE + nom}
    return resultat


def laender_de_zone(sud: float, ouest: float, nord: float, est: float) -> list:
    """Les Länder dont l'emprise touche celle-ci."""
    return sorted(land for land, (s, o, n, e) in BORNES.items()
                  if s <= nord and n >= sud and o <= est and e >= ouest)


def geopackage(dossier, land: str, fichier: dict, taille=None) -> Path:
    """Les chemins du Land à la date du fichier, téléchargés une fois et gardés
    dans dossier/atkis-laender ; les dates plus anciennes du Land sont
    effacées."""
    racine = Path(dossier) / DOSSIER
    base = racine / f"{land}_{fichier['date']}.chemins.sqlite"
    if base.is_file():
        return base
    travail = racine / f".{land}"
    try:
        travail.mkdir(parents=True, exist_ok=True)
        complet = travail / fichier["url"].rsplit("/", 1)[-1]
        a_telecharger = {"url": fichier["url"], "octets": (taille or _taille)(fichier["url"]), "md5": None}
        journal.info("Basis-DLM : téléchargement de %s (%.0f Mo)", complet.name, a_telecharger["octets"] / 1e6)
        en_bloc.telecharger(a_telecharger, complet, essais=8, plages=PLAGES)
        mince = travail / "chemins.sqlite"
        gardes = _garder_les_chemins(complet, mince)
        journal.info("Basis-DLM %s : %d chemins gardés", land, gardes)
        mince.replace(base)
    finally:
        shutil.rmtree(travail, ignore_errors=True)
    for ancien in racine.glob(f"{land}_*.chemins.sqlite"):
        if ancien != base:
            ancien.unlink()
    return base


def _garder_les_chemins(gpkg: Path, cible: Path) -> int:
    """Les voies des classes de chemins (CLASSES) et leur index RTree, avec les
    seules colonnes que lit la fusion ; fid reste la clé que rend l'index."""
    classes = sorted(CLASSES)
    marques = ", ".join("?" for _ in classes)
    with closing(sqlite3.connect(str(cible), uri=True)) as base:     # uri : ATTACH en lecture seule
        base.execute("ATTACH DATABASE ? AS complet", (f"file:{gpkg.resolve().as_posix()}?mode=ro",))
        try:
            base.execute(f'CREATE TABLE "{TABLE}" ({CLE} INTEGER PRIMARY KEY, id TEXT, land TEXT, ebene INTEGER, '
                         f'klasse TEXT, {GEOMETRIE} BLOB)')
            base.execute(f'INSERT INTO "{TABLE}" SELECT {CLE}, id, land, ebene, klasse, {GEOMETRIE} '
                         f'FROM complet."{SOURCE}" WHERE klasse IN ({marques})', classes)
            rtree = f"rtree_{TABLE}_{GEOMETRIE}"
            base.execute(f'CREATE VIRTUAL TABLE "{rtree}" USING rtree(id, minx, maxx, miny, maxy)')
            base.execute(f'INSERT INTO "{rtree}" SELECT r.id, r.minx, r.maxx, r.miny, r.maxy '
                         f'FROM complet."rtree_{SOURCE}_{GEOMETRIE}" r JOIN "{TABLE}" t ON t.{CLE} = r.id')
        except sqlite3.OperationalError as exc:
            raise ErreurArchive(f"{gpkg.name} : pas de {SOURCE} lisible ({exc}).") from exc
        base.commit()
        gardes = base.execute(f'SELECT COUNT(*) FROM "{TABLE}"').fetchone()[0]
        base.execute("DETACH DATABASE complet")
    return gardes


class Lecteur:
    """Lecture des chemins du Basis-DLM d'une emprise dans les bases des
    Länder, pour fabrication.fabriquer(troncons={"atkis": ...}). La liste
    des fichiers n'est lue qu'une fois, et chaque Land n'est téléchargé qu'à
    la première emprise qui en a besoin."""

    def __init__(self, dossier):
        self.dossier = dossier
        self._fichiers = None
        self._bases = {}            # Land -> chemin

    def fichiers(self) -> dict:
        if self._fichiers is None:
            self._fichiers = fichiers()
        return self._fichiers

    def laender(self, sud: float, ouest: float, nord: float, est: float) -> list:
        return [land for land in laender_de_zone(sud, ouest, nord, est) if land in self.fichiers()]

    def date(self, sud: float, ouest: float, nord: float, est: float) -> str | None:
        """L'édition pour le manifeste : le fichier le plus récent des Länder de l'emprise."""
        return max((self.fichiers()[land]["date"] for land in self.laender(sud, ouest, nord, est)), default=None)

    def preparer(self, sud: float, ouest: float, nord: float, est: float) -> None:
        """Télécharge d'avance les Länder de l'emprise, sans rien lire : l'étape
        « données » les range dans son artefact, et la fusion en damier ne
        s'active que si chaque lecteur de la case sait le faire."""
        for land in self.laender(sud, ouest, nord, est):
            if land not in self._bases:
                self._bases[land] = geopackage(self.dossier, land, self.fichiers()[land])

    def __call__(self, sud: float, ouest: float, nord: float, est: float) -> list:
        self.preparer(sud, ouest, nord, est)
        resultat = []
        for land in self.laender(sud, ouest, nord, est):
            for (identifiant, ebene, klasse), k, pts in en_bloc.lignes_gpkg(
                    self._bases[land], TABLE, ("id", "ebene", "klasse"), EPSG, sud, ouest, nord, est,
                    geometrie=GEOMETRIE, cle=CLE):
                resultat.append({"id": f"DLM:{land}:{identifiant}:{k}", "land": land, "niveau": ebene or 0,
                                 "nature": CLASSES[klasse], "pts": pts})
        return resultat
