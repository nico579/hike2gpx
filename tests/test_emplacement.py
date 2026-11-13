"""Le dossier des données, déplacé aux réglages (emplacement.py ; demande de Nico du 2026-11-13)."""
import pytest

from hike2gpx import application as appli, emplacement

from test_hors_ligne import fabriquer_lot


@pytest.fixture
def standard(tmp_path, monkeypatch):
    """L'emplacement standard des données, ici un dossier d'essai."""
    dossier = tmp_path / "standard" / "hike2gpx-data"
    dossier.mkdir(parents=True)
    monkeypatch.setattr(emplacement, "standard", lambda: dossier)
    monkeypatch.setattr(emplacement, "force", lambda: None)
    return dossier


def test_tout_le_dossier_se_copie_puis_hike2gpx_redemarre_sur_la_copie(tmp_path, standard):
    a = appli.Application(standard)
    a.hors_ligne.installer(fabriquer_lot(tmp_path / "lot"))
    (standard / "mapsforge" / "extraits").mkdir(parents=True)
    (standard / "mapsforge" / "extraits" / "provence.osm.pbf").write_bytes(b"pbf" * 1000)
    a.enregistrer_reglages({"cle_ign": "cle_essai"})
    relances = []
    a.relancer = lambda: relances.append(True)
    assert "lot_en_cours" in a.deplacer_donnees({"dossier": str(tmp_path / "grand disque")})
    a._fil_lot.join(30)
    cible = (tmp_path / "grand disque" / "hike2gpx-data").resolve()
    assert a.lot_en_cours()["deplace"] == str(cible) and relances == [True]
    # Tout a suivi : zones, extraits OSM, préférences ; pas de dossier .part.
    assert (cible / "mapsforge" / "extraits" / "provence.osm.pbf").stat().st_size == 3000
    assert not list(cible.parent.glob("*.part"))
    # Le nouveau processus démarre sur la copie et efface l'ancien dossier, pointeur gardé.
    assert emplacement.dossier_effectif(standard) == cible
    emplacement.nettoyer(standard, cible)
    assert [p.name for p in standard.iterdir()] == [emplacement.POINTEUR]
    b = appli.Application(cible)
    assert [m["case"] for m in b.hors_ligne.lots()] == ["E5_N40"]
    assert b.reglages()["cle_ign"] == "cle_essai" and b.reglages()["dossier_donnees"] == str(cible)
    # Et retour à l'emplacement standard : le pointeur ne garde plus de dossier.
    b.relancer = lambda: None
    assert "lot_en_cours" in b.deplacer_donnees({"dossier": str(standard.parent)})
    b._fil_lot.join(30)
    assert emplacement.dossier_effectif(standard) == standard
    emplacement.nettoyer(standard, standard)
    assert not cible.exists()
    assert [m["case"] for m in appli.Application(standard).hors_ligne.lots()] == ["E5_N40"]


def test_un_disque_debranche_fait_repartir_sur_l_emplacement_standard(tmp_path, standard):
    emplacement.basculer(standard, standard, tmp_path / "cle USB" / "hike2gpx-data")
    assert emplacement.dossier_effectif(standard) == standard


def test_un_dossier_refuse_ne_deplace_rien(tmp_path, standard, monkeypatch):
    a = appli.Application(standard)
    assert "chemin complet" in a.deplacer_donnees({"dossier": "relatif"})["erreur"]
    assert "déjà" in a.deplacer_donnees({"dossier": str(standard.parent)})["erreur"]
    assert "intérieur" in a.deplacer_donnees({"dossier": str(standard / "x")})["erreur"]
    (tmp_path / "occupe" / "hike2gpx-data").mkdir(parents=True)
    (tmp_path / "occupe" / "hike2gpx-data" / "autre").write_text("x")
    assert "existe déjà" in a.deplacer_donnees({"dossier": str(tmp_path / "occupe")})["erreur"]
    monkeypatch.setattr(emplacement, "force", lambda: standard)
    assert "HIKE2GPX_HOME" in a.deplacer_donnees({"dossier": str(tmp_path / "libre")})["erreur"]
    assert not (standard / emplacement.POINTEUR).exists()


def test_une_copie_arretee_ne_laisse_rien(tmp_path):
    source = tmp_path / "hike2gpx-data"
    (source / "hors-ligne" / "fonds").mkdir(parents=True)
    (source / "hors-ligne" / "fonds" / "N43E006-scan25.mbtiles").write_bytes(b"x" * 3_000_000)
    with pytest.raises(emplacement.Abandon):
        emplacement.copier(source, tmp_path / "ailleurs" / "hike2gpx-data", continuer=lambda: False)
    assert (source / "hors-ligne" / "fonds" / "N43E006-scan25.mbtiles").stat().st_size == 3_000_000
    assert list((tmp_path / "ailleurs").iterdir()) == []
