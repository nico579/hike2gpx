"""Chemins BDOT10k de toute la Pologne, pour le calque de la page.

Jusqu'au 2026-11-09, la page lisait le service ArcGIS du Geoportal de
Basse-Silésie, qui ne couvre que cette voïvodie. Elle lit désormais, comme le
serveur des lots, les GeoPackages par powiat du GUGiK (bdot10k_powiaty) : les
powiats de la tuile, téléchargés une fois (quelques dizaines de Mo chacun) et
gardés sur disque. Même source et même filtre partout.
"""
import threading
from pathlib import Path

_lecteurs = {}
_verrou = threading.Lock()


def lire(s, w, n, e, dossier):
    from .. import bdot10k_powiaty
    with _verrou:
        lecteur = _lecteurs.setdefault(Path(dossier).resolve(),
                                       bdot10k_powiaty.Lecteur(dossier, par_case=False))
    return lecteur(s, w, n, e)
