import gzip
import json

import pytest

from hike2gpx import application as appli, brouter, franchissements, hors_ligne, lot

EMPRISE = [42.98, 5.65, 43.81, 6.94]       # le Var
FRANCHISSEMENTS = [
    {"cle": "a", "statut": "blocked", "raison": "r", "nature": "Clôture", "lat": 43.3, "lon": 6.005,
     "voies": [1], "coupes": [[[6.005, 43.29999], [6.005, 43.30001]]]},
    {"cle": "b", "statut": "blocked", "raison": "r", "nature": "Mur", "lat": 44.2, "lon": 7.5,
     "voies": [2], "coupes": [[[7.5, 44.19999], [7.5, 44.20001]]]},
]


def fabriquer_lot(dossier, case="E5_N40", rd5=b"rd5 de la case", **sources):
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / f"{case}.rd5").write_bytes(rd5)
    with gzip.open(dossier / "franchissements.json.gz", "wt", encoding="utf-8") as f:
        json.dump(FRANCHISSEMENTS, f)
    (dossier / "calques.mbtiles").write_bytes(b"tuiles")
    lot.ecrire_manifeste(dossier, case, [dossier / f"{case}.rd5", dossier / "franchissements.json.gz",
                                         dossier / "calques.mbtiles"],
                         sources or {"osm": "2026-10-25T21:21:21Z", "bdtopo": "2026-09-15"},
                         emprise_enrichie=EMPRISE)
    return dossier


def test_installer_range_la_rd5_avec_les_segments(tmp_path):
    h = hors_ligne.HorsLigne(tmp_path / "donnees")
    manifeste = h.installer(fabriquer_lot(tmp_path / "lot"))
    assert manifeste["case"] == "E5_N40"
    assert (h.segments / "E5_N40.rd5").read_bytes() == b"rd5 de la case"
    assert sorted(p.name for p in (h.racine / "E5_N40").iterdir()) == [
        "calques.mbtiles", "franchissements.json.gz", "manifest.json"]
    assert [m["case"] for m in h.lots()] == ["E5_N40"]
    assert not list(h.racine.glob(".*")) and not list(h.segments.glob(".*")), "aucun reste provisoire"


def test_un_lot_altere_n_est_pas_installe(tmp_path):
    source = fabriquer_lot(tmp_path / "lot")
    (source / "calques.mbtiles").write_bytes(b"tuileS")             # même taille, autre contenu
    h = hors_ligne.HorsLigne(tmp_path / "donnees")
    with pytest.raises(hors_ligne.ErreurLot, match="SHA-256"):
        h.installer(source)
    assert h.lots() == []


@pytest.mark.parametrize("champ, valeur, message", [("format", 99, "Format"), ("case", "../E5_N40", "case")])
def test_manifeste_invalide_refuse(tmp_path, champ, valeur, message):
    source = fabriquer_lot(tmp_path / "lot")
    m = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    m[champ] = valeur
    (source / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(hors_ligne.ErreurLot, match=message):
        hors_ligne.HorsLigne(tmp_path / "donnees").installer(source)


def test_une_nouvelle_edition_remplace_l_ancienne(tmp_path):
    h = hors_ligne.HorsLigne(tmp_path / "donnees")
    h.installer(fabriquer_lot(tmp_path / "v1", rd5=b"ancienne"))
    h.installer(fabriquer_lot(tmp_path / "v2", rd5=b"nouvelle"))
    assert (h.segments / "E5_N40.rd5").read_bytes() == b"nouvelle"
    assert len(h.lots()) == 1


def test_lot_pour_une_zone_dans_l_emprise_enrichie(tmp_path):
    h = hors_ligne.HorsLigne(tmp_path / "donnees")
    h.installer(fabriquer_lot(tmp_path / "lot"))
    assert h.lot_pour((43.28, 5.99, 43.32, 6.03))["case"] == "E5_N40"
    assert h.lot_pour((43.7, 6.9, 43.9, 7.0)) is None, "déborde du Var"
    assert h.lot_pour((43.28, 5.99, 43.32, 6.03), source="atkis") is None
    zone = (43.28, 5.99, 43.32, 6.03)
    assert [f["cle"] for f in h.franchissements(h.lot_pour(zone), zone)] == ["a"]


def test_itineraire_hors_ligne_sans_reseau_ni_rd5_officielle(tmp_path, monkeypatch):
    a = appli.Application(tmp_path / "donnees")
    a.hors_ligne.installer(fabriquer_lot(tmp_path / "lot"))
    monkeypatch.setattr(a.installation, "installee", lambda: True)
    monkeypatch.setattr(a.installation, "segment_present", lambda nom: False)    # aucune RD5 officielle

    def interdit(*args, **options):
        raise AssertionError("aucun accès réseau ni fabrication avec un lot installé")
    monkeypatch.setattr(a, "_extrait_automatique", interdit)
    monkeypatch.setattr(a.maison, "preparer", interdit)
    monkeypatch.setattr(franchissements, "franchissements_zone", interdit)
    segments_lances = []
    monkeypatch.setattr(a, "moteur_maison", lambda segments: segments_lances.append(segments) or 7)
    appels = []

    def calculer(port, points, liste=(), **options):
        appels.append((port, [f["cle"] for f in liste]))
        return {"type": "Feature", "properties": {"track-length": "900", "filtered ascend": "40"},
                "geometry": {"type": "LineString", "coordinates": [[6.0, 43.302, 0], [6.01, 43.302, 0]]}}
    monkeypatch.setattr(brouter, "calculer", calculer)
    resultat = a.itineraire({"points": [[43.302, 6.0], [43.302, 6.01]], "comparer": False})
    assert resultat["moteur"] == "lot" and "erreur" not in resultat
    assert segments_lances == [a.hors_ligne.segments]
    assert appels == [(7, ["a"])], "les franchissements du lot, filtrés sur la zone"


def test_routes_des_lots(tmp_path):
    a = appli.Application(tmp_path / "donnees")
    get, post = a.routes()
    assert get["hors_ligne"]() == {"lots": []}
    assert post["installer_lot"]({"chemin": str(tmp_path / "absent")})["erreur"]
    reponse = post["installer_lot"]({"chemin": str(fabriquer_lot(tmp_path / "lot"))})
    assert reponse["installe"] == "E5_N40" and reponse["lots"][0]["emprise_enrichie"] == EMPRISE
