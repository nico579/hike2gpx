"""Lots de cases installés pour le calcul sans réseau.

Un lot (lot.py) se livre avec son manifeste : chaque fichier y figure avec sa
taille et son SHA-256. L'installation les vérifie tous, puis range la RD5 dans
un dossier de segments commun à tous les lots (BRouter lit un seul dossier),
et le reste dans le dossier de la case :

  hors-ligne/segments/E5_N40.rd5
  hors-ligne/E5_N40/manifest.json, franchissements.json.gz, calques.mbtiles

Les fonds de carte (fonds.py) se rangent à part, un MBTiles chacun, sans
manifeste : ils ne sont pas des lots et n'entrent jamais dans une publication.

  hors-ligne/fonds/E5_N40-scan25.mbtiles, E5_N40-scan25-vue-3fa2c1.mbtiles

Règle unique : un parcours dont la zone tient dans un lot (l'emprise enrichie
d'un lot enrichi, la zone d'un lot OSM) se calcule et s'affiche sur ce lot
seul, sans Overpass, WFS ni RD5 téléchargée ; sinon, tout se fait à la volée.
"""
from __future__ import annotations

import gzip
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from . import fonds, lot


class ErreurLot(ValueError):
    pass


class HorsLigne:
    def __init__(self, dossier: Path):
        self.racine = Path(dossier) / "hors-ligne"
        self.segments = self.racine / "segments"
        # RD5 officielles des lots OSM : la table de tags standard de BRouter,
        # pas celle des RD5 enrichies ; un dossier à part pour ne pas les mêler.
        self.segments_osm = self.racine / "segments-osm"
        self._franchissements = {}      # case -> liste, lue une fois
        self.dossier_fonds = self.racine / "fonds"

    def lots(self) -> list:
        """Manifestes des lots installés."""
        if not self.racine.is_dir():
            return []
        return [json.loads(m.read_text(encoding="utf-8")) for m in sorted(self.racine.glob("*/manifest.json"))]

    def fonds(self) -> list:
        """Les fonds de carte installés, décrits par fonds.decrire ; un fichier
        illisible (copie interrompue, autre format) est ignoré."""
        if not self.dossier_fonds.is_dir():
            return []
        decrits = []
        for chemin in sorted(self.dossier_fonds.glob("*.mbtiles")):
            try:
                decrits.append(fonds.decrire(chemin))
            except (OSError, sqlite3.Error, KeyError, ValueError):
                continue
        return decrits

    def chemin_fond(self, nom: str) -> Path | None:
        """Le fichier du fond installé de ce nom, ou None : un nom venu d'une
        requête ne désigne jamais rien hors du dossier des fonds."""
        if not fonds.nom_valide(nom):
            return None
        chemin = self.dossier_fonds / f"{nom}.mbtiles"
        return chemin if chemin.is_file() else None

    def supprimer(self, case: str) -> int:
        """Retire du PC tout ce qui sert la case hors ligne : son lot, sa RD5
        et ses fonds de carte (un voyage fini, une case qu'on ne visitera
        plus). Les moteurs BRouter qui lisent la RD5 sont arrêtés avant, par
        l'appelant. Rend les octets libérés."""
        fichiers = [self.segments / f"{case}.rd5", self.segments_osm / f"{case}.rd5",
                    *self.dossier_fonds.glob(f"{case}-*.mbtiles")]
        dossier = self.racine / case
        if dossier.is_dir():
            fichiers += [p for p in dossier.iterdir() if p.is_file()]
        fichiers = [p for p in fichiers if p.is_file()]
        octets = sum(p.stat().st_size for p in fichiers)
        for p in fichiers:
            p.unlink()
        shutil.rmtree(dossier, ignore_errors=True)
        self._oublier()
        return octets

    def vider(self) -> None:
        """Tous les lots et les fonds de carte retirés, pour repartir de zéro :
        ceux du serveur se retéléchargent vite."""
        if self.racine.is_dir():
            shutil.rmtree(self.racine)
        self._oublier()

    def _oublier(self) -> None:
        """Ce qui a été lu des lots retirés ne sert plus."""
        self._franchissements.clear()
        lot._tuile_decodee.cache_clear()

    def installer(self, source: Path) -> dict:
        """Installe le lot du dossier source après vérification de chaque fichier
        contre le manifeste. Remplace un lot plus ancien de la même case."""
        source = Path(source)
        try:
            manifeste = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ErreurLot(f"Manifeste illisible : {exc}") from exc
        if manifeste.get("format") not in lot.FORMATS_LUS:
            raise ErreurLot(f"Format de lot {manifeste.get('format')} inconnu (attendu : {lot.FORMAT}).")
        case = manifeste.get("case", "")
        if not case or "/" in case or "\\" in case or ".." in case:
            raise ErreurLot("Nom de case invalide dans le manifeste.")
        for f in manifeste.get("fichiers", []):
            chemin = source / Path(f["nom"]).name
            if not chemin.is_file() or chemin.stat().st_size != f["octets"]:
                raise ErreurLot(f"{f['nom']} manquant ou de taille inattendue.")
            if lot.empreinte(chemin) != f["sha256"]:
                raise ErreurLot(f"{f['nom']} ne correspond pas à son empreinte SHA-256.")
        rd5 = f"{case}.rd5"
        if rd5 not in {f["nom"] for f in manifeste["fichiers"]}:
            raise ErreurLot(f"Le lot ne contient pas {rd5}.")
        # Copie à côté, puis remplacement : un lot à moitié copié n'est jamais lu.
        segments = self.segments_osm if manifeste.get("type") == "osm" else self.segments
        segments.mkdir(parents=True, exist_ok=True)
        provisoire = self.racine / f".{case}.part"
        shutil.rmtree(provisoire, ignore_errors=True)
        provisoire.mkdir(parents=True)
        for f in manifeste["fichiers"]:
            if f["nom"] != rd5:
                shutil.copy2(source / f["nom"], provisoire / f["nom"])
        shutil.copy2(source / "manifest.json", provisoire / "manifest.json")
        shutil.copy2(source / rd5, segments / f".{rd5}.part")
        shutil.rmtree(self.racine / case, ignore_errors=True)
        provisoire.replace(self.racine / case)
        (segments / f".{rd5}.part").replace(segments / rd5)
        self._franchissements.pop(case, None)
        return manifeste

    def lot_couvrant(self, zone: tuple) -> dict | None:
        """Le lot installé qui couvre toute la zone (sud, ouest, nord, est) :
        règle unique, un lot qui couvre la zone sert seul, calcul et calques.
        Un lot enrichi couvre son emprise enrichie, un lot OSM sa zone ; à
        égalité, l'enrichi passe d'abord."""
        sud, ouest, nord, est = zone
        candidats = []
        for manifeste in self.lots():
            osm = manifeste.get("type") == "osm"
            couverture = manifeste.get("zone") if osm else manifeste.get("emprise_enrichie")
            segments = self.segments_osm if osm else self.segments
            if not couverture or not (segments / f"{manifeste['case']}.rd5").is_file():
                continue
            cs, co, cn, ce = couverture
            if cs <= sud and co <= ouest and nord <= cn and est <= ce:
                candidats.append((osm, manifeste))
        return min(candidats, key=lambda c: c[0])[1] if candidats else None

    def date_du_lot(self, manifeste: dict) -> float:
        """Date des données du lot (horodatage) : l'édition de l'extrait OSM,
        sinon le jour de son installation. Un lot plus vieux que le délai de
        renouvellement des réglages fait poser la question de sa mise à jour."""
        try:
            return datetime.fromisoformat(manifeste["sources"]["osm"].replace("Z", "+00:00")).timestamp()
        except (KeyError, TypeError, AttributeError, ValueError):
            return (self.racine / manifeste["case"] / "manifest.json").stat().st_mtime

    def lot_du_calque(self, zone: tuple, calque: str) -> dict | None:
        """Le lot qui sait afficher ce calque de la page sur toute la zone : la
        case entière pour OSM, l'emprise enrichie pour les chemins officiels."""
        sud, ouest, nord, est = zone
        for manifeste in self.lots():
            if calque == "osm":
                # Un lot OSM peut ne couvrir qu'une partie de sa case (zone).
                bs, bo, bn, be = manifeste.get("zone") or lot.boite_case(manifeste["case"])
            elif manifeste.get("sources", {}).get(calque):      # bdtopo, atkis… : le fournisseur du lot
                bs, bo, bn, be = manifeste.get("emprise_enrichie") or (0, 0, 0, 0)
            else:
                continue
            if bs <= sud and bo <= ouest and nord <= bn and est <= be \
                    and (self.racine / manifeste["case"] / "calques.mbtiles").is_file():
                return manifeste
        return None

    def calque(self, manifeste: dict, calque: str, zone: tuple) -> dict:
        return lot.lire_calque(self.racine / manifeste["case"] / "calques.mbtiles", calque, *zone)

    def franchissements(self, manifeste: dict, zone: tuple) -> list:
        """Les franchissements du lot qui tombent dans la zone."""
        case = manifeste["case"]
        if case not in self._franchissements:
            with gzip.open(self.racine / case / "franchissements.json.gz", "rt", encoding="utf-8") as f:
                self._franchissements[case] = json.load(f)
        sud, ouest, nord, est = zone
        return [f for f in self._franchissements[case] if sud <= f["lat"] <= nord and ouest <= f["lon"] <= est]
