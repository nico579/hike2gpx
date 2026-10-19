import math
import time

import pytest
from nico579_commons import atomique

from hike2gpx import bdtopo, brouter, franchissements as fr, maison

I, J = 866, 120             # tuile 43,30-43,35 N, 6,00-6,05 E
LAT0, LON0 = 43.32, 6.02
KX = fr.M_PAR_DEGRE * math.cos(math.radians(LAT0))


def geo(x, y):
    return LAT0 + y / fr.M_PAR_DEGRE, LON0 + x / KX


def voie(wid, premier_noeud, *points, **tags):
    return {"type": "way", "id": wid, "nodes": list(range(premier_noeud, premier_noeud + len(points))),
            "geometry": [dict(zip(("lat", "lon"), geo(x, y))) for x, y in points], "tags": tags}


def cloture_et_sentier():
    """Une clôture est-ouest et un sentier OSM venu du nord qui s'y arrête."""
    return [voie(1, 10, (-50, 0), (50, 0), barrier="fence"), voie(2, 20, (0, 100), (0, 0), highway="path")]


def sentier_ign_sud():
    """Le tronçon IGN qui arrive du sud au même point : le raccord traverse la clôture."""
    return [{"id": "T1-0", "nature": "Sentier", "acces_pieton": None, "pts": [list(geo(0, -100)), list(geo(0, 0))]}]


def ecrire_tuile(dossier, i, j, elements, troncons, date=None):
    date = time.time() if date is None else date
    atomique.ecrire_json(dossier / "overpass" / f"v{fr.VERSION_DONNEES}_{i}_{j}.json",
                         {"version": fr.VERSION_DONNEES, "fetched_at": date, "bornes": fr.bornes_tuile(i, j),
                          "elements": elements})
    atomique.ecrire_json(dossier / "bdtopo" / f"v{bdtopo.VERSION_CACHE}_{i}_{j}.json",
                         {"version": bdtopo.VERSION_CACHE, "fetched_at": date, "troncons": troncons})


@pytest.fixture
def tuiles(tmp_path, monkeypatch):
    """Tuiles maison sans Java : la fabrication BRouter est simulée, la
    fusion, le PBF et l'analyse sont les vrais."""
    inst = brouter.Installation(tmp_path)
    monkeypatch.setattr(inst, "preparer_maison", lambda: None)
    fabriquees = []

    def fabriquer(installation, pbf, dossier):
        assert pbf.stat().st_size > 0
        (dossier / "segments").mkdir(parents=True)
        fabriquees.append(dossier.name)
        return dossier / "segments"

    monkeypatch.setattr(brouter, "fabriquer_tuiles", fabriquer)
    return maison.TuilesMaison(inst, tmp_path), fabriquees


def test_fabrique_une_fois_puis_reprend_et_coupe_le_raccord(tuiles, tmp_path):
    tm, fabriquees = tuiles
    ecrire_tuile(tmp_path, I, J, cloture_et_sentier(), sentier_ign_sud())
    segments, liste = tm.preparer([(I, J)])
    assert fabriquees == ["fabrication-1"] and segments == tm.racine / "fabrication-1" / "segments"
    # Audit B16 : ni OSM seul ni le chemin IGN seul ne traversent la clôture,
    # leur raccord si ; l'analyse du réseau fusionné le voit.
    assert fr.analyser(cloture_et_sentier()) == []
    assert [f["statut"] for f in liste] == ["blocked"]
    assert tm.preparer([(I, J)]) == (segments, liste) and fabriquees == ["fabrication-1"]
    assert tm.etat()["chemins_ign"] == 1


def test_tuile_relue_refait_la_fabrication_et_efface_l_ancienne(tuiles, tmp_path):
    tm, fabriquees = tuiles
    ecrire_tuile(tmp_path, I, J, cloture_et_sentier(), sentier_ign_sud())
    tm.preparer([(I, J)])
    ecrire_tuile(tmp_path, I, J, cloture_et_sentier(), sentier_ign_sud(), date=time.time() + 1)
    segments, _ = tm.preparer([(I, J)])
    assert fabriquees == ["fabrication-1", "fabrication-2"] and segments.parent.name == "fabrication-2"
    assert not (tm.racine / "fabrication-1").exists()


def test_zone_nouvelle_ajoutee_aux_anciennes(tuiles, tmp_path):
    tm, fabriquees = tuiles
    ecrire_tuile(tmp_path, I, J, cloture_et_sentier(), sentier_ign_sud())
    ecrire_tuile(tmp_path, I, J + 1, [], [])
    tm.preparer([(I, J)])
    _, liste = tm.preparer([(I, J + 1)])
    assert len(fabriquees) == 2 and set(tm.etat()["tuiles"]) == {f"{I}_{J}", f"{I}_{J + 1}"}
    assert liste == []          # le franchissement est dans l'autre tuile
    assert len(tm.preparer([(I, J), (I, J + 1)])[1]) == 1 and len(fabriquees) == 2


def test_union_bornee_repart_de_la_zone_demandee(tuiles, tmp_path, monkeypatch):
    # Sans borne, chaque zone nouvelle refaisait tout l'historique des zones vues.
    tm, fabriquees = tuiles
    monkeypatch.setattr(tm, "UNION_MAX", 1)
    ecrire_tuile(tmp_path, I, J, cloture_et_sentier(), sentier_ign_sud())
    ecrire_tuile(tmp_path, I, J + 1, [], [])
    tm.preparer([(I, J)])
    tm.preparer([(I, J + 1)])
    assert len(fabriquees) == 2 and set(tm.etat()["tuiles"]) == {f"{I}_{J + 1}"}


def test_bdtopo_absente_hors_ligne(tuiles, tmp_path):
    tm, fabriquees = tuiles
    ecrire_tuile(tmp_path, I, J, cloture_et_sentier(), sentier_ign_sud())
    (tmp_path / "bdtopo" / f"v{bdtopo.VERSION_CACHE}_{I}_{J}.json").unlink()
    with pytest.raises(fr.ErreurDonnees):
        tm.preparer([(I, J)], en_ligne=False)
    assert fabriquees == []
