"""La légende du PC et d'Android vient d'une source unique (hike2gpx/assets/legende.json)."""
import re
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "tools"))
import generer_legende as g  # noqa: E402

ORDRE = ["osm", "chemins_officiels", "itineraire", "gpx", "barriere", "bloque", "verifier", "jonction"]


def test_fichiers_generes_a_jour():
    sortie = subprocess.run([sys.executable, str(RACINE / "tools" / "generer_legende.py"), "--check"],
                            capture_output=True, text=True, encoding="utf-8")
    assert sortie.returncode == 0, sortie.stdout


def test_ordre_et_textes_voulus():
    donnees = g.charger()
    assert [e["id"] for e in donnees["entrees"]] == ORDRE
    textes = {e["id"]: e["fr"] for e in donnees["entrees"]}
    assert textes == {"osm": "chemin OSM", "chemins_officiels": "chemin {reseau}", "itineraire": "tracé itinéraire",
                      "gpx": "import GPX", "barriere": "clôture et mur", "bloque": "franchissement bloquant",
                      "verifier": "franchissement à vérifier", "jonction": "chemin non raccordé (à vérifier)"}


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


def test_une_couleur_pour_toutes_les_cartographies_nationales():
    """Les chemins des fournisseurs à lots (France, Suisse, Tchéquie, Allemagne, Pologne) se dessinent
    tous avec la couleur de la légende, sur le PC comme sur Android."""
    couleur = next(e["couleur"] for e in g.charger()["entrees"] if e["id"] == "chemins_officiels")
    android = (RACINE / "android" / "app" / "src" / "main" / "java" / "org" / "hike2gpx" / "android" / "CalquesOverlay.kt")
    assert f"0xff{couleur.lstrip('#')}" in android.read_text(encoding="utf-8")
    page = (RACINE / "hike2gpx" / "assets" / "web" / "app.js").read_text(encoding="utf-8")
    assert f'COULEUR_CHEMINS_OFFICIELS = "{couleur}"' in page
    fournisseurs = RACINE / "hike2gpx" / "assets" / "web" / "providers"
    avec_lots = [f for f in sorted(fournisseurs.glob("*.js")) if "paths: {" in f.read_text(encoding="utf-8")]
    assert [f.stem for f in avec_lots] == ["ch", "cz", "de", "fr", "pl"]
    for fichier in avec_lots:
        trace = fichier.read_text(encoding="utf-8").split("draw(", 1)[1].split("\n    },", 1)[0]
        assert "color: couleur" in trace and not re.search(r'color: "#', trace), fichier.name


def test_croix_de_fermeture_presente_sur_la_page():
    html = (RACINE / "hike2gpx" / "assets" / "web" / "index.html").read_text(encoding="utf-8")
    assert re.search(r'id="legendFermer"', html)
