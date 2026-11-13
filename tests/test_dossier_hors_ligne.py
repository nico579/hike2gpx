"""Le dossier des cartes et des zones hors ligne, choisi aux réglages (demande de Nico du 2026-11-13)."""
import os

import pytest

from hike2gpx import application as appli, hors_ligne

from test_hors_ligne import fabriquer_lot


def attendre(a):
    a._fil_lot.join(30)
    return a.lot_en_cours()


@pytest.mark.parametrize("autre_disque", [False, True])
def test_les_donnees_hors_ligne_se_deplacent_et_l_application_les_suit(tmp_path, monkeypatch, autre_disque):
    a = appli.Application(tmp_path / "donnees")
    a.hors_ligne.installer(fabriquer_lot(tmp_path / "lot"))
    if autre_disque:
        # Un autre disque : le renommage échoue, la copie fichier par fichier prend le relais.
        renommer = os.rename

        def refus(source, cible):
            if not str(source).endswith(".part"):      # la source, pas le dossier provisoire final
                raise OSError(18, "Invalid cross-device link")
            renommer(source, cible)
        monkeypatch.setattr(hors_ligne.os, "rename", refus)
    cible = tmp_path / "grand disque"
    assert "lot_en_cours" in a.deplacer_hors_ligne({"dossier": str(cible)})
    etat = attendre(a)
    assert etat["etape"] == "fini" and etat["deplace"] == str(cible.resolve())
    assert not (tmp_path / "donnees" / "hors-ligne").exists(), "rien ne reste à l'ancien endroit"
    assert not list(cible.glob("*.part"))
    assert a.hors_ligne.racine == cible.resolve() / "hors-ligne"
    assert [m["case"] for m in a.hors_ligne.lots()] == ["E5_N40"]
    assert (a.hors_ligne.segments / "E5_N40.rd5").is_file()
    assert a.partage.hors_ligne is a.hors_ligne
    assert a.reglages()["dossier_hors_ligne"] == str(cible.resolve())
    # Au lancement suivant, l'application les retrouve là.
    assert [m["case"] for m in appli.Application(tmp_path / "donnees").hors_ligne.lots()] == ["E5_N40"]


def test_un_dossier_refuse_ne_deplace_rien(tmp_path):
    a = appli.Application(tmp_path / "donnees")
    a.hors_ligne.installer(fabriquer_lot(tmp_path / "lot"))
    assert "chemin complet" in a.deplacer_hors_ligne({"dossier": "relatif"})["erreur"]
    assert "déjà" in a.deplacer_hors_ligne({"dossier": str(tmp_path / "donnees")})["erreur"]
    assert "intérieur" in a.deplacer_hors_ligne({"dossier": str(tmp_path / "donnees" / "hors-ligne" / "x")})["erreur"]
    (tmp_path / "occupe" / "hors-ligne").mkdir(parents=True)
    assert "existe déjà" in a.deplacer_hors_ligne({"dossier": str(tmp_path / "occupe")})["erreur"]
    assert [m["case"] for m in a.hors_ligne.lots()] == ["E5_N40"]


def test_une_copie_arretee_laisse_les_donnees_en_place(tmp_path, monkeypatch):
    source = tmp_path / "hors-ligne"
    (source / "fonds").mkdir(parents=True)
    (source / "fonds" / "N43E006-scan25.mbtiles").write_bytes(b"x" * 3_000_000)
    monkeypatch.setattr(hors_ligne.os, "rename", lambda *args: (_ for _ in ()).throw(OSError("autre disque")))
    with pytest.raises(hors_ligne.Abandon):
        hors_ligne.deplacer(source, tmp_path / "ailleurs" / "hors-ligne", continuer=lambda: False)
    assert (source / "fonds" / "N43E006-scan25.mbtiles").stat().st_size == 3_000_000
    assert not (tmp_path / "ailleurs" / "hors-ligne").exists()
    assert not (tmp_path / "ailleurs" / "hors-ligne.part").exists()
    assert os.listdir(tmp_path / "ailleurs") == []
