import gzip
import json
import time

import pytest
import shapely

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
    # De vraies tuiles : un sentier OSM et un chemin IGN près de Garéoult.
    calques = lot.Calques(dossier / "calques.mbtiles", case, lot.boite_case(case), "")
    couches = {"voies": [(shapely.LineString([(6.000, 43.300), (6.004, 43.302)]), {"id": 1, "genre": "sentier"}),
                         # Dans la même tuile de 0,05° que la vue des essais, mais hors de la vue.
                         (shapely.LineString([(6.040, 43.340), (6.044, 43.342)]), {"id": 2, "genre": "piste"})],
               "troncons": [(shapely.LineString([(6.001, 43.301), (6.003, 43.301)]),
                             {"id": "T-0", "nature": "Chemin"})]}
    for x, y in lot.blocs(43.29, 5.99, 43.36, 6.06):
        calques.ajouter_bloc(x, y, couches)
    calques.fermer()
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
    contenu = bytearray((source / "calques.mbtiles").read_bytes())
    contenu[-1] ^= 0xFF                                             # même taille, autre contenu
    (source / "calques.mbtiles").write_bytes(bytes(contenu))
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


def test_lot_couvrant_une_zone_dans_l_emprise_enrichie(tmp_path):
    h = hors_ligne.HorsLigne(tmp_path / "donnees")
    h.installer(fabriquer_lot(tmp_path / "lot"))
    assert h.lot_couvrant((43.28, 5.99, 43.32, 6.03))["case"] == "E5_N40"
    assert h.lot_couvrant((43.7, 6.9, 43.9, 7.0)) is None, "déborde du Var"
    zone = (43.28, 5.99, 43.32, 6.03)
    assert [f["cle"] for f in h.franchissements(h.lot_couvrant(zone), zone)] == ["a"]


def lot_osm(dossier, case="E5_N40", zone=(43.0, 5.0, 45.0, 10.0), date="2026-10-25T21:21:21Z"):
    """Un lot OSM installable : RD5 officielle, sans emprise enrichie."""
    fabriquer_lot(dossier, case=case)
    (dossier / "manifest.json").unlink()
    lot.ecrire_manifeste(dossier, case, [dossier / f"{case}.rd5", dossier / "franchissements.json.gz",
                                         dossier / "calques.mbtiles"], {"osm": date}, type="osm", zone=list(zone))
    return dossier


def test_un_lot_enrichi_passe_devant_un_lot_osm(tmp_path):
    h = hors_ligne.HorsLigne(tmp_path / "donnees")
    h.installer(lot_osm(tmp_path / "osm", case="E5_N45", zone=(43.0, 5.0, 45.0, 10.0)))
    assert h.lot_couvrant((43.28, 5.99, 43.32, 6.03))["type"] == "osm"
    h.installer(fabriquer_lot(tmp_path / "enrichi"))
    assert h.lot_couvrant((43.28, 5.99, 43.32, 6.03))["case"] == "E5_N40"
    assert h.lot_couvrant((44.5, 8.0, 44.6, 8.1))["type"] == "osm", "hors de l'emprise enrichie"


def test_date_du_lot_et_peremption(tmp_path):
    a = appli.Application(tmp_path / "donnees")
    a.hors_ligne.installer(lot_osm(tmp_path / "vieux", date="2020-01-01T00:00:00Z"))
    assert a.hors_ligne.date_du_lot(a.hors_ligne.lots()[0]) == 1577836800
    assert [(l["type"], l["perime"]) for l in a.lots_hors_ligne()["lots"]] == [("osm", True)]
    a.hors_ligne.installer(lot_osm(tmp_path / "frais", date=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
    assert [l["perime"] for l in a.lots_hors_ligne()["lots"]] == [False]


def sans_reseau(a, monkeypatch):
    """L'application avec un lot installé : tout accès réseau ou fabrication
    échoue, et chaque calcul BRouter est noté (port, franchissements, options)."""
    monkeypatch.setattr(a.installation, "installee", lambda: True)
    monkeypatch.setattr(a.installation, "segment_present", lambda nom: False)    # aucune RD5 officielle

    def interdit(*args, **options):
        raise AssertionError("aucun accès réseau ni fabrication avec un lot installé")
    monkeypatch.setattr(a, "_extrait_automatique", interdit)
    monkeypatch.setattr(a.maison, "preparer", interdit)
    monkeypatch.setattr(franchissements, "franchissements_zone", interdit)
    appels = []

    def calculer(port, points, liste=(), **options):
        appels.append((port, [f["cle"] for f in liste], options))
        return {"type": "Feature", "properties": {"track-length": "900", "filtered ascend": "40"},
                "geometry": {"type": "LineString", "coordinates": [[6.0, 43.302, 0], [6.01, 43.302, 0]]}}
    monkeypatch.setattr(brouter, "calculer", calculer)
    return appels


@pytest.mark.parametrize("ign", [True, False])
def test_itineraire_hors_ligne_sans_reseau_ni_rd5_officielle(tmp_path, monkeypatch, ign):
    a = appli.Application(tmp_path / "donnees")
    a.hors_ligne.installer(fabriquer_lot(tmp_path / "lot"))
    appels = sans_reseau(a, monkeypatch)
    segments_lances = []
    monkeypatch.setattr(a, "moteur_maison", lambda segments: segments_lances.append(segments) or 7)
    resultat = a.itineraire({"points": [[43.302, 6.0], [43.302, 6.01]], "comparer": False, "ign": ign})
    assert resultat["moteur"] == "lot" and "erreur" not in resultat
    assert resultat["lot"]["case"] == "E5_N40" and not resultat["avertissement"]
    assert segments_lances == [a.hors_ligne.segments]
    assert [(port, cles, o["officiels"]) for port, cles, o in appels] == [(7, ["a"], ign)], \
        "les franchissements du lot, filtrés sur la zone, et la coche passée au profil"


def test_itineraire_sur_un_lot_osm(tmp_path, monkeypatch):
    a = appli.Application(tmp_path / "donnees")
    a.hors_ligne.installer(lot_osm(tmp_path / "lot"))
    appels = sans_reseau(a, monkeypatch)
    monkeypatch.setattr(a, "moteur_maison", lambda segments: pytest.fail("pas le profil maison sur une RD5 officielle"))
    monkeypatch.setattr(a, "moteur_lot_osm", lambda: 9)
    resultat = a.itineraire({"points": [[43.302, 6.0], [43.302, 6.01]], "comparer": False})
    assert resultat["moteur"] == "lot" and [port for port, *_ in appels] == [9]
    assert resultat["lot"]["type"] == "osm"
    assert "sans chemins officiels" in resultat["avertissement"], "la coche demandait des chemins absents du lot"
    sans = a.itineraire({"points": [[43.302, 6.0], [43.302, 6.01]], "comparer": False, "ign": False})
    assert not sans["avertissement"]


def test_calques_de_la_page_lus_dans_le_lot(tmp_path, monkeypatch):
    a = appli.Application(tmp_path / "donnees")
    a.hors_ligne.installer(fabriquer_lot(tmp_path / "lot"))

    def interdit(*args, **options):
        raise AssertionError("ni lecture en ligne ni extrait quand un lot couvre la vue")
    monkeypatch.setattr(a, "_extrait_automatique", interdit)
    monkeypatch.setattr(franchissements, "voies_affichables", interdit)
    zone = (43.299, 5.999, 43.303, 6.005)
    osm = a.calque_osm(zone)
    # La page ne redemande rien dans les bornes annoncées : le lot les lit en entier.
    assert osm["bornes"] == franchissements.bornes_zone(*zone)
    assert {v["genre"] for v in osm["voies"]} == {"sentier", "piste"}
    officiel = a.calque_officiel("ign", zone)
    assert {t["nature"] for t in officiel["troncons"]} == {"Chemin"}
    # Hors de l'emprise enrichie, les chemins officiels ne viennent pas du lot.
    assert a.hors_ligne.lot_du_calque((44.5, 7.5, 44.51, 7.51), "bdtopo") is None
    assert a.hors_ligne.lot_du_calque((44.5, 7.5, 44.51, 7.51), "osm")["case"] == "E5_N40"


def test_routes_des_lots(tmp_path):
    a = appli.Application(tmp_path / "donnees")
    get, post = a.routes()
    assert get["hors_ligne"]() == {"lots": []}
    assert post["installer_lot"]({"chemin": str(tmp_path / "absent")})["erreur"]
    reponse = post["installer_lot"]({"chemin": str(fabriquer_lot(tmp_path / "lot"))})
    assert reponse["installe"] == "E5_N40" and reponse["lots"][0]["emprise_enrichie"] == EMPRISE
