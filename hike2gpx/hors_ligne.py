"""Lots de cases installés pour le calcul sans réseau.

Un lot (lot.py) se livre avec son manifeste : chaque fichier y figure avec sa
taille et son SHA-256. L'installation les vérifie tous, puis range la RD5 dans
un dossier de segments commun à tous les lots (BRouter lit un seul dossier),
et le reste dans le dossier de la case :

  hors-ligne/segments/E5_N40.rd5
  hors-ligne/E5_N40/manifest.json, franchissements.json.gz, calques.mbtiles

Un parcours dont la zone tient dans l'emprise enrichie d'un lot se calcule
alors sur ces fichiers seuls, sans Overpass, WFS ni RD5 officielle.
"""
from __future__ import annotations

import gzip
import json
import shutil
from pathlib import Path

from . import lot

SOURCE_DU_LOT = {"ign": "bdtopo"}       # source de l'application -> clé des sources du manifeste


class ErreurLot(ValueError):
    pass


class HorsLigne:
    def __init__(self, dossier: Path):
        self.racine = Path(dossier) / "hors-ligne"
        self.segments = self.racine / "segments"
        self._franchissements = {}      # case -> liste, lue une fois

    def lots(self) -> list:
        """Manifestes des lots installés."""
        if not self.racine.is_dir():
            return []
        return [json.loads(m.read_text(encoding="utf-8")) for m in sorted(self.racine.glob("*/manifest.json"))]

    def installer(self, source: Path) -> dict:
        """Installe le lot du dossier source après vérification de chaque fichier
        contre le manifeste. Remplace un lot plus ancien de la même case."""
        source = Path(source)
        try:
            manifeste = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ErreurLot(f"Manifeste illisible : {exc}") from exc
        if manifeste.get("format") != lot.FORMAT:
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
        self.segments.mkdir(parents=True, exist_ok=True)
        provisoire = self.racine / f".{case}.part"
        shutil.rmtree(provisoire, ignore_errors=True)
        provisoire.mkdir(parents=True)
        for f in manifeste["fichiers"]:
            if f["nom"] != rd5:
                shutil.copy2(source / f["nom"], provisoire / f["nom"])
        shutil.copy2(source / "manifest.json", provisoire / "manifest.json")
        shutil.copy2(source / rd5, self.segments / f".{rd5}.part")
        shutil.rmtree(self.racine / case, ignore_errors=True)
        provisoire.replace(self.racine / case)
        (self.segments / f".{rd5}.part").replace(self.segments / rd5)
        self._franchissements.pop(case, None)
        return manifeste

    def lot_pour(self, zone: tuple, source: str = "ign") -> dict | None:
        """Le lot installé dont l'emprise enrichie contient toute la zone (sud,
        ouest, nord, est), pour cette source de chemins officiels."""
        cle = SOURCE_DU_LOT.get(source)
        sud, ouest, nord, est = zone
        for manifeste in self.lots():
            emprise = manifeste.get("emprise_enrichie")
            if not emprise or not cle or not manifeste.get("sources", {}).get(cle):
                continue
            es, eo, en, ee = emprise
            if es <= sud and eo <= ouest and nord <= en and est <= ee \
                    and (self.segments / f"{manifeste['case']}.rd5").is_file():
                return manifeste
        return None

    def franchissements(self, manifeste: dict, zone: tuple) -> list:
        """Les franchissements du lot qui tombent dans la zone."""
        case = manifeste["case"]
        if case not in self._franchissements:
            with gzip.open(self.racine / case / "franchissements.json.gz", "rt", encoding="utf-8") as f:
                self._franchissements[case] = json.load(f)
        sud, ouest, nord, est = zone
        return [f for f in self._franchissements[case] if sud <= f["lat"] <= nord and ouest <= f["lon"] <= est]
