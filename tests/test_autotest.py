"""Auto-test du programme (--self-test-version), éprouvé ici depuis les
sources ; build.py le relance sur le programme construit."""
import os
import shutil

import pytest

from hike2gpx import __main__ as cli, __version__, autotest

JAVA = shutil.which("java") or os.environ.get("JAVA_HOME")


@pytest.mark.skipif(not JAVA, reason="pas de Java sur cette machine")
def test_auto_test_passe_depuis_les_sources(capsys):
    assert autotest.verifier(__version__) == 0
    assert f"hike2gpx {__version__}" in capsys.readouterr().out


def test_auto_test_refuse_une_autre_version_sans_toucher_aux_donnees(monkeypatch, tmp_path):
    # L'installateur de mise à jour lance le nouveau programme avec la version
    # attendue : une autre version, et il refuse de le mettre en place.
    monkeypatch.setenv("HIKE2GPX_HOME", str(tmp_path / "donnees"))
    assert cli.main(["--self-test-version", "0.0.0-autre"]) == 3
    assert not (tmp_path / "donnees").exists()


def test_auto_test_signale_un_fichier_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(autotest.web, "GUI", tmp_path)
    assert autotest.verifier(__version__) == 4


def test_auto_test_signale_java_ou_une_bibliotheque_inutilisables(monkeypatch):
    monkeypatch.setattr(autotest.brouter, "java", lambda: "java")
    monkeypatch.setattr(autotest.subprocess, "run",
                        lambda *a, **o: autotest.subprocess.CompletedProcess(a, 1, "", "Error: could not find libjava"))
    assert autotest.verifier(__version__) == 5
    monkeypatch.setattr(autotest.subprocess, "run",
                        lambda *a, **o: autotest.subprocess.CompletedProcess(a, 0, "", 'openjdk version "21"'))

    def panne():
        raise ImportError("DLL load failed while importing _osmium")
    monkeypatch.setattr(autotest, "bibliotheques", panne)
    assert autotest.verifier(__version__) == 6
    # L'import d'extrait Geofabrik, par le programme relancé en mode import.
    monkeypatch.setattr(autotest, "bibliotheques", lambda: None)

    def import_en_panne():
        raise OSError("Import de l'extrait impossible : No module named 'sqlite3'")
    monkeypatch.setattr(autotest, "import_d_extrait", import_en_panne)
    assert autotest.verifier(__version__) == 7
