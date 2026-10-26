import gzip
import json
import sqlite3

import pytest

from hike2gpx import franchissements as fr, geofabrik, hors_ligne, lot, lot_osm

ZONE = (43.30, 6.00, 43.35, 6.05)       # une seule tuile de 0,05° : 866, 120
TUILE = fr.tuile_du_point(43.32, 6.02)


class Installation:
    def __init__(self):
        self.demandes = []

    def telecharger_segment(self, nom, vers=None):
        self.demandes.append(nom)
        (vers / f"{nom}.rd5").write_bytes(b"rd5 officielle")
        return vers / f"{nom}.rd5"


@pytest.fixture
def mode_en_ligne(monkeypatch):
    """Le code du mode en ligne, simulé : une tuile couverte par un extrait installé."""
    lus = []
    monkeypatch.setattr(geofabrik, "extrait_de_tuile",
                        lambda dossier, i, j: {"id": "paca", "date": "2026-10-25T21:21:21Z"} if (i, j) == TUILE else None)
    monkeypatch.setattr(geofabrik, "regions", lambda dossier: [])
    monkeypatch.setattr(geofabrik, "installes", lambda dossier: [])

    def voies(sud, ouest, nord, est, dossier, **options):
        lus.append((sud, ouest))
        return {"voies": [{"id": 1, "genre": "sentier", "pts": [[43.31, 6.01], [43.32, 6.02]]}],
                "barrieres": [{"id": 2, "nature": "Clôture", "pts": [[43.315, 6.01], [43.315, 6.02]]}],
                "franchissements": []}
    monkeypatch.setattr(fr, "voies_affichables", voies)
    monkeypatch.setattr(fr, "franchissements_tuile", lambda i, j, dossier, **o: [
        {"cle": "a", "statut": "blocked", "raison": "r", "nature": "Clôture", "lat": 43.315, "lon": 6.015,
         "osm": "way/2", "voies": [1], "coupes": [[[6.015, 43.3149], [6.015, 43.3151]]]},
        {"cle": "b", "statut": "passable", "raison": "r", "nature": "Portillon", "lat": 43.316, "lon": 6.016,
         "osm": "node/3", "voies": [1], "coupes": []}])
    return lus


def test_lot_osm_reprend_le_mode_en_ligne(tmp_path, mode_en_ligne):
    installation = Installation()
    manifeste = lot_osm.fabriquer(tmp_path / "donnees", installation, "E5_N40", tmp_path / "lot", zone=ZONE)
    m = json.loads(manifeste.read_text(encoding="utf-8"))
    assert installation.demandes == ["E5_N40"], "la RD5 officielle de brouter.de, pas une compilation"
    assert m["type"] == "osm" and m["zone"] == list(ZONE) and m["sources"]["osm"] == "2026-10-25T21:21:21Z"
    assert {f["nom"] for f in m["fichiers"]} == {"E5_N40.rd5", "franchissements.json.gz", "calques.mbtiles"}
    assert len(mode_en_ligne) == 1, "seules les tuiles couvertes par un extrait sont lues"
    with gzip.open(tmp_path / "lot" / "franchissements.json.gz", "rt", encoding="utf-8") as f:
        assert {x["cle"] for x in json.load(f)} == {"a", "b"}, "tous, avec leurs coupes, comme pour le calcul"
    calque = lot.lire_calque(tmp_path / "lot" / "calques.mbtiles", "osm", *ZONE)
    assert {v["genre"] for v in calque["voies"]} == {"sentier"}
    assert [b["nature"] for b in calque["barrieres"]] and [f["cle"] for f in calque["franchissements"]] == ["a"]


def test_lot_osm_installe_a_part_des_lots_enrichis(tmp_path, mode_en_ligne):
    lot_osm.fabriquer(tmp_path / "donnees", Installation(), "E5_N40", tmp_path / "lot", zone=ZONE)
    h = hors_ligne.HorsLigne(tmp_path / "donnees")
    h.installer(tmp_path / "lot")
    assert (h.segments_osm / "E5_N40.rd5").is_file() and not (h.segments / "E5_N40.rd5").exists()
    assert h.lot_pour(ZONE) is None, "pas d'emprise enrichie : le calcul enrichi n'en dépend pas"
    assert h.lot_du_calque((43.31, 6.01, 43.33, 6.03), "osm")["type"] == "osm"
    assert h.lot_du_calque((43.40, 6.01, 43.42, 6.03), "osm") is None, "hors de la zone fabriquée"


def test_lot_osm_s_arrete_a_la_demande(tmp_path, mode_en_ligne):
    with pytest.raises(lot_osm.Abandon):
        lot_osm.fabriquer(tmp_path / "donnees", Installation(), "E5_N40", tmp_path / "lot", zone=ZONE,
                          continuer=lambda: False)


def attendre(a):
    a._fil_lot.join(10)
    return a.lot_en_cours()


def test_l_application_prepare_et_installe_le_lot(tmp_path, mode_en_ligne, monkeypatch):
    from hike2gpx import application as appli
    a = appli.Application(tmp_path / "donnees")
    monkeypatch.setattr(a, "installation", Installation())
    reponse = a.preparer_lot({"case": "E5_N40", "zone": list(ZONE)})
    assert reponse["lot_en_cours"]["actif"] in (True, False)
    etat = attendre(a)
    assert etat["etape"] == "fini" and not etat["actif"] and "erreur" not in etat
    assert [l["case"] for l in a.lots_hors_ligne()["lots"]] == ["E5_N40"]
    assert not list(a.hors_ligne.racine.glob(".fabrication-*")), "le dossier de travail est effacé"


@pytest.mark.parametrize("corps", [{}, {"case": "../E5_N40"}, {"case": "E5_N40", "zone": [1, 2]}])
def test_preparer_lot_refuse_une_demande_invalide(tmp_path, corps):
    from hike2gpx import application as appli
    assert "erreur" in appli.Application(tmp_path).preparer_lot(corps)


def test_un_seul_lot_a_la_fois_et_arret(tmp_path, mode_en_ligne, monkeypatch):
    import threading
    from hike2gpx import application as appli
    a = appli.Application(tmp_path / "donnees")
    monkeypatch.setattr(a, "installation", Installation())
    libre = threading.Event()
    original = lot_osm.fabriquer

    def lent(*args, **options):
        libre.wait(5)
        return original(*args, **options)
    monkeypatch.setattr(lot_osm, "fabriquer", lent)
    a.preparer_lot({"case": "E5_N40", "zone": list(ZONE)})
    assert a.preparer_lot({"case": "E5_N40"})["erreur"] == "Un lot se prépare déjà."
    a.arreter_lot()
    libre.set()
    etat = attendre(a)
    assert etat["erreur"] == "Fabrication arrêtée." and a.lots_hors_ligne()["lots"] == []


def test_regions_a_installer_pour_les_tuiles_sans_extrait(tmp_path, monkeypatch):
    region = {"id": "provence-alpes-cote-d-azur", "bornes": (42.9, 4.2, 45.2, 7.8)}
    monkeypatch.setattr(geofabrik, "regions", lambda dossier: [region])
    monkeypatch.setattr(geofabrik, "installes", lambda dossier: [])
    monkeypatch.setattr(geofabrik, "extrait_de_tuile", lambda dossier, i, j: None)
    monkeypatch.setattr(geofabrik, "region_de_tuile", lambda regions, i, j: region)
    assert lot_osm.regions_a_installer(tmp_path, ZONE) == [region]
    monkeypatch.setattr(geofabrik, "installes", lambda dossier: [region])
    assert lot_osm.regions_a_installer(tmp_path, ZONE) == []
