import logging
import os
import time
from pathlib import Path

import pytest

from hike2gpx import application as appli, brouter, franchissements, geofabrik, osmfr


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
    assert a.reglages() == {"cle_ign": "", "renouvellement_jours": 30}
    assert a.enregistrer_reglages({"cle_ign": " cle_essai-1 "}) == {"cle_ign": "cle_essai-1", "renouvellement_jours": 30}
    assert appli.Application(tmp_path).reglages() == {"cle_ign": "cle_essai-1", "renouvellement_jours": 30}
    assert a.enregistrer_reglages({"cle_ign": "cle_essai-1", "renouvellement_jours": 45})["renouvellement_jours"] == 45
    assert "erreur" in a.enregistrer_reglages({"cle_ign": "cle_essai-1", "renouvellement_jours": 0})
    assert "erreur" in a.enregistrer_reglages({"cle_ign": "<script>"})


@pytest.fixture(autouse=True)
def sans_index_geofabrik(monkeypatch):
    """Calculs et calques consultent les index de Geofabrik et d'OSM France
    pour télécharger d'eux-mêmes l'extrait de la région : ici, aucune région,
    donc aucun réseau. Les essais de l'extrait fournissent la leur."""
    monkeypatch.setattr(geofabrik, "regions", lambda dossier, **options: [])
    monkeypatch.setattr(osmfr, "regions", lambda dossier, **options: [])


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
    monkeypatch.setattr(geofabrik.Telechargements, "lancer", lambda self, region, **options: lancees.append(region["id"]) or True)
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
    monkeypatch.setattr(geofabrik.Telechargements, "lancer", lambda self, region, **options: lancees.append(region["id"]) or True)
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
    monkeypatch.setattr(geofabrik.Telechargements, "lancer", lambda self, region, **options: False)
    assert "extrait_en_cours" not in appli.Application(tmp_path / "autre").calque_osm(vue)


def test_une_autre_region_prend_la_place_de_l_extrait_en_cours(tmp_path, monkeypatch):
    # Nico, 2026-10-20 : passé du Centre à la Bretagne, il attendait la fin du
    # Centre. La page demandait bien la Bretagne, mais l'extrait en cours,
    # d'où qu'il soit, était rendu tel quel, sans rien lancer.
    a = appli.Application(tmp_path)
    monkeypatch.setattr(geofabrik, "regions", lambda dossier, **options: [REGION_PACA])
    lancees = []
    monkeypatch.setattr(geofabrik.Telechargements, "lancer", lambda self, region, **options: lancees.append(region["id"]) or True)
    monkeypatch.setattr(franchissements, "voies_affichables", lambda *z, **o: {"voies": [], "barrieres": []})
    monkeypatch.setattr(geofabrik.Telechargements, "etat",
                        lambda self: {"id": "centre", "nom": "Centre", "etape": "import"})
    vue = (43.30, 6.00, 43.34, 6.08)
    assert a.calque_osm(vue)["extrait_en_cours"]["id"] == REGION_PACA["id"]
    assert lancees == [REGION_PACA["id"]]
    # La même région déjà en cours : rien ne repart.
    monkeypatch.setattr(geofabrik.Telechargements, "etat",
                        lambda self: {"id": REGION_PACA["id"], "nom": REGION_PACA["nom"], "etape": "import"})
    assert a.calque_osm(vue)["extrait_en_cours"]["id"] == REGION_PACA["id"] and lancees == [REGION_PACA["id"]]


def test_la_cascade_le_departement_puis_sa_region_de_geofabrik(tmp_path, monkeypatch):
    # Nico, 2026-10-20 : « comme ça, on a la main rapidement sur le var
    # (garéoult), on peut travailler, pendant ce temps paca se prépare » ;
    # « dès que paca est dispo, on l'utilise pour ne pas avoir de pb aux
    # frontières ». Le Var d'OSM France : 83 Mo ; la PACA de Geofabrik : 391 Mo.
    a = appli.Application(tmp_path)
    var = {"id": "fr-var", "nom": "Var", "pbf": osmfr.EXTRAITS + "provence_alpes_cote_d_azur/var.osm.pbf",
           "bornes": (43.0, 5.6, 43.8, 6.95), "voies_coupees": True,
           "polygones": [[[(5.6, 43.0), (6.95, 43.0), (6.95, 43.8), (5.6, 43.8), (5.6, 43.0)]]]}
    paca = {**REGION_PACA, "id": "fr-provence-alpes-cote-d-azur", "voies_coupees": True,
            "pbf": osmfr.EXTRAITS + "provence_alpes_cote_d_azur.osm.pbf"}
    monkeypatch.setattr(osmfr, "regions", lambda dossier, **options: [paca, var])
    monkeypatch.setattr(geofabrik, "regions", lambda dossier, **options: [REGION_PACA])
    lancees = []
    monkeypatch.setattr(geofabrik.Telechargements, "lancer",
                        lambda self, region, **options: lancees.append((region["id"], options)) or True)
    monkeypatch.setattr(franchissements, "voies_affichables", lambda *z, **o: {"voies": [], "barrieres": []})
    vue = (43.30, 6.00, 43.34, 6.08)
    # Rien sur le disque : le Var d'abord, la PACA de Geofabrik à sa suite.
    assert a.calque_osm(vue)["extrait_en_cours"] == {"id": "fr-var", "nom": "Var"}
    assert lancees == [("fr-var", {"ensuite": REGION_PACA})]
    # Le Var installé : la page a ses données, la PACA se prépare pour le relayer.
    monkeypatch.setattr(geofabrik, "extrait_de_tuile", lambda dossier, i, j: {**var, "date": "2026-10-19T01:38:06Z"})
    assert "extrait_en_cours" not in a.calque_osm(vue)
    assert lancees[-1] == (REGION_PACA["id"], {"relais": True})
    # Un téléchargement en cours ailleurs : la PACA ne lui prend pas sa place.
    del lancees[:]
    monkeypatch.setattr(geofabrik.Telechargements, "etat",
                        lambda self: {"id": "fr-bouches-du-rhone", "nom": "Bouches-du-Rhone", "etape": "import"})
    assert "extrait_en_cours" not in a.calque_osm(vue) and lancees == []
    # La PACA installée : c'est elle qui sert, plus rien ne part.
    monkeypatch.setattr(geofabrik, "extrait_de_tuile", lambda dossier, i, j: REGION_PACA)
    monkeypatch.setattr(geofabrik.Telechargements, "etat", lambda self: None)
    assert "extrait_en_cours" not in a.calque_osm(vue) and lancees == []
    # Le Var en échec, une heure : la région d'OSM France, toujours suivie de la PACA.
    monkeypatch.setattr(geofabrik, "extrait_de_tuile", lambda dossier, i, j: None)
    geofabrik.telechargements(tmp_path)._echecs["fr-var"] = time.monotonic()
    assert a.calque_osm(vue)["extrait_en_cours"]["id"] == "fr-provence-alpes-cote-d-azur"
    assert lancees == [("fr-provence-alpes-cote-d-azur", {"ensuite": REGION_PACA})]


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


def test_disponibilite_depuis_extrait_ou_overpass(tmp_path, monkeypatch):
    a = appli.Application(tmp_path)
    zone = (43.3, 6.0, 43.31, 6.01)
    monkeypatch.setattr(geofabrik, "extrait_de_tuile", lambda *args: {"nom": "Var"})
    monkeypatch.setattr(franchissements, "disponibilite_overpass", lambda: False)
    assert a.disponibilite(zone) == {"pret": True, "source": "extrait", "nom": "Var"}
    monkeypatch.setattr(geofabrik, "extrait_de_tuile", lambda *args: None)
    monkeypatch.setattr(franchissements, "disponibilite_overpass", lambda: True)
    assert a.disponibilite(zone)["pret"] is True
    monkeypatch.setattr(franchissements, "disponibilite_overpass", lambda: False)
    assert a.disponibilite(zone)["pret"] is False



def test_routes_init_annonce_l_application(tmp_path):
    get, post = appli.Application(tmp_path).routes()
    assert get["init"]()["app"] == "hike2gpx"
    assert {"osm", "bdtopo", "extrait"} <= set(get)
    # Plus de téléchargement à la demande depuis la carte (tuile, extrait) : tout
    # part de lui-même ; seuls les réglages actualisent ou vident (donnees).
    assert set(post) == {"itineraire", "reglages", "moteur", "denivele", "communes", "langue", "arreter_calques", "donnees"}


def test_langue_choisie_gardee_dans_les_preferences(tmp_path):
    # /api/langue : le choix FR / EN du commun, à côté de la clé IGN.
    a = appli.Application(tmp_path)
    a.enregistrer_reglages({"cle_ign": "cle_test"})
    get, post = a.routes()
    assert get["langue"]()["code"] is None
    assert post["langue"]({"code": "en"})["enregistre"]
    autre = appli.Application(tmp_path)
    assert autre.routes()[0]["langue"]()["code"] == "en" and autre.reglages() == {"cle_ign": "cle_test", "renouvellement_jours": 30}


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
    # les réglages », « utile aussi pour actualiser les données rapidement ».
    installes = donnees_d_essai(tmp_path)
    monkeypatch.setattr(geofabrik, "installes", lambda dossier: [e for e in installes if e["base"].exists()])
    a = appli.Application(tmp_path)
    d = a.donnees()
    assert d["osm"] == {"fichiers": 3, "octets": 6} and d["bdtopo"] == {"fichiers": 1, "octets": 2}
    assert [(e["id"], e["provisoire"], e["octets"]) for e in d["extraits"]] == [
        ("fr-var", True, 1000), (REGION_PACA["id"], False, 1000)]
    assert [s["nom"] for s in d["brouter"]] == ["E5_N40"] and d["restes"] == {"fichiers": 1, "octets": 500}
    assert d["occupe"] == {"extrait": None, "brouter": False}
    # Vider : les tuiles se reliront d'elles-mêmes au besoin.
    assert a.agir_donnees({"action": "vider_osm"})["osm"]["fichiers"] == 0
    assert not list((tmp_path / "franchissements").iterdir()) and (tmp_path / "bdtopo" / "v1_866_120.json").exists()
    assert a.agir_donnees({"action": "vider_bdtopo"})["bdtopo"]["fichiers"] == 0
    # Actualiser : l'extrait repart, l'ancien sert jusqu'à la bascule.
    lances = []
    monkeypatch.setattr(geofabrik.Telechargements, "lancer", lambda self, region, **o: lances.append(region["id"]) or True)
    a.agir_donnees({"action": "actualiser_extrait", "cible": "fr-var"})
    assert lances == ["fr-var"]
    # Pendant son téléchargement, l'extrait ne se supprime pas.
    monkeypatch.setattr(geofabrik.Telechargements, "occupee", lambda self: True)
    monkeypatch.setattr(geofabrik.Telechargements, "etat", lambda self: {"id": "fr-var", "etape": "import"})
    assert a.agir_donnees({"action": "supprimer_extrait", "cible": "fr-var"}) == {
        "erreur": "Cet extrait se télécharge déjà."}
    monkeypatch.setattr(geofabrik.Telechargements, "occupee", lambda self: False)
    d = a.agir_donnees({"action": "supprimer_extrait", "cible": "fr-var"})
    assert [e["id"] for e in d["extraits"]] == [REGION_PACA["id"]] and not installes[0]["base"].exists()
    assert a.agir_donnees({"action": "nettoyer"})["restes"]["fichiers"] == 0
    assert a.agir_donnees({"action": "supprimer_extrait", "cible": "inconnu"}) == {"erreur": "Extrait inconnu."}
    assert a.agir_donnees({"action": "formater"}) == {"erreur": "Action inconnue."}


def test_vider_cache_unique_efface_toutes_les_donnees_locales(tmp_path):
    donnees_d_essai(tmp_path)
    for dossier, nom in (("gpx2elev", "profil.json"), ("brouter/maison", "etat.json")):
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
        assert resultat["chemin"] == str(chemin)
        assert any("nouvelle session" in ligne for ligne in resultat["lignes"])
        assert not any("ancienne session" in ligne for ligne in resultat["lignes"])
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
