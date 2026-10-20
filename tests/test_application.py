import logging
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
    assert a.reglages() == {"cle_ign": ""}
    assert a.enregistrer_reglages({"cle_ign": " cle_essai-1 "}) == {"cle_ign": "cle_essai-1"}
    assert appli.Application(tmp_path).reglages() == {"cle_ign": "cle_essai-1"}
    assert "erreur" in a.enregistrer_reglages({"cle_ign": "<script>"})


@pytest.fixture(autouse=True)
def sans_index_geofabrik(monkeypatch):
    """Calculs et calques consultent l'index de Geofabrik pour télécharger
    d'eux-mêmes l'extrait de la région : ici, aucune région, donc aucun
    réseau. Les essais de l'extrait fournissent la leur."""
    monkeypatch.setattr(geofabrik, "regions", lambda dossier, **options: [])


@pytest.fixture
def simulee(tmp_path, monkeypatch):
    a = appli.Application(tmp_path)
    monkeypatch.setattr(a.installation, "installee", lambda: True)
    monkeypatch.setattr(a.installation, "segment_present", lambda nom: True)
    monkeypatch.setattr(a, "moteur", lambda: 1)
    zones, appels = [], []
    bloquant = {"cle": "x", "statut": "blocked", "raison": "r", "nature": "Clôture",
                "lat": 43.3, "lon": 6.005, "osm": "way/9", "voies": [1], "coupes": [coupe_nord_sud(43.3, 6.005)]}

    def zone(*args, **options):
        zones.append(args[:4])
        return [bloquant]

    monkeypatch.setattr(franchissements, "franchissements_zone", zone)

    def sans_tuiles_maison(tuiles, **options):
        raise brouter.ErreurBRouter("tuiles maison hors de cet essai")

    # Les essais du moteur standard passent par le repli : jamais de réseau ici.
    monkeypatch.setattr(a.maison, "preparer", sans_tuiles_maison)
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
    assert appli.portions_ign(t) == [{"debut_m": 300, "longueur_m": 324,
                                      "coords": [[43.302, 6.003], [43.302, 6.007]]}]
    # Deux morceaux IGN de suite ne font qu'une portion.
    t = trace_messages(DETOUR, [(1, 300, "highway=path hike2gpx=ign"), (2, 324, "foot=private hike2gpx=ign"),
                                (3, 300, "highway=track")])
    [p] = appli.portions_ign(t)
    assert (p["debut_m"], p["longueur_m"], len(p["coords"])) == (0, 624, 3)
    assert appli.portions_ign(trace(*DETOUR)) == []


def test_itineraire_sur_les_tuiles_maison(simulee, monkeypatch):
    a, zones, appels, bloquant = simulee
    monkeypatch.setattr(a.maison, "preparer", lambda tuiles, **o: ("segments-maison", [bloquant]))
    monkeypatch.setattr(a, "moteur_maison", lambda segments: 2 if segments == "segments-maison" else 0)

    def calculer(port, points, liste=(), **options):
        appels.append((port, options.get("profil", "hike2gpx"), len(liste)))
        if port == 2:
            return trace_messages(DETOUR, [(1, 300, "highway=path"), (2, 324, "highway=path hike2gpx=ign"),
                                           (3, 300, "highway=track")])
        return trace((43.3, 6.0), (43.3, 6.01), longueur="800")

    monkeypatch.setattr(brouter, "calculer", calculer)
    r = a.itineraire({"points": [[43.3, 6.0], [43.3, 6.01]]})
    assert r["moteur"] == "maison" and r["avertissement"] is None
    # Les franchissements viennent du réseau fusionné, pas d'OSM seul.
    assert zones == [] and appels == [(2, "hike2gpx", 1), (1, "hiking-mountain", 0)]
    assert [p["longueur_m"] for p in r["portions_ign"]] == [324]
    [f] = r["sur_le_trace"]
    assert f["statut"] == "uncertain" and f["osm"] is None and f["distance_m"] == 300
    assert [f["cle"] for f in r["naif_traverse"]] == ["x"]


def test_itineraire_repli_sur_osm_quand_les_tuiles_maison_echouent(simulee, monkeypatch):
    a, zones, _, _ = simulee
    essais = []

    def panne(tuiles, **options):
        essais.append(tuiles)
        raise brouter.ErreurBRouter("Fabrication des tuiles impossible (WayLinker)")

    monkeypatch.setattr(a.maison, "preparer", panne)
    monkeypatch.setattr(brouter, "calculer", lambda port, points, liste=(), **o:
                        trace((43.3, 6.0), (43.35, 6.005), (43.3, 6.01)))
    r = a.itineraire({"points": [[43.3, 6.0], [43.3, 6.01]], "comparer": False})
    assert r["moteur"] == "standard" and "OSM seul" in r["avertissement"] and "WayLinker" in r["avertissement"]
    # La zone s'élargit une fois ; les tuiles maison ne sont pas retentées.
    assert len(essais) == 1 and len(zones) == 2 and r["portions_ign"] == []


def test_itineraire_introuvable_sur_les_tuiles_maison_reste_une_erreur(simulee, monkeypatch):
    a, zones, _, bloquant = simulee
    monkeypatch.setattr(a.maison, "preparer", lambda tuiles, **o: ("segments-maison", [bloquant]))
    monkeypatch.setattr(a, "moteur_maison", lambda segments: 2)

    def calculer(port, points, liste=(), **options):
        if port != 2:
            pytest.fail("repli sur OSM seul après un itinéraire introuvable")
        raise brouter.ErreurBRouter("Aucun itinéraire ne respecte les barrières entre ces points.")

    monkeypatch.setattr(brouter, "calculer", calculer)
    assert "barrières" in a.itineraire({"points": [[43.3, 6.0], [43.3, 6.01]]})["erreur"]


def test_itineraire_sans_les_chemins_ign(simulee, monkeypatch):
    a, zones, _, _ = simulee
    monkeypatch.setattr(a.maison, "preparer", lambda tuiles, **o: pytest.fail("tuiles maison demandées"))
    monkeypatch.setattr(brouter, "calculer", lambda port, points, liste=(), **o: trace(*DETOUR))
    r = a.itineraire({"points": [[43.3, 6.0], [43.3, 6.01]], "ign": False, "comparer": False})
    assert r["moteur"] == "standard" and r["avertissement"] is None and len(zones) == 1


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
    monkeypatch.setattr(franchissements, "franchissements_zone", lambda *args, **o: [incertain])
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


def test_itineraire_s_arrete_si_les_barrieres_sont_inconnues(simulee, monkeypatch):
    a, _, _, _ = simulee

    def panne(*args, **options):
        raise franchissements.ErreurDonnees("Overpass ne répond pas : barrières non vérifiées.")

    monkeypatch.setattr(franchissements, "franchissements_zone", panne)
    monkeypatch.setattr(brouter, "calculer", lambda *a, **o: pytest.fail("calcul sans barrières"))
    reponse = a.itineraire({"points": [[43.3, 6.0], [43.3, 6.01]]})
    assert "barrières non vérifiées" in reponse["erreur"] and "extrait_en_cours" not in reponse
    # La région a un extrait : le calcul l'a lancé de lui-même, la page attendra.
    monkeypatch.setattr(geofabrik, "regions", lambda dossier, **options: [REGION_PACA])
    lancees = []
    monkeypatch.setattr(geofabrik.Telechargements, "lancer", lambda self, region: lancees.append(region["id"]) or True)
    reponse = a.itineraire({"points": [[43.3, 6.0], [43.3, 6.01]]})
    assert reponse["extrait_en_cours"] == {"id": REGION_PACA["id"], "nom": REGION_PACA["nom"]}
    assert lancees == [REGION_PACA["id"]]


REGION_PACA = {"id": "provence-alpes-cote-d-azur", "nom": "Provence Alpes-Cote-d'Azur",
               "pbf": "https://download.geofabrik.de/europe/france/provence-alpes-cote-d-azur-latest.osm.pbf",
               "bornes": (42.9, 4.2, 45.2, 7.8),
               "polygones": [[[(4.2, 42.9), (7.8, 42.9), (7.8, 45.2), (4.2, 45.2), (4.2, 42.9)]]]}


def test_extrait_telecharge_de_lui_meme_quand_la_region_sert(tmp_path, monkeypatch):
    # Décision de Nico du 2026-10-19 : pas de bouton. Le calque des chemins OSM
    # (ou un calcul) lance l'extrait ; survoler la carte (/api/extrait) non.
    a = appli.Application(tmp_path)
    monkeypatch.setattr(geofabrik, "regions", lambda dossier, **options: [REGION_PACA])
    lancees = []
    monkeypatch.setattr(geofabrik.Telechargements, "lancer", lambda self, region: lancees.append(region["id"]) or True)
    monkeypatch.setattr(franchissements, "voies_affichables", lambda *z, **o: {"voies": [], "barrieres": []})
    # La requête du calque ne parle jamais à Geofabrik : sa réponse tarde
    # parfois une minute (2026-10-20), la taille se vérifie en tâche de fond.
    monkeypatch.setattr(geofabrik.urllib.request, "urlopen",
                        lambda *a, **o: pytest.fail("Geofabrik interrogé pendant la requête de la page"))
    vue = (43.30, 6.00, 43.34, 6.08)
    assert a.extrait(vue) == {"en_cours": None, "brouter": None} and lancees == []
    assert a.calque_osm(vue)["extrait_en_cours"] == {"id": REGION_PACA["id"], "nom": REGION_PACA["nom"]}
    assert lancees == [REGION_PACA["id"]]
    # Hors de toute région, ou région écartée (trop grosse, disque plein) : rien ne part.
    assert "extrait_en_cours" not in a.calque_osm((60.0, 6.0, 60.01, 6.01))
    monkeypatch.setattr(geofabrik.Telechargements, "lancer", lambda self, region: False)
    assert "extrait_en_cours" not in appli.Application(tmp_path / "autre").calque_osm(vue)


def test_un_calque_publie_son_avancement_tuile_apres_tuile(tmp_path, monkeypatch):
    # La page en tire la barre de sa note (« 2 sur 6 tuiles · 12 s »).
    a = appli.Application(tmp_path)
    vus = []

    def lire(*zone, continuer, suivi, **options):
        for faites in range(3):
            suivi(faites, 3)
            vus.append(a.progression()["calques"]["osm"])
        suivi(3, 3)
        return {"voies": [], "barrieres": []}

    monkeypatch.setattr(franchissements, "voies_affichables", lire)
    a.calque_osm((43.30, 6.00, 43.34, 6.08))
    assert [(v["faites"], v["total"]) for v in vus] == [(0, 3), (1, 3), (2, 3)]
    assert all(v["duree_s"] >= 0 for v in vus)
    assert a.progression()["calques"] == {}


def test_moteur_et_tuiles_brouter_telecharges_d_eux_memes(simulee, monkeypatch):
    # Même règle pour BRouter : la tuile manquante part en tâche de fond, le
    # calcul le dit, et une tuile en échec attend une heure avant un nouvel essai.
    a, _, _, _ = simulee
    present, telechargees = set(), []

    def telecharger(nom):
        telechargees.append(nom)
        if nom == "E5_N40":
            raise brouter.ErreurBRouter("Téléchargement impossible : brouter.de injoignable.")
        present.add(nom)

    monkeypatch.setattr(a.installation, "segment_present", lambda nom: nom in present)
    monkeypatch.setattr(a.installation, "telecharger_segment", telecharger)
    r = a.itineraire({"points": [[43.3, 6.0], [43.3, 6.01]]})
    assert r["segments_manquants"] == ["E5_N40"] and r["brouter_en_cours"] == {"moteur": False, "segments": ["E5_N40"]}
    a._fil_brouter.join(5)
    assert telechargees == ["E5_N40"] and a.extrait(None)["brouter"] is None
    r = a.itineraire({"points": [[43.3, 6.0], [43.3, 6.01]]})
    assert r["brouter_en_cours"] is None and telechargees == ["E5_N40"]      # échec récent : pas d'essai
    # Moteur absent au lancement de la page : il s'installe de lui-même.
    installe = []
    monkeypatch.setattr(a.installation, "installee", lambda: bool(installe))
    monkeypatch.setattr(a.installation, "installer", lambda: installe.append(True))
    assert a.installer_moteur() == {"brouter_en_cours": {"moteur": True, "segments": []}}
    a._fil_brouter.join(5)
    assert installe == [True]


@pytest.mark.parametrize("requete, attendu", [
    ({"s": ["43.3"], "w": ["6.0"], "n": ["43.35"], "e": ["6.05"]}, (43.3, 6.0, 43.35, 6.05)),
    ({"s": ["43.35"], "w": ["6.0"], "n": ["43.3"], "e": ["6.05"]}, None),
    ({"s": ["43.3"], "w": ["6.0"], "n": ["43.35"]}, None),
    ({"s": ["nan"], "w": ["6.0"], "n": ["43.35"], "e": ["6.05"]}, None),
    ({"s": ["x"], "w": ["6.0"], "n": ["43.35"], "e": ["6.05"]}, None),
])
def test_lire_zone(requete, attendu):
    assert appli.lire_zone(requete) == attendu


def test_calques_refusent_une_zone_trop_grande_ou_invalide(tmp_path, monkeypatch):
    a = appli.Application(tmp_path)
    monkeypatch.setattr(franchissements, "voies_affichables", lambda *z: pytest.fail("lecture inutile"))
    assert "trop grande" in a.calque_osm((43.0, 6.0, 43.5, 6.5))["erreur"]
    assert "invalide" in a.calque_osm(None)["erreur"]


def test_calque_bdtopo_et_panne(tmp_path, monkeypatch):
    from hike2gpx import bdtopo
    a = appli.Application(tmp_path)
    monkeypatch.setattr(bdtopo, "troncons_zone", lambda *z, **o: [{"id": "A-0"}])
    # Les bornes des tuiles lues, que la page n'a pas à redemander.
    assert a.calque_bdtopo((43.31, 6.01, 43.34, 6.04)) == {"troncons": [{"id": "A-0"}],
                                                          "bornes": (43.3, 6.0, 43.35, 6.05)}

    def panne(*z, **o):
        raise franchissements.ErreurDonnees("BD TOPO indisponible (hors ligne).")

    monkeypatch.setattr(bdtopo, "troncons_zone", panne)
    assert a.calque_bdtopo((43.3, 6.0, 43.35, 6.05)) == {"erreur": "BD TOPO indisponible (hors ligne)."}


def test_une_nouvelle_vue_arrete_la_lecture_de_la_precedente(tmp_path, monkeypatch):
    # Journal du 2026-10-19 : chaque déplacement de la carte ajoutait sa lecture
    # Overpass à celles des vues quittées. Ici, la vue B arrive pendant que la
    # vue A lit sa première tuile : A s'arrête là.
    a = appli.Application(tmp_path)
    vue_a, vue_b = (43.31, 6.01, 43.34, 6.06), (43.41, 6.21, 43.44, 6.26)
    lues = []

    def lire(sud, ouest, nord, est, dossier, continuer, suivi):
        for tuile in franchissements.tuiles_zone(sud, ouest, nord, est):
            if not continuer():
                raise franchissements.VueRemplacee()
            lues.append(tuile)
            if (sud, ouest, nord, est) == vue_a:
                assert a.calque_osm(vue_b)["voies"] == []
        return {"voies": [], "barrieres": []}

    monkeypatch.setattr(franchissements, "voies_affichables", lire)
    assert a.calque_osm(vue_a)["code"] == "vue_remplacee"
    assert lues == [(866, 120), (868, 124), (868, 125)]
    assert a.calque_osm(vue_b)["bornes"] == (43.4, 6.2, 43.45, 6.3)


def test_une_vue_plus_ancienne_arrivee_apres_est_refusee_d_emblee(tmp_path, monkeypatch):
    # Calque figé du 2026-10-20 : une requête plus ancienne de la page, arrivée
    # au serveur après la plus récente, passait pour la vue en cours ; la plus
    # récente revenait « remplacée » et la page restait sans chemins. La page
    # date désormais ses vues, et le serveur refuse les plus anciennes.
    a = appli.Application(tmp_path)
    lues, lances = [], []
    monkeypatch.setattr(franchissements, "voies_affichables",
                        lambda *z, **o: lues.append(z[:4]) or {"voies": [], "barrieres": []})
    monkeypatch.setattr(a, "_extrait_automatique", lambda zone, raison: lances.append(zone))
    vue = (43.30, 6.00, 43.34, 6.08)
    assert "voies" in a.calque_osm(vue, 1760000000002.5)
    assert a.calque_osm(vue, 1760000000001.0)["code"] == "vue_remplacee"
    assert len(lues) == 1 and len(lances) == 1         # ni lecture ni extrait pour la périmée
    assert "voies" in a.calque_osm(vue, 1760000000003.0)
    # Un arrêt daté remplace ce qui le précède, sans toucher à ce qui le suit.
    a.arreter_calques({"calques": ["osm"], "vue": 1760000000004.0})
    assert a.calque_osm(vue, 1760000000003.5)["code"] == "vue_remplacee"
    assert "voies" in a.calque_osm(vue, 1760000000005.0)
    assert appli.lire_vue({"vue": ["1760000000005.125"]}) == 1760000000005.125
    assert [appli.lire_vue(q) for q in ({}, {"vue": ["nan"]}, {"vue": ["x"]})] == [None, None, None]


def test_arreter_calques_ne_touche_que_ceux_que_la_page_masque(tmp_path):
    a = appli.Application(tmp_path)
    assert a.arreter_calques({"calques": ["bdtopo"]}) == {"arretes": ["bdtopo"]}
    assert a._vues == {"osm": 0, "bdtopo": 1}
    assert a.arreter_calques({}) == {"arretes": ["osm", "bdtopo"]}


def test_route_denivele(tmp_path, monkeypatch):
    from hike2gpx import denivele
    a = appli.Application(tmp_path)
    monkeypatch.setattr(denivele, "calculer", lambda coordonnees, dossier: {"montee_m": 523, "dossier": dossier})
    assert a.denivele({"coordonnees": [[6.0, 43.3], [6.01, 43.3]]}) == {"montee_m": 523, "dossier": tmp_path}

    def invalide(coordonnees, dossier):
        raise ValueError("Tracé invalide.")

    monkeypatch.setattr(denivele, "calculer", invalide)
    assert a.denivele({}) == {"erreur": "Tracé invalide."}


def test_routes_init_annonce_l_application(tmp_path):
    get, post = appli.Application(tmp_path).routes()
    assert get["init"]()["app"] == "hike2gpx"
    assert {"osm", "bdtopo", "extrait"} <= set(get)
    # Plus de téléchargement à la demande (tuile, extrait) : tout part de lui-même.
    assert set(post) == {"itineraire", "reglages", "moteur", "denivele", "langue", "arreter_calques"}


def test_langue_choisie_gardee_dans_les_preferences(tmp_path):
    # /api/langue : le choix FR / EN du commun, à côté de la clé IGN.
    a = appli.Application(tmp_path)
    a.enregistrer_reglages({"cle_ign": "cle_test"})
    get, post = a.routes()
    assert get["langue"]()["code"] is None
    assert post["langue"]({"code": "en"})["enregistre"]
    autre = appli.Application(tmp_path)
    assert autre.routes()[0]["langue"]()["code"] == "en" and autre.reglages() == {"cle_ign": "cle_test"}


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
    assert a.progression() == {"actif": False, "calques": {}}


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
