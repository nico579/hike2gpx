"""Intégration au bureau par le commun : relance, raccourci, menu de l'icône,
instance unique."""
import sys
from pathlib import Path

import pytest

from hike2gpx import bureau, web


def test_relance_depuis_les_sources_repasse_par_le_module(monkeypatch):
    monkeypatch.setattr(sys, "argv", [r"C:\venv\Scripts\hike2gpx.exe", "serve", "--port", "8800"])
    assert bureau.commande_relance() == [sys.executable, "-m", "hike2gpx", "serve", "--port", "8800"]


def test_raccourci_lance_le_programme_sans_argument(tmp_path):
    lignes = []
    assert bureau.commande_programme()[1:] == ["-m", "hike2gpx"]
    assert bureau.creer_raccourci("fr", tmp_path, simulation=True, dossier_bureau=tmp_path, ecrire=lignes.append) == 0
    assert bureau.ICONE.is_file() and bureau.ICONE.with_suffix(".png").is_file()


def test_langue_du_menu(monkeypatch):
    assert bureau.langue(lambda: "en") == "en"
    monkeypatch.setattr(bureau.locale, "getlocale", lambda: ("French_France", "1252"))
    assert bureau.langue(lambda: None) == "fr"


class Verificateur:
    page_des_releases = "https://github.com/nico579/hike2gpx/releases/latest"

    def __init__(self, info=None):
        self.info = info

    def disponible(self):
        return self.info


def test_menu_commun(monkeypatch):
    ouverts = []
    monkeypatch.setattr(bureau.webbrowser, "open", ouverts.append)
    actions = bureau.actions("http://127.0.0.1:8795/", lambda: None,
                             Verificateur({"version": "0.2.0", "page": "https://exemple/v0.2.0"}),
                             lambda: "fr", Path("."))
    assert actions.version_disponible() == "0.2.0" and actions.langue() == "fr"
    actions.ouvrir()
    actions.mettre_a_jour()
    assert ouverts == ["http://127.0.0.1:8795/", "https://exemple/v0.2.0"]
    assert bureau.actions("u", lambda: None, Verificateur(), lambda: None, Path(".")).version_disponible() is None


def test_relance_rouvre_le_serveur_deja_lance(monkeypatch, tmp_path):
    # Une seule instance : relancé, hike2gpx rouvre la page du serveur en place.
    ouverts = []
    monkeypatch.setattr(web.serveweb, "instance_existante", lambda app, hote, port, timeout=1.0: port == 8797)
    monkeypatch.setattr(web.webbrowser, "open", ouverts.append)
    monkeypatch.setattr(web, "demarrer", lambda *args, **options: pytest.fail("second serveur démarré"))
    web.servir(tmp_path, 8795)
    assert ouverts == ["http://127.0.0.1:8797/"]
