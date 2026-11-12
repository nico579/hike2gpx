"""La légende du PC et d'Android vient d'une source unique (hike2gpx/assets/legende.json)."""
import re
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "tools"))
import generer_legende as g  # noqa: E402


def test_fichiers_generes_a_jour():
    sortie = subprocess.run([sys.executable, str(RACINE / "tools" / "generer_legende.py"), "--check"],
                            capture_output=True, text=True, encoding="utf-8")
    assert sortie.returncode == 0, sortie.stdout


def test_couleurs_et_textes_identiques_sur_les_deux_plateformes():
    donnees = g.charger()
    commun = [e for e in donnees["entrees"] if {"pc", "android"} <= set(e["plateformes"])]
    assert len(commun) >= 6
    kotlin = g.kotlin(donnees)
    css = g.bloc_css(donnees)
    strings = g.bloc_strings(donnees, "fr")
    js = g.bloc_js(donnees, "fr")
    for e in commun:
        assert g.argb(e["couleur"]) in kotlin
        assert e["couleur"] in css
        assert f"legende_{e['id']}" in strings
        assert f"legende.{e['id']}" in js


def test_croix_de_fermeture_presente_sur_la_page():
    html = (RACINE / "hike2gpx" / "assets" / "web" / "index.html").read_text(encoding="utf-8")
    assert re.search(r'id="legendFermer"', html)
