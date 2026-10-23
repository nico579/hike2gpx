from pathlib import Path
from types import SimpleNamespace

from hike2gpx import application, journaux


def test_le_bouton_ouvre_seulement_le_dossier_des_journaux(tmp_path, monkeypatch):
    ouverts = []
    monkeypatch.setattr(journaux, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(journaux.os, "startfile", lambda chemin: ouverts.append(Path(chemin)), raising=False)
    app = application.Application(tmp_path)
    _, post = app.routes()

    resultat = post["ouvrir_journaux"]({})

    attendu = (tmp_path / "logs").resolve()
    assert ouverts == [attendu]
    assert resultat == {"dossier": str(attendu)}
    assert attendu.is_dir()
