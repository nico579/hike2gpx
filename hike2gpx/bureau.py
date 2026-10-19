"""Intégration au bureau, comme dans les autres applications de nico579 (par
nico579-commons) : l'icône de la zone de notification et son menu commun
(Ouvrir, Mettre à jour, Redémarrer, Arrêter, Créer un raccourci sur le
Bureau), la relance et le raccourci. Le menu n'a aucune entrée propre à
hike2gpx : tout le reste passe par la page qu'ouvre « Ouvrir ».
"""
from __future__ import annotations

import locale
import logging
import os
import sys
import webbrowser
from pathlib import Path

journal = logging.getLogger(__name__)

ICONE = Path(__file__).parent / "assets" / "hike2gpx.ico"
DEPOT = "nico579/hike2gpx"


def commande_programme() -> list:
    """Le programme sans argument, qui sert la page et ouvre le navigateur :
    l'exécutable une fois figé ; depuis les sources, python -m hike2gpx
    (pythonw sous Windows, sans console à côté du navigateur)."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    python = Path(sys.executable)
    if sys.platform == "win32" and python.with_name("pythonw.exe").is_file():
        python = python.with_name("pythonw.exe")
    return [str(python), "-m", "hike2gpx"]


def commande_relance() -> list:
    """Le même programme avec les mêmes arguments. Depuis les sources,
    relance.commande() rejouerait argv[0], le __main__.py du paquet, que
    python ne sait pas lancer seul (imports relatifs) : on repasse par -m."""
    if getattr(sys, "frozen", False):
        from nico579_commons import relance
        return relance.commande()
    return [sys.executable, "-m", "hike2gpx", *sys.argv[1:]]


def langue(lire) -> str:
    """Langue du menu de l'icône : celle choisie dans la page, sinon celle
    du système."""
    code = lire()
    if code in ("fr", "en"):
        return code
    systeme = (locale.getlocale()[0] or "").lower()
    return "fr" if systeme.startswith(("fr", "french")) else "en"


def creer_raccourci(code_langue: str, dossier: Path, **options) -> int:
    from nico579_commons import raccourci
    icone = ICONE if sys.platform == "win32" else ICONE.with_suffix(".png")
    return raccourci.creer("hike2gpx", commande_programme(), Path(dossier), icone=icone,
                           description="hike2gpx", langue=code_langue, **options)


def actions(url: str, arreter, verificateur, lire_langue, dossier: Path):
    """Les actions du menu commun. « Mettre à jour » ouvre pour l'instant la
    page de la nouvelle version ; l'installation automatique viendra avec
    les bundles."""
    from nico579_commons import relance, tray

    def redemarrer():
        arreter()
        relance.relancer(commande_relance(), nom="hike2gpx", cwd=os.getcwd())

    def mettre_a_jour():
        info = verificateur.disponible()
        webbrowser.open(info["page"] if info else verificateur.page_des_releases)

    return tray.Actions(
        ouvrir=lambda: webbrowser.open(url),
        redemarrer=redemarrer,
        arreter=arreter,
        version_disponible=lambda: (verificateur.disponible() or {}).get("version"),
        mettre_a_jour=mettre_a_jour,
        mettre_a_jour_referme=False,
        creer_raccourci=lambda: creer_raccourci(langue(lire_langue), dossier),
        langue=lambda: langue(lire_langue),
    )


def icone_de_notification(url: str, arreter, verificateur, lire_langue, dossier: Path, arret):
    """L'icône prête à tourner, ou None sans zone de notification (serveur
    sans bureau, pystray absent) : le serveur continue alors sans elle."""
    from nico579_commons import tray
    if not tray.disponible():
        return None
    try:
        icone = tray.Tray("hike2gpx", ICONE, actions(url, arreter, verificateur, lire_langue, dossier), arret=arret)
        icone.construire()
    except Exception as exc:      # pystray lève sans affichage
        journal.warning("Icône de notification indisponible : %s", exc)
        return None
    return icone
