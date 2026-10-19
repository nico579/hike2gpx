"""regles.py est une copie conforme de gpx2elev : ce test compare chaque
définition à sa source quand le dépôt de gpx2elev est présent sur la machine
(variable GPX2ELEV_OBSTACLES, ou son emplacement habituel)."""
import ast
import os
from pathlib import Path

import pytest

from hike2gpx import regles

SOURCE = Path(os.environ.get("GPX2ELEV_OBSTACLES", Path.home() / "Documents" / "gpxelev" / "android"
                             / "desktop" / "gpx2elev" / "obstacles.py"))
NOMS = ("SOLID", "PASSAGES", "LABELS", "ACCESS_KEYS", "access", "status")


def definitions(chemin):
    texte = Path(chemin).read_text(encoding="utf-8")
    trouvees = {}
    for noeud in ast.parse(texte).body:
        if isinstance(noeud, ast.FunctionDef):
            nom = noeud.name
        elif isinstance(noeud, ast.Assign) and isinstance(noeud.targets[0], ast.Name):
            nom = noeud.targets[0].id
        else:
            continue
        if nom in NOMS:
            trouvees[nom] = ast.get_source_segment(texte, noeud)
    return trouvees


@pytest.mark.skipif(not SOURCE.is_file(), reason="dépôt gpx2elev absent de cette machine")
def test_copie_conforme_de_gpx2elev():
    assert definitions(regles.__file__) == definitions(SOURCE)


def test_toutes_les_definitions_copiees():
    assert set(definitions(regles.__file__)) == set(NOMS)
