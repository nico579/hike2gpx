"""Emplacement commun des journaux et ouverture de ce dossier sur le poste."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def dossier(donnees) -> Path:
    return Path(donnees) / "logs"


def ouvrir(donnees) -> Path:
    chemin = dossier(donnees).resolve()
    chemin.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(chemin)
    else:
        commande = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([commande, str(chemin)], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    return chemin
