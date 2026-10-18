import pytest

from hike2gpx import application as appli, brouter, franchissements


def trace(*points_lat_lon, longueur="1234", montee="56"):
    return {"type": "Feature", "properties": {"track-length": longueur, "filtered ascend": montee},
            "geometry": {"type": "LineString", "coordinates": [[lon, lat, 100.0] for lat, lon in points_lat_lon]}}


def test_zone_autour_garde_une_marge_d_un_kilometre():
    sud, ouest, nord, est = appli.zone_autour([(43.30, 6.00), (43.31, 6.02)])
    assert sud == pytest.approx(43.29) and nord == pytest.approx(43.32)
    assert ouest < 5.99 and est > 6.03


def test_contient_et_union():
    zone = (43.0, 6.0, 43.1, 6.1)
    assert appli.contient(zone, (43.01, 6.01, 43.09, 6.09))
    assert not appli.contient(zone, (43.01, 6.01, 43.1, 6.09))
    assert appli.union(zone, (42.9, 6.05, 43.05, 6.2)) == (42.9, 6.0, 43.1, 6.2)


@pytest.mark.parametrize("brut", [None, [], [[43, 6]], [[43, 6], [95, 6]], [[43, 6], ["43", 6]],
                                  [[43, 6]] * (appli.POINTS_MAX + 1)])
def test_points_invalides(brut):
    with pytest.raises(ValueError):
        appli.valider_points(brut)


def coupe_nord_sud(lat, lon, demi_m=0.5):
    d = demi_m / franchissements.M_PAR_DEGRE
    return [[lon, lat - d], [lon, lat + d]]


def test_sur_le_trace_seulement_si_le_trace_coupe_la_coupe():
    coords = trace((43.0, 6.0), (43.0, 6.01))["geometry"]["coordinates"]
    passe = {"cle": "a", "statut": "uncertain", "raison": "r", "nature": "Portail", "lat": 43.0, "lon": 6.005,
             "osm": "node/1", "coupes": [coupe_nord_sud(43.0, 6.005)]}
    # Une voie voisine, à 1,3 m du tracé : sa coupe ne le touche pas.
    voisine = {**passe, "cle": "b", "statut": "blocked", "lat": 43.0 + 1.3 / franchissements.M_PAR_DEGRE,
               "coupes": [coupe_nord_sud(43.0 + 1.3 / franchissements.M_PAR_DEGRE, 6.005)]}
    [f] = appli.sur_le_trace(coords, [passe, voisine])
    assert f["cle"] == "a" and f["distance_m"] == pytest.approx(406, abs=2)


def test_reglages_cle_ign(tmp_path):
    a = appli.Application(tmp_path)
    assert a.reglages() == {"cle_ign": ""}
    assert a.enregistrer_reglages({"cle_ign": " ign_scan_ws "}) == {"cle_ign": "ign_scan_ws"}
    assert appli.Application(tmp_path).reglages() == {"cle_ign": "ign_scan_ws"}
    assert "erreur" in a.enregistrer_reglages({"cle_ign": "<script>"})


@pytest.fixture
def simulee(tmp_path, monkeypatch):
    a = appli.Application(tmp_path)
    monkeypatch.setattr(a.installation, "installee", lambda: True)
    monkeypatch.setattr(a.installation, "segment_present", lambda nom: True)
    monkeypatch.setattr(a, "moteur", lambda: 1)
    zones, appels = [], []
    bloquant = {"cle": "x", "statut": "blocked", "raison": "r", "nature": "Clôture",
                "lat": 43.3, "lon": 6.005, "osm": "way/9", "voies": [1], "coupes": [coupe_nord_sud(43.3, 6.005)]}

    def zone(*args):
        zones.append(args[:4])
        return [bloquant]

    monkeypatch.setattr(franchissements, "franchissements_zone", zone)
    return a, zones, appels, bloquant


def test_itineraire_et_comparaison(simulee, monkeypatch):
    a, zones, appels, bloquant = simulee

    def calculer(port, points, liste=(), **options):
        appels.append((options.get("profil", "hike2gpx"), len(liste)))
        if options.get("profil") == "hiking-mountain":
            return trace((43.3, 6.0), (43.3, 6.01), longueur="800")
        return trace((43.3, 6.0), (43.302, 6.005), (43.3, 6.01))

    monkeypatch.setattr(brouter, "calculer", calculer)
    r = a.itineraire({"points": [[43.3, 6.0], [43.3, 6.01]]})
    assert r["longueur_m"] == 1234 and r["denivele_m"] == 56
    assert appels == [("hike2gpx", 1), ("hiking-mountain", 0)]
    assert [f["cle"] for f in r["naif_traverse"]] == ["x"] and r["sur_le_trace"] == []
    assert len(zones) == 1


def test_itineraire_elargit_la_zone_quand_le_trace_en_sort(simulee, monkeypatch):
    a, zones, _, _ = simulee
    monkeypatch.setattr(brouter, "calculer", lambda port, points, liste=(), **o:
                        trace((43.3, 6.0), (43.35, 6.005), (43.3, 6.01)))
    r = a.itineraire({"points": [[43.3, 6.0], [43.3, 6.01]], "comparer": False})
    assert "erreur" not in r and len(zones) == 2 and zones[1][2] > 43.35


def test_itineraire_s_arrete_si_les_barrieres_sont_inconnues(simulee, monkeypatch):
    a, _, _, _ = simulee

    def panne(*args):
        raise franchissements.ErreurDonnees("Overpass ne répond pas : barrières non vérifiées.")

    monkeypatch.setattr(franchissements, "franchissements_zone", panne)
    monkeypatch.setattr(brouter, "calculer", lambda *a, **o: pytest.fail("calcul sans barrières"))
    assert "barrières non vérifiées" in a.itineraire({"points": [[43.3, 6.0], [43.3, 6.01]]})["erreur"]


def test_itineraire_signale_les_donnees_manquantes(simulee, monkeypatch):
    a, _, _, _ = simulee
    monkeypatch.setattr(a.installation, "segment_present", lambda nom: False)
    r = a.itineraire({"points": [[43.3, 6.0], [43.3, 6.01]]})
    assert r["segments_manquants"] == ["E5_N40"]


def test_routes_init_annonce_l_application(tmp_path):
    get, post = appli.Application(tmp_path).routes()
    assert get["init"]()["app"] == "hike2gpx"
    assert set(post) == {"itineraire", "reglages", "segment", "moteur"}
    assert "erreur" in post["segment"]({"nom": "../x"})
