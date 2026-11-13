"""L'emplacement du dossier des données, choisi aux réglages (demande de Nico du
2026-11-13 : les cartes et les zones pèsent des Go, un autre disque peut les
recevoir).

Tout le dossier change de place, préférences, journaux et téléchargements
(cartes, zones, extraits OSM, moteur BRouter, relief) : chaque module continue
de tout trouver sous un seul dossier, comme avec HIKE2GPX_HOME. À
l'emplacement standard ne reste qu'un pointeur :

  %LOCALAPPDATA%/hike2gpx-data/emplacement.json   {"dossier": "D:/Cartes/hike2gpx-data"}

Le déplacement copie le dossier (avec son avancement) dans <choisi>/hike2gpx-data,
pose le pointeur, puis relance hike2gpx : le nouveau processus démarre sur la
copie, et efface l'ancien dossier. Une copie, pas un renommage : sous Windows,
le journal ouvert et le moteur BRouter empêchent de renommer leur dossier.
Une copie interrompue ne laisse qu'un dossier .part, effacé.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from nico579_commons import atomique
from nico579_commons.dossiers import Dossiers

journal = logging.getLogger(__name__)
POINTEUR = "emplacement.json"
DOSSIERS = Dossiers("hike2gpx", variable_home="HIKE2GPX_HOME")


def standard() -> Path:
    """L'emplacement standard des données, celui du pointeur."""
    return DOSSIERS.dossier_etat_standard()


def force() -> Path | None:
    """Le dossier que HIKE2GPX_HOME impose, ou None : il passe avant le pointeur."""
    return DOSSIERS.force(os.environ)


class Abandon(Exception):
    """La copie arrêtée à la demande."""


def taille(dossier: Path) -> int:
    """Les octets d'un dossier, sous-dossiers compris."""
    return sum(p.stat().st_size for p in Path(dossier).rglob("*") if p.is_file())


def lire(standard: Path) -> dict:
    """Le pointeur de l'emplacement standard, ou {}."""
    contenu = atomique.lire_json(Path(standard) / POINTEUR, {})
    return contenu if isinstance(contenu, dict) else {}


def dossier_effectif(standard: Path) -> Path:
    """Le dossier des données : celui du pointeur s'il existe, sinon
    l'emplacement standard. Un disque débranché ne fait pas démarrer
    hike2gpx sur un dossier vide : il repart, avec un avertissement, sur
    l'emplacement standard."""
    choisi = lire(standard).get("dossier")
    if not isinstance(choisi, str) or not choisi:
        return Path(standard)
    if Path(choisi).is_dir():
        return Path(choisi)
    journal.warning("Dossier des données %s introuvable (disque débranché ?) : %s à la place", choisi, standard)
    return Path(standard)


def nettoyer(standard: Path, actuel: Path) -> None:
    """Efface l'ancien dossier qu'un déplacement a laissé (pointeur « effacer »),
    au démarrage qui suit : plus rien n'y est ouvert. À l'emplacement
    standard, le pointeur reste."""
    pointeur = lire(standard)
    ancien = pointeur.get("effacer")
    if not isinstance(ancien, str) or not ancien or Path(ancien).resolve() == Path(actuel).resolve():
        return
    ancien = Path(ancien)
    if ancien.resolve() == Path(standard).resolve():
        for enfant in ancien.iterdir():
            if enfant.name != POINTEUR:
                shutil.rmtree(enfant, ignore_errors=True) if enfant.is_dir() else enfant.unlink(missing_ok=True)
    else:
        shutil.rmtree(ancien, ignore_errors=True)
    pointeur.pop("effacer", None)
    atomique.ecrire_json(Path(standard) / POINTEUR, pointeur)
    journal.info("Ancien dossier des données effacé : %s", ancien)


def copier(source: Path, cible: Path, suivi=lambda faites, total: None, continuer=lambda: True) -> None:
    """Copie le dossier source en cible, absente (ou ne contenant que le
    pointeur, pour revenir à l'emplacement standard), dans cible.part renommé
    à la fin. Le pointeur de la source ne suit pas."""
    source, cible = Path(source), Path(cible)
    provisoire = cible.with_name(cible.name + ".part")
    shutil.rmtree(provisoire, ignore_errors=True)
    fichiers = [p for p in sorted(source.rglob("*")) if p.relative_to(source).as_posix() != POINTEUR]
    total = sum(p.stat().st_size for p in fichiers if p.is_file())
    faites = 0
    try:
        provisoire.mkdir(parents=True)
        for chemin in fichiers:
            destination = provisoire / chemin.relative_to(source)
            if chemin.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with open(chemin, "rb") as a, open(destination, "wb") as b:
                while bloc := a.read(1 << 20):
                    if not continuer():
                        raise Abandon()
                    b.write(bloc)
                    faites += len(bloc)
                    suivi(faites, total)
            shutil.copystat(chemin, destination)
        if cible.exists():                  # l'emplacement standard : il n'y reste que le pointeur
            for chemin in provisoire.iterdir():
                chemin.rename(cible / chemin.name)
            provisoire.rmdir()
        else:
            provisoire.rename(cible)
    except BaseException:
        shutil.rmtree(provisoire, ignore_errors=True)
        raise


def basculer(standard: Path, ancien: Path, nouveau: Path) -> None:
    """Le pointeur vers le nouveau dossier, et l'ancien à effacer au démarrage
    suivant. Revenu à l'emplacement standard, le pointeur ne garde que
    l'effacement."""
    pointeur = {"effacer": str(ancien)}
    if Path(nouveau).resolve() != Path(standard).resolve():
        pointeur["dossier"] = str(nouveau)
    Path(standard).mkdir(parents=True, exist_ok=True)
    atomique.ecrire_json(Path(standard) / POINTEUR, pointeur)
