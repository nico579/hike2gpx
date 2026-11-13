import logging
import os
import time
from pathlib import Path

import pytest

from hike2gpx import application as appli, brouter, franchissements, geofabrik


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
    assert a.reglages() == {"cle_ign": "", "renouvellement_jours": 30, "dossier_donnees": str(tmp_path)}
    assert a.enregistrer_reglages({"cle_ign": " cle_essai-1 "}) == {"cle_ign": "cle_essai-1", "renouvellement_jours": 30, "dossier_donnees": str(tmp_path)}
    assert appli.Application(tmp_path).reglages() == {"cle_ign": "cle_essai-1", "renouvellement_jours": 30, "dossier_donnees": str(tmp_path)}
    assert a.enregistrer_reglages({"cle_ign": "cle_essai-1", "renouvellement_jours": 45})["renouvellement_jours"] == 45
    assert "erreur" in a.enregistrer_reglages({"cle_ign": "cle_essai-1", "renouvellement_jours": 0})
    assert "erreur" in a.enregistrer_reglages({"cle_ign": "<script>"})


@pytest.fixture(autouse=True)
def sans_index_geofabrik(monkeypatch):
    """Le pays de la vue se lit dans l'index de Geofabrik : ici, aucune
    région, donc aucun réseau. Les essais du pays fournissent les leurs."""
    monkeypatch.setattr(geofabrik, "regions", lambda dossier, **options: [])


def test_extrait_identifie_le_pays_au_centre_de_la_carte(tmp_path, monkeypatch):
    def region(identifiant, sud, ouest, nord, est):
        anneau = [(ouest, sud), (est, sud), (est, nord), (ouest, nord), (ouest, sud)]
        return {"id": identifiant, "bornes": (sud, ouest, nord, est), "polygones": [[anneau]]}

    zones = [region("spain", 36, -10, 44, 4), region("switzerland", 45, 5, 48, 11),
             region("austria", 46, 9, 49, 17), region("germany", 50, 10, 54, 14),
             region("netherlands", 50, 3, 54, 8),
             region("norway", 58, 9, 62, 12), region("luxembourg", 49, 5, 50, 7),
             region("us", 36, -121, 38, -118)]
    monkeypatch.setattr(geofabrik, "regions", lambda dossier, **options: zones)
    app = appli.Application(tmp_path)
    assert app.extrait((40.4, -3.8, 40.5, -3.6))["pays"] == "es"
    assert app.extrait((46.7, 7.9, 46.9, 8.1))["pays"] == "ch"
    assert app.extrait((48.1, 16.3, 48.3, 16.5))["pays"] == "at"
    assert app.extrait((52.0, 11.0, 52.2, 11.2))["pays"] == "de"
    assert app.extrait((52.0, 5.0, 52.2, 5.2))["pays"] == "nl"
    assert app.extrait((59.9, 10.7, 60.0, 10.8))["pays"] == "no"
    assert app.extrait((49.6, 6.1, 49.7, 6.2))["pays"] == "lu"
    assert app.extrait((37.7, -119.7, 37.8, -119.5))["pays"] == "us"
    assert "pays" not in app.extrait((52, 20, 52.1, 20.1))


@pytest.fixture
def simulee(tmp_path, monkeypatch):
    a = appli.Application(tmp_path)
    monkeypatch.setattr(a.installation, "installee", lambda: True)
    monkeypatch.setattr(a.installation, "segment_present", lambda nom: True)
    monkeypatch.setattr(a, "moteur", lambda: 1)
    monkeypatch.setattr(a, "moteur_lot_osm", lambda: 1)
    zones, appels = [], []
    bloquant = {"cle": "x", "statut": "blocked", "raison": "r", "nature": "Clôture",
                "lat": 43.3, "lon": 6.005, "osm": "way/9", "voies": [1], "coupes": [coupe_nord_sud(43.3, 6.005)]}
    # Une zone de routage OSM installée sur toute la case : depuis la 0.9.31, tout
    # calcul part d'un lot, sans rien lire à la volée.
    lot = {"case": "E5_N40", "type": "osm", "zone": [40.0, 5.0, 45.0, 10.0],
           "sources": {"osm": "2026-11-01T00:00:00Z"}, "fichiers": []}
    monkeypatch.setattr(a.hors_ligne, "lots", lambda: [lot])
    monkeypatch.setattr(a.hors_ligne, "lot_couvrant", lambda zone: lot)

    def zone(manifeste, bornes):
        zones.append(tuple(bornes))
        return [bloquant]

    monkeypatch.setattr(a.hors_ligne, "franchissements", zone)
    return a, zones, appels, bloquant


ENTETE = ["Longitude", "Latitude", "Elevation", "Distance", "CostPerKm", "ElevCost", "TurnCost", "NodeCost",
          "InitialCost", "WayTags", "NodeTags", "Time", "Energy"]
DETOUR = [(43.3, 6.0), (43.302, 6.003), (43.302, 6.007), (43.3, 6.01)]


def trace_messages(points, morceaux):
    """Tracé avec les messages de BRouter : morceaux = [(rang du dernier
    point, longueur, étiquettes)], comme le serveur les écrit."""
    t = trace(*points)
    t["properties"]["messages"] = [ENTETE] + [
        [str(round(points[k][1] * 1e6)), str(round(points[k][0] * 1e6)), "-8192", str(longueur),
         "0", "0", "0", "0", "0", tags, "", "0", "0"] for k, longueur, tags in morceaux]
    return t


def test_portions_ign_lues_dans_les_messages():
    t = trace_messages(DETOUR, [(1, 300, "highway=path"), (2, 324, "highway=path hike2gpx=ign"),
                                (3, 300, "highway=track")])
    # La source est toujours dite, IGN compris : un lot frontalier en mêle plusieurs.
    assert appli.portions_ign(t) == [{"debut_m": 300, "longueur_m": 324, "source": "ign",
                                      "coords": [[43.302, 6.003], [43.302, 6.007]]}]
    # Deux morceaux IGN de suite ne font qu'une portion.
    t = trace_messages(DETOUR, [(1, 300, "highway=path hike2gpx=ign"), (2, 324, "foot=private hike2gpx=ign"),
                                (3, 300, "highway=track")])
    [p] = appli.portions_ign(t)
    assert (p["debut_m"], p["longueur_m"], len(p["coords"])) == (0, 624, 3)
    assert appli.portions_ign(trace(*DETOUR)) == []


def test_portions_atkis_sont_signalees_a_verifier():
    t = trace_messages(DETOUR, [(1, 300, "highway=path"),
                                (2, 324, "highway=path hike2gpx=atkis"),
                                (3, 300, "highway=track")])
    [portion] = appli.portions_ign(t)
    assert portion["source"] == "atkis" and portion["longueur_m"] == 324
    [entree] = appli.entrees_ign([portion])
    assert entree["cle"] == "atkis-0"
    assert "ATKIS" in entree["nature"] and "accès à vérifier" in entree["raison"]


def test_itineraire_sans_les_chemins_ign(simulee, monkeypatch):
    a, zones, _, _ = simulee
    monkeypatch.setattr(brouter, "calculer", lambda port, points, liste=(), **o: trace(*DETOUR))
    r = a.itineraire({"points": [[43.3, 6.0], [43.3, 6.01]], "ign": False, "comparer": False})
    assert r["moteur"] == "lot" and r["avertissement"] is None and len(zones) == 1


def test_itineraire_refuse_s_il_traverse_encore_un_blocage(simulee, monkeypatch):
    # Audit B10 et amélioration 2 : quelle qu'en soit la cause, un tracé qui
    # passe une coupe bloquante n'est jamais rendu comme un itinéraire.
    a, _, _, _ = simulee
    monkeypatch.setattr(brouter, "calculer", lambda port, points, liste=(), **o: trace((43.3, 6.0), (43.3, 6.01)))
    r = a.itineraire({"points": [[43.3, 6.0], [43.3, 6.01]], "comparer": False})
    assert r["erreur"].startswith("Itinéraire refusé") and [f["cle"] for f in r["traverses"]] == ["x"]


def test_mode_strict_refuse_un_passage_a_verifier_sur_le_trace(simulee, monkeypatch):
    a, _, _, bloquant = simulee
    incertain = {**bloquant, "cle": "y", "statut": "uncertain"}
    monkeypatch.setattr(a.hors_ligne, "franchissements", lambda manifeste, zone: [incertain])
    monkeypatch.setattr(brouter, "calculer", lambda port, points, liste=(), **o: trace((43.3, 6.0), (43.3, 6.01)))
    points = [[43.3, 6.0], [43.3, 6.01]]
    assert "erreur" not in a.itineraire({"points": points, "comparer": False})
    assert a.itineraire({"points": points, "comparer": False, "strict": True})["erreur"].startswith("Itinéraire refusé")


def test_zone_trop_etendue_refusee_avant_tout_chargement(simulee, monkeypatch):
    # Amélioration 3 : sans borne, des points éloignés lançaient la lecture
    # et la fusion de centaines de tuiles.
    a, zones, _, _ = simulee
    monkeypatch.setattr(brouter, "calculer", lambda *args, **o: pytest.fail("calcul lancé"))
    r = a.itineraire({"points": [[43.0, 5.5], [43.9, 6.4]]})
    assert "trop étendue" in r["erreur"] and zones == []


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


REGION_PACA = {"id": "provence-alpes-cote-d-azur", "nom": "Provence Alpes-Cote-d'Azur",
               "pbf": "https://download.geofabrik.de/europe/france/provence-alpes-cote-d-azur-latest.osm.pbf",
               "bornes": (42.9, 4.2, 45.2, 7.8),
               "polygones": [[[(4.2, 42.9), (7.8, 42.9), (7.8, 45.2), (4.2, 45.2), (4.2, 42.9)]]]}


def test_extrait_dit_si_la_vue_est_hors_de_france(tmp_path, monkeypatch):
    # Le contour de la France chez Geofabrik, comme pour les autres pays : plus
    # d'OSM France, dont les extraits ne servaient qu'au calcul à la volée.
    france = {**REGION_PACA, "id": "france", "bornes": (41.0, -5.0, 51.0, 10.0),
              "polygones": [[[(-5.0, 41.0), (10.0, 41.0), (10.0, 51.0), (-5.0, 51.0), (-5.0, 41.0)]]]}
    monkeypatch.setattr(geofabrik, "regions", lambda dossier, **options: [france])
    a = appli.Application(tmp_path)
    assert a.extrait((43.30, 6.00, 43.34, 6.08)) == {"brouter": None, "pays": "fr", "hors_france": False}
    assert a.extrait((40.40, -3.73, 40.43, -3.68))["hors_france"] is True
    monkeypatch.setattr(geofabrik, "regions", lambda dossier, **options: [])
    assert "hors_france" not in a.extrait((43.30, 6.00, 43.34, 6.08)), "index pas encore lu : on ne sait pas"


def test_le_moteur_brouter_s_installe_de_lui_meme(simulee, monkeypatch):
    # Le moteur absent : il s'installe en tâche de fond, et le calcul le dit.
    a, _, _, _ = simulee
    installe = []
    monkeypatch.setattr(a.installation, "installee", lambda: bool(installe))
    monkeypatch.setattr(a.installation, "installer", lambda: installe.append(True))
    r = a.itineraire({"points": [[43.3, 6.0], [43.3, 6.01]]})
    assert r["moteur_absent"] is True and r["brouter_en_cours"] == {"moteur": True, "segments": []}
    a._fil_brouter.join(5)
    assert installe == [True] and a.extrait(None)["brouter"] is None
    assert a.installer_moteur() == {"brouter_en_cours": None}


@pytest.mark.parametrize("requete, attendu", [
    ({"s": ["43.3"], "w": ["6.0"], "n": ["43.35"], "e": ["6.05"]}, (43.3, 6.0, 43.35, 6.05)),
    ({"s": ["43.35"], "w": ["6.0"], "n": ["43.3"], "e": ["6.05"]}, None),
    ({"s": ["43.3"], "w": ["6.0"], "n": ["43.35"]}, None),
    ({"s": ["nan"], "w": ["6.0"], "n": ["43.35"], "e": ["6.05"]}, None),
    ({"s": ["x"], "w": ["6.0"], "n": ["43.35"], "e": ["6.05"]}, None),
])
def test_lire_zone(requete, attendu):
    assert appli.lire_zone(requete) == attendu


def test_calques_refusent_une_zone_invalide(tmp_path):
    assert "invalide" in appli.Application(tmp_path).calque_osm(None)["erreur"]


def test_une_vue_plus_ancienne_arrivee_apres_est_refusee_d_emblee(tmp_path):
    # Calque figé du 2026-10-20 : une requête plus ancienne de la page, arrivée
    # au serveur après la plus récente, passait pour la vue en cours. La page
    # date ses vues, et le serveur refuse les plus anciennes.
    a = appli.Application(tmp_path)
    vue = (43.30, 6.00, 43.34, 6.08)
    assert a.calque_osm(vue, 1760000000002.5).get("code") != "vue_remplacee"
    assert a.calque_osm(vue, 1760000000001.0)["code"] == "vue_remplacee"
    assert a.calque_osm(vue, 1760000000003.0).get("code") != "vue_remplacee"


def test_arreter_calques_ne_touche_que_ceux_que_la_page_masque(tmp_path):
    a = appli.Application(tmp_path)
    assert a.arreter_calques({"calques": ["bdtopo"]}) == {"arretes": ["bdtopo"]}
    assert a._vues["bdtopo"] == 1 and all(v == 0 for k, v in a._vues.items() if k != "bdtopo")
    assert set(a.arreter_calques({})["arretes"]) == set(a._vues)


def test_route_denivele(tmp_path, monkeypatch):
    from hike2gpx import denivele
    a = appli.Application(tmp_path)
    monkeypatch.setattr(denivele, "calculer", lambda coordonnees, dossier: {"montee_m": 523, "dossier": dossier})
    assert a.denivele({"coordonnees": [[6.0, 43.3], [6.01, 43.3]]}) == {"montee_m": 523, "dossier": tmp_path}

    def invalide(coordonnees, dossier):
        raise ValueError("Tracé invalide.")

    monkeypatch.setattr(denivele, "calculer", invalide)
    assert a.denivele({}) == {"erreur": "Tracé invalide."}


@pytest.mark.zones_reelles
def test_disponibilite_ne_compte_que_la_zone_de_routage(tmp_path, monkeypatch):
    # Nico, 2026-11-13 : « le message n'est pas à jour » ; l'infobulle énumérait encore
    # Overpass et les extraits OSM, quand un tracé ne part plus que d'une zone de routage.
    a = appli.Application(tmp_path)
    zone = (43.3, 6.0, 43.31, 6.01)
    monkeypatch.setattr(a.installation, "installee", lambda: True)
    assert a.disponibilite(zone) == {"pret": False, "source": None, "attente": "zone_absente",
                                    "details": {"lot": {"nom": "E5_N40", "etat": "absent"}}}
    a._lot = {"actif": True, "case": "E5_N40"}
    assert a.disponibilite(zone)["details"]["lot"]["etat"] == "preparation"
    a._lot = {"actif": False}
    monkeypatch.setattr(a, "_cases_sans_lot", lambda zone: [])
    monkeypatch.setattr(a, "_cases_sans_calques", lambda zone: ["E5_N40"])
    d = a.disponibilite(zone)
    assert d["pret"] is True and d["details"]["lot"]["etat"] == "simple", "la zone simple trace"
    monkeypatch.setattr(a, "_cases_sans_calques", lambda zone: [])
    assert a.disponibilite(zone) == {"pret": True, "source": "lot", "nom": "E5_N40",
                                    "details": {"lot": {"nom": "E5_N40", "etat": "disponible"}}}
    monkeypatch.setattr(a.installation, "installee", lambda: False)
    assert a.disponibilite(zone)["attente"] == "moteur"
    assert a.disponibilite_parcours({"points": [[43.3, 6], [43.31, 6.01]]})["attente"] == "moteur"
    assert a.disponibilite(None)["attente"] == "zone"


def test_routes_init_annonce_l_application(tmp_path):
    get, post = appli.Application(tmp_path).routes()
    assert get["init"]()["app"] == "hike2gpx"
    assert {"osm", "bdtopo", "extrait"} <= set(get)
    # Plus de téléchargement à la demande depuis la carte (tuile, extrait) : tout
    # part de lui-même ; seuls les réglages actualisent ou vident (donnees).
    # installer_lot, preparer_lot, arreter_lot, telecharger_lot : les lots de
    # case pour le hors ligne (hors_ligne.py, fabrication.py, depot.py) ;
    # preparer_fond : le fond de carte d'une case ou d'une vue (fonds.py) ;
    # partage : ouvrir ou fermer le partage au téléphone (partage.py) ;
    # supprimer_case : retirer de l'ordinateur le lot et les fonds d'une case.
    assert set(post) == {"itineraire", "disponibilite", "reglages", "moteur", "denivele", "communes", "langue",
                         "arreter_calques", "donnees", "ouvrir_journaux", "installer_lot", "preparer_lot",
                         "arreter_lot", "telecharger_lot", "preparer_fond", "partage", "supprimer_case", "supprimer_fond", "zone_planification", "deplacer_donnees"}


def test_langue_choisie_gardee_dans_les_preferences(tmp_path):
    # /api/langue : le choix FR / EN du commun, à côté de la clé IGN.
    a = appli.Application(tmp_path)
    a.enregistrer_reglages({"cle_ign": "cle_test"})
    get, post = a.routes()
    assert get["langue"]()["code"] is None
    assert post["langue"]({"code": "en"})["enregistre"]
    autre = appli.Application(tmp_path)
    assert autre.routes()[0]["langue"]()["code"] == "en" and autre.reglages() == {"cle_ign": "cle_test", "renouvellement_jours": 30, "dossier_donnees": str(tmp_path)}


def test_progression_publiee_pendant_le_calcul_puis_effacee(simulee, monkeypatch):
    # La barre de progression de la page lit /api/progression pendant le calcul.
    a, _, _, _ = simulee
    vues = []

    def calculer(port, points, liste=(), **options):
        vues.append(a.progression())
        return trace(*DETOUR)

    monkeypatch.setattr(brouter, "calculer", calculer)
    assert "erreur" not in a.itineraire({"points": [[43.3, 6.0], [43.3, 6.01]]})
    assert [v["etape"] for v in vues] == ["itineraire", "comparaison"]
    assert all(v["actif"] and 0 < v["fraction"] < 1 for v in vues)
    assert a.progression() == {"actif": False}


def test_journal_garde_la_trace_des_calculs(simulee, monkeypatch):
    a, _, _, _ = simulee
    chemin = appli.configurer_journal(a.dossier)
    try:
        monkeypatch.setattr(brouter, "calculer", lambda port, points, liste=(), **o: trace((43.3, 6.0), (43.3, 6.01)))
        a.itineraire({"points": [[43.3, 6.0], [43.3, 6.01]], "comparer": False})    # passe la clôture : refusé
    finally:
        racine = logging.getLogger("hike2gpx")
        for h in [h for h in racine.handlers if Path(getattr(h, "baseFilename", "")) == chemin]:
            racine.removeHandler(h)
            h.close()
    journal = a.lire_journal()
    assert journal["chemin"] == str(chemin)
    assert any("Itinéraire : 2 points" in ligne for ligne in journal["lignes"])
    [erreur] = [ligne for ligne in journal["lignes"] if "WARNING Itinéraire en erreur" in ligne]
    # Le temps de chaque étape accompagne l'issue du calcul.
    assert "refusé" in erreur and "préparation" in erreur and "calcul BRouter" in erreur


def donnees_d_essai(dossier):
    """Un dossier de données comme celui de Nico : caches, deux extraits, une
    tuile BRouter, l'ancien index de Geofabrik."""
    for sous, noms in (("overpass", ["v1_866_120.json", "v1_866_121.json"]),
                       ("franchissements", ["v3_866_120.json"]), ("bdtopo", ["v1_866_120.json"])):
        (dossier / sous).mkdir(parents=True)
        for nom in noms:
            (dossier / sous / nom).write_text("{}")
    extraits = geofabrik.dossier_extraits(dossier)
    extraits.mkdir(parents=True)
    for nom in ("fr-var.sqlite", "provence-alpes-cote-d-azur.sqlite"):
        (extraits / nom).write_bytes(bytes(1000))
    (extraits / "index-v1.json").write_bytes(bytes(500))
    segments = dossier / "brouter" / "segments4"
    segments.mkdir(parents=True)
    (segments / "E5_N40.rd5").write_bytes(b"ancienne")
    return [{**REGION_PACA, "id": "fr-var", "nom": "Var", "voies_coupees": True, "date": "2026-10-19T01:38:06Z",
             "base": extraits / "fr-var.sqlite"},
            {**REGION_PACA, "date": "2026-10-18T20:25:06Z", "base": extraits / "provence-alpes-cote-d-azur.sqlite"}]


def test_les_donnees_telechargees_se_voient_et_se_videent(tmp_path, monkeypatch):
    # Nico, 2026-10-20 : « il faudrait une fonction pour vider le cache, dans
    # les réglages ». Les caches d'Overpass d'avant la 0.9.31 ne sont plus que
    # des restes, à nettoyer (Nico, 2026-11-13 : « supprime tout ce qui traîne
    # sur overpass et extraits »).
    installes = donnees_d_essai(tmp_path)
    monkeypatch.setattr(geofabrik, "installes", lambda dossier: [e for e in installes if e["base"].exists()])
    a = appli.Application(tmp_path)
    d = a.donnees()
    assert "osm" not in d and d["bdtopo"] == {"fichiers": 1, "octets": 2}
    assert [(e["id"], e["octets"]) for e in d["extraits"]] == [("fr-var", 1000), (REGION_PACA["id"], 1000)]
    assert [s["nom"] for s in d["brouter"]] == ["E5_N40"] and d["restes"] == {"fichiers": 4, "octets": 506}
    assert d["occupe"] == {"brouter": False}
    assert a.agir_donnees({"action": "vider_bdtopo"})["bdtopo"]["fichiers"] == 0
    # Un extrait de la fabrication se supprime, sauf pendant qu'un lot se prépare.
    a._fil_lot = type("Fil", (), {"is_alive": lambda self: True})()
    assert "erreur" in a.agir_donnees({"action": "supprimer_extrait", "cible": "fr-var"})
    a._fil_lot = None
    d = a.agir_donnees({"action": "supprimer_extrait", "cible": "fr-var"})
    assert [e["id"] for e in d["extraits"]] == [REGION_PACA["id"]] and not installes[0]["base"].exists()
    assert a.agir_donnees({"action": "nettoyer"})["restes"]["fichiers"] == 0
    assert not (tmp_path / "overpass").exists() and not (tmp_path / "franchissements").exists()
    assert a.agir_donnees({"action": "supprimer_extrait", "cible": "inconnu"}) == {"erreur": "Extrait inconnu."}
    assert a.agir_donnees({"action": "actualiser_extrait", "cible": REGION_PACA["id"]}) == {
        "erreur": "Action inconnue."}, "un extrait se refait avec son lot"


def test_vider_cache_unique_efface_toutes_les_donnees_locales(tmp_path):
    donnees_d_essai(tmp_path)
    for dossier, nom in (("gpx2elev", "profil.json"), ("brouter/maison", "etat.json"),
                         ("hors-ligne/E5_N40", "manifest.json"), ("hors-ligne/fonds", "E5_N40-scan25.mbtiles")):
        p = tmp_path / dossier / nom
        p.parent.mkdir(parents=True)
        p.write_text("{}")
    a = appli.Application(tmp_path)
    assert "erreur" not in a.agir_donnees({"action": "vider_cache"})
    assert not list((tmp_path / "overpass").glob("*.json"))
    assert not list((tmp_path / "franchissements").glob("*.json"))
    assert not list((tmp_path / "bdtopo").glob("*.json"))
    assert not (tmp_path / "gpx2elev").exists()
    assert not (tmp_path / "brouter" / "maison").exists()
    assert not list((tmp_path / "brouter" / "segments4").glob("*.rd5"))
    assert not list(geofabrik.dossier_extraits(tmp_path).iterdir())
    assert not (tmp_path / "hors-ligne").exists(), "les lots et les fonds aussi, pour repartir de zéro"


def test_supprimer_une_case_depuis_la_carte(tmp_path):
    a = appli.Application(tmp_path)
    assert "erreur" in a.supprimer_case({"case": "../E5_N40"})
    (tmp_path / "hors-ligne" / "fonds").mkdir(parents=True)
    (tmp_path / "hors-ligne" / "fonds" / "E5_N40-scan25.mbtiles").write_bytes(b"fond")
    assert a.supprimer_case({"case": "E5_N40"}) == {"octets": 4}
    assert not list((tmp_path / "hors-ligne" / "fonds").iterdir())


def test_vider_cache_refuse_pendant_un_calcul(tmp_path):
    donnees_d_essai(tmp_path)
    a = appli.Application(tmp_path)
    a._verrou_calcul.acquire()
    try:
        assert "erreur" in a.agir_donnees({"action": "vider_cache"})
        assert (tmp_path / "brouter" / "segments4" / "E5_N40.rd5").exists()
    finally:
        a._verrou_calcul.release()


def test_journal_est_horodate_et_ne_reprend_pas_l_ancien(tmp_path):
    (tmp_path / "hike2gpx.log").write_text("ancienne session\n")
    chemin = appli.configurer_journal(tmp_path)
    racine = logging.getLogger("hike2gpx")
    try:
        racine.info("nouvelle session")
        resultat = appli.Application(tmp_path).lire_journal()
        assert chemin.name.startswith("hike2gpx-20") and chemin.suffix == ".log"
        assert chemin.parent == tmp_path / "logs"
        assert resultat["chemin"] == str(chemin)
        assert any("nouvelle session" in ligne for ligne in resultat["lignes"])
        assert not any("ancienne session" in ligne for ligne in resultat["lignes"])
    finally:
        for h in [h for h in racine.handlers if Path(getattr(h, "baseFilename", "")) == chemin]:
            racine.removeHandler(h)
            h.close()


def test_journal_ne_garde_que_les_dernieres_sessions(tmp_path):
    # Un fichier par démarrage : sans élagage, ils s'accumuleraient à jamais.
    logs = tmp_path / "logs"
    logs.mkdir()
    anciennes = [f"hike2gpx-202610{jour:02d}-120000-000000.log" for jour in range(1, 13)]
    for nom in anciennes:
        (logs / nom).write_text("session\n")
    (logs / (anciennes[0] + ".1")).write_text("rotation\n")
    (tmp_path / "hike2gpx.log").write_text("journal d'avant les sessions\n")
    chemin = appli.configurer_journal(tmp_path)
    racine = logging.getLogger("hike2gpx")
    try:
        restants = sorted(p.name for p in logs.glob("hike2gpx-*"))
        assert len(restants) == appli.SESSIONS_GARDEES and restants[-1] == chemin.name
        assert restants[:-1] == anciennes[-(appli.SESSIONS_GARDEES - 1):]      # les plus récentes
        assert (tmp_path / "hike2gpx.log").exists()         # rien d'autre n'est touché
    finally:
        for h in [h for h in racine.handlers if Path(getattr(h, "baseFilename", "")) == chemin]:
            racine.removeHandler(h)
            h.close()


def test_les_tuiles_brouter_s_actualisent_a_cote_puis_basculent(tmp_path, monkeypatch):
    # Les anciennes servent pendant le téléchargement ; la bascule se fait
    # moteurs arrêtés, car sous Windows un RD5 ouvert ne se remplace pas.
    donnees_d_essai(tmp_path)
    a = appli.Application(tmp_path)
    vues, arrets = [], []

    def telecharger(nom, vers=None):
        vues.append((tmp_path / "brouter" / "segments4" / f"{nom}.rd5").read_bytes())
        vers.mkdir(parents=True, exist_ok=True)
        (vers / f"{nom}.rd5").write_bytes(b"nouvelle")

    monkeypatch.setattr(a.installation, "telecharger_segment", telecharger)
    monkeypatch.setattr(a, "arreter", lambda: arrets.append(True))
    d = a.agir_donnees({"action": "actualiser_brouter"})
    assert "erreur" not in d
    a._fil_brouter.join(5)
    assert vues == [b"ancienne"] and arrets == [True]
    assert (tmp_path / "brouter" / "segments4" / "E5_N40.rd5").read_bytes() == b"nouvelle"
    assert not (tmp_path / "brouter" / "segments4" / "nouvelles").exists()
    assert a.extrait(None)["brouter"] is None


def test_brouter_se_renouvelle_apres_le_delai_des_reglages(tmp_path, monkeypatch):
    a = appli.Application(tmp_path)
    a.installation.segments.mkdir(parents=True)
    ancienne = a.installation.segments / "E5_N40.rd5"
    recente = a.installation.segments / "E0_N45.rd5"
    ancienne.write_bytes(b"ancienne")
    recente.write_bytes(b"recente")
    date_ancienne = time.time() - 2 * 86400
    os.utime(ancienne, (date_ancienne, date_ancienne))
    monkeypatch.setattr(a.installation, "installee", lambda: True)
    telechargees = []

    def telecharger(nom, vers=None):
        telechargees.append(nom)
        assert ancienne.read_bytes() == b"ancienne"
        vers.mkdir(parents=True, exist_ok=True)
        (vers / f"{nom}.rd5").write_bytes(b"nouvelle")

    monkeypatch.setattr(a.installation, "telecharger_segment", telecharger)
    monkeypatch.setattr(a, "arreter", lambda: None)
    assert a.installer_moteur() == {"brouter_en_cours": None}  # délai par défaut : 30 jours
    a.enregistrer_reglages({"renouvellement_jours": 1})
    assert a.installer_moteur() == {"brouter_en_cours": {"moteur": False, "segments": ["E5_N40"]}}
    a._fil_brouter.join(5)
    assert telechargees == ["E5_N40"]
    assert ancienne.read_bytes() == b"nouvelle"
    assert recente.read_bytes() == b"recente"
    assert a.installer_moteur() == {"brouter_en_cours": None}


def test_renouvellement_brouter_en_echec_attend_une_heure(tmp_path, monkeypatch):
    a = appli.Application(tmp_path)
    a.installation.segments.mkdir(parents=True)
    ancienne = a.installation.segments / "E5_N40.rd5"
    ancienne.write_bytes(b"ancienne")
    date_ancienne = time.time() - 40 * 86400
    os.utime(ancienne, (date_ancienne, date_ancienne))
    monkeypatch.setattr(a.installation, "installee", lambda: True)
    essais = []

    def telecharger(nom, vers=None):
        essais.append(nom)
        raise brouter.ErreurBRouter("réseau indisponible")

    monkeypatch.setattr(a.installation, "telecharger_segment", telecharger)
    assert a.installer_moteur()["brouter_en_cours"]["segments"] == ["E5_N40"]
    a._fil_brouter.join(5)
    assert ancienne.read_bytes() == b"ancienne"
    assert a.installer_moteur() == {"brouter_en_cours": None}
    assert essais == ["E5_N40"]


def test_chaque_provider_a_son_pays_dans_l_index_geofabrik():
    """Un provider absent de PAYS_CARTES n'est jamais choisi quand on déplace la
    carte à la main : un oubli silencieux, qu'un test rend visible."""
    providers = Path(appli.__file__).parent / "assets" / "web" / "providers"
    assert set(appli.PAYS_CARTES.values()) == {p.stem for p in providers.glob("[a-z][a-z].js")}
