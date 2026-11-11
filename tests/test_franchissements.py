import json
import math

import pytest

from hike2gpx import franchissements as fr, geofabrik


def test_disponibilite_tuile_utilise_le_cache_valide_sans_overpass(tmp_path, monkeypatch):
    monkeypatch.setattr(geofabrik, "extrait_de_tuile", lambda *args: None)
    i, j = fr.tuile_du_point(43.3, 6.0)
    assert not fr.tuile_disponible(i, j, tmp_path, maintenant=lambda: 1000)
    dossier = tmp_path / "overpass"
    dossier.mkdir()
    (dossier / f"v{fr.VERSION_DONNEES}_{i}_{j}.json").write_text(
        json.dumps({"fetched_at": 900, "elements": []}), encoding="utf-8")
    assert fr.tuile_disponible(i, j, tmp_path, maintenant=lambda: 1000)
    assert not fr.tuile_disponible(i, j, tmp_path, maintenant=lambda: 900 + fr.TTL_S + 1)

LAT0, LON0 = 43.3, 6.0
KX = fr.M_PAR_DEGRE * math.cos(math.radians(LAT0))


class Carte:
    """Petite carte OSM au format Overpass (out body geom), en mètres autour
    d'un point du Var. Seuls les nœuds étiquetés deviennent des éléments,
    comme dans une vraie réponse."""

    def __init__(self):
        self.elements, self.positions, self.suivant = [], {}, 1

    def _id(self):
        self.suivant += 1
        return self.suivant

    def noeud(self, x, y, **tags):
        nid = self._id()
        self.positions[nid] = (LAT0 + y / fr.M_PAR_DEGRE, LON0 + x / KX)
        if tags:
            lat, lon = self.positions[nid]
            self.elements.append({"type": "node", "id": nid, "lat": lat, "lon": lon, "tags": tags})
        return nid

    def voie(self, noeuds, **tags):
        wid = self._id()
        self.elements.append({"type": "way", "id": wid, "nodes": list(noeuds), "tags": tags,
                              "geometry": [{"lat": self.positions[n][0], "lon": self.positions[n][1]} for n in noeuds]})
        return wid

    def chemin(self, *points, **tags):
        return self.voie([self.noeud(x, y) for x, y in points], highway=tags.pop("highway", "path"), **tags)

    def cloture(self, *points, **tags):
        return self.voie([self.noeud(x, y) for x, y in points], barrier=tags.pop("barrier", "fence"), **tags)

    def itineraire(self, *voies):
        self.elements.append({"type": "relation", "id": self._id(), "tags": {"type": "route", "route": "hiking"},
                              "members": [{"type": "way", "ref": w, "role": ""} for w in voies]})


def xy(lon, lat):
    return (lon - LON0) * KX, (lat - LAT0) * fr.M_PAR_DEGRE


def coupe_traverse(coupe, a, b):
    return fr._intersection(xy(*coupe[0]), xy(*coupe[1]), a, b) is not None


def test_cloture_traversee_sans_ouverture_bloque_et_coupe_le_chemin():
    carte = Carte()
    carte.chemin((-50, 0), (50, 0))
    carte.cloture((0, -30), (0, 30))
    [f] = fr.analyser(carte.elements)
    assert (f["statut"], f["nature"]) == ("blocked", "Clôture")
    assert f["raison"] == "Obstacle linéaire traversé sans ouverture cartographiée"
    [coupe] = f["coupes"]
    assert coupe_traverse(coupe, (-50, 0), (50, 0))
    assert math.dist(xy(*coupe[0]), xy(*coupe[1])) == pytest.approx(2 * fr.DEMI_COUPE_M, abs=.01)
    assert abs(f["lat"] - LAT0) < 1e-6 and abs(f["lon"] - LON0) < 1e-6


def test_cloture_parallele_ne_bloque_pas():
    carte = Carte()
    carte.chemin((-50, 0), (50, 0))
    carte.cloture((-50, 2), (50, 2))
    assert fr.analyser(carte.elements) == []


@pytest.mark.parametrize("tags", [{"barrier": "gap"}, {"barrier": "gate", "access": "yes"},
                                  {"barrier": "gate", "foot": "permissive"}])
def test_ouverture_libre_sur_la_cloture_laisse_passer(tags):
    carte = Carte()
    carte.chemin((-50, 0), (50, 0))
    ouverture = carte.noeud(0, 1.5, **tags)
    carte.voie([carte.noeud(0, -30), ouverture, carte.noeud(0, 30)], barrier="fence")
    assert fr.analyser(carte.elements) == []


@pytest.mark.parametrize("tags, statut", [({"barrier": "gate"}, "uncertain"),
                                          ({"barrier": "gate", "access": "private"}, "blocked"),
                                          ({"barrier": "gate", "foot": "no"}, "blocked"),
                                          ({"barrier": "gate", "locked": "yes"}, "blocked")])
def test_portail_voisin_juge_comme_s_il_etait_sur_le_chemin(tags, statut):
    # Audit B01 : le portail est sur la clôture, à 1,5 m du chemin qu'il ne
    # porte pas. Il ne doit pas effacer la clôture sans être jugé lui-même.
    carte = Carte()
    carte.chemin((-50, 0), (50, 0))
    portail = carte.noeud(0, 1.5, **tags)
    carte.voie([carte.noeud(0, -30), portail, carte.noeud(0, 30)], barrier="fence")
    [f] = fr.analyser(carte.elements)
    assert (f["statut"], f["nature"], f["osm"]) == (statut, "Portail", f"node/{portail}")
    [coupe] = f["coupes"]
    assert coupe_traverse(coupe, (-50, 0), (50, 0))


def test_portail_voisin_porte_par_le_chemin_n_est_juge_qu_une_fois():
    carte = Carte()
    portail = carte.noeud(0, 0, barrier="gate", access="private")
    carte.voie([carte.noeud(-50, 0), portail, carte.noeud(50, 0)], highway="path")
    carte.voie([carte.noeud(0, -30), portail, carte.noeud(0, 30)], barrier="fence")
    [f] = fr.analyser(carte.elements)
    assert (f["statut"], f["cle"]) == ("blocked", f"noeud-{portail}")


@pytest.mark.parametrize("meme_noeud", [True, False])
def test_noeud_repete_ou_superpose_ne_casse_pas_l_analyse(meme_noeud):
    # Audit B08 : un lien de longueur nulle divisait par zéro.
    carte = Carte()
    portail = carte.noeud(0, 0, barrier="gate", access="private")
    double = portail if meme_noeud else carte.noeud(0, 0)
    carte.voie([carte.noeud(-50, 0), portail, double, carte.noeud(50, 0)], highway="path")
    [f] = fr.analyser(carte.elements)
    assert f["statut"] == "blocked"
    # Les deux côtés du portail restent coupés, sur les vrais liens.
    assert {round(xy(*c[0])[0]) for c in f["coupes"]} == {-2, 2}


def test_portail_sur_le_chemin_sans_acces_est_a_verifier_et_coupe_les_deux_cotes():
    carte = Carte()
    portail = carte.noeud(0, 0, barrier="gate")
    carte.voie([carte.noeud(-50, 0), portail, carte.noeud(50, 0)], highway="track")
    carte.voie([carte.noeud(0, -30), portail, carte.noeud(0, 30)], barrier="fence")
    [f] = fr.analyser(carte.elements)
    assert (f["statut"], f["nature"], f["osm"]) == ("uncertain", "Portail", f"node/{portail}")
    assert len(f["coupes"]) == 2
    assert coupe_traverse(f["coupes"][0], (-50, 0), (0, 0)) and coupe_traverse(f["coupes"][1], (0, 0), (50, 0))


@pytest.mark.parametrize("tags, attendu", [
    ({"barrier": "gate", "access": "private"}, "blocked"),
    ({"barrier": "gate", "locked": "yes"}, "blocked"),
    ({"barrier": "gate", "access": "private", "foot": "yes"}, None),
    ({"barrier": "stile"}, None),
    ({"barrier": "fence"}, "blocked"),
    ({"barrier": "gate", "opening_hours": "Mo-Fr 08:00-18:00"}, "uncertain"),
    # Audit B07 : les horaires ne lèvent pas une interdiction piétonne explicite.
    ({"barrier": "gate", "foot": "no", "opening_hours": "24/7"}, "blocked"),
    ({"barrier": "gate", "foot": "no", "access:conditional": "yes @ (Mo-Fr)"}, "blocked"),
    ({"barrier": "gate", "foot": "no", "foot:conditional": "yes @ (Sa-Su)"}, "uncertain"),
])
def test_noeud_barriere_jugé_par_les_regles_de_gpx2elev(tags, attendu):
    carte = Carte()
    obstacle = carte.noeud(0, 0, **tags)
    carte.voie([carte.noeud(-50, 0), obstacle, carte.noeud(50, 0)], highway="track")
    resultat = fr.analyser(carte.elements)
    assert [f["statut"] for f in resultat] == ([attendu] if attendu else [])


def test_cloture_qui_s_arrete_sur_le_chemin_ne_le_traverse_pas():
    carte = Carte()
    debut, fin = carte.noeud(-50, 0), carte.noeud(50, 0)
    contact = carte.noeud(0, 0)
    carte.voie([debut, contact, fin], highway="path")
    carte.voie([carte.noeud(0, 40), contact], barrier="fence")
    assert fr.analyser(carte.elements) == []


def test_cloture_qui_finit_juste_apres_le_chemin_se_contourne():
    carte = Carte()
    carte.chemin((-50, 0), (50, 0))
    carte.cloture((0, 40), (0, -1.5))
    assert fr.analyser(carte.elements) == []


def test_noeud_commun_non_etiquete_bloque_d_un_seul_cote():
    carte = Carte()
    commun = carte.noeud(0, 0)
    carte.voie([carte.noeud(-50, 0), commun, carte.noeud(50, 0)], highway="path")
    carte.voie([carte.noeud(0, -30), commun, carte.noeud(0, 30)], barrier="fence")
    [f] = fr.analyser(carte.elements)
    assert f["statut"] == "blocked" and len(f["coupes"]) == 1


def test_carrefour_sur_une_cloture_coupe_le_passage_d_un_cote_a_l_autre():
    carte = Carte()
    centre = carte.noeud(0, 0)
    carte.voie([carte.noeud(-50, 0), centre], highway="track")      # s'arrête sur la clôture
    carte.voie([centre, carte.noeud(50, 10)], highway="path")       # et repart de l'autre côté
    carte.voie([centre, carte.noeud(50, -10)], highway="path")
    carte.cloture((0, -30), (0, 30))
    [f] = fr.analyser(carte.elements)
    assert f["statut"] == "blocked" and len(f["coupes"]) == 1      # le côté qui n'a qu'un lien


def test_pont_et_tunnel_passent_au_dessus_ou_au_dessous():
    carte = Carte()
    carte.chemin((-50, 0), (50, 0), bridge="yes", layer="1")
    carte.chemin((-50, 10), (50, 10), tunnel="yes", layer="-1")
    carte.cloture((0, -30), (0, 30))
    assert fr.analyser(carte.elements) == []


def test_niveau_different_est_a_verifier():
    carte = Carte()
    carte.chemin((-50, 0), (50, 0))
    carte.cloture((0, -30), (0, 30), layer="1")
    [f] = fr.analyser(carte.elements)
    assert (f["statut"], f["raison"]) == ("uncertain", fr.NIVEAU)


def test_sentier_balise_passage_probable():
    carte = Carte()
    gr = carte.chemin((-50, 0), (50, 0))
    carte.cloture((0, -30), (0, 30))
    carte.itineraire(gr)
    [f] = fr.analyser(carte.elements)
    assert (f["statut"], f["raison"]) == ("uncertain", fr.PROBABLE)


def test_bordure_et_autres_lignes_franchissables_ignorees():
    carte = Carte()
    carte.chemin((-50, 0), (50, 0))
    carte.cloture((0, -30), (0, 30), barrier="kerb")
    assert fr.analyser(carte.elements) == []


def test_cloture_qui_touche_le_chemin_et_repart_du_meme_cote():
    carte = Carte()
    carte.chemin((-50, 0), (50, 0))
    carte.cloture((-20, 30), (0, 0), (20, 30))
    assert fr.analyser(carte.elements) == []


def test_cloture_decoupee_pile_sur_le_chemin_reste_une_cloture():
    carte = Carte()
    carte.chemin((-50, 0), (50, 0))
    jonction = carte.noeud(0, 0)
    carte.voie([carte.noeud(0, -30), jonction], barrier="fence")
    carte.voie([jonction, carte.noeud(0, 30)], barrier="fence")
    [f] = fr.analyser(carte.elements)
    assert f["statut"] == "blocked"


def test_cloture_fermee_autour_d_un_champ_coupe_deux_fois():
    carte = Carte()
    carte.chemin((-100, 0), (100, 0))
    carte.cloture((-40, -40), (40, -40), (40, 40), (-40, 40), (-40, -40))
    assert sorted(round(f["lon"], 6) for f in fr.analyser(carte.elements)) == \
        sorted(round(LON0 + x / KX, 6) for x in (-40, 40))


def test_voies_affichables_par_genre_sans_les_bordures(tmp_path):
    carte = Carte()
    sentier = carte.chemin((-50, 0), (50, 0))
    piste = carte.chemin((-50, 20), (50, 20), highway="track")
    route = carte.chemin((-50, 40), (50, 40), highway="residential")
    cloture = carte.cloture((0, -30), (0, 30))
    carte.cloture((10, -30), (10, 30), barrier="kerb")
    calque = fr.voies_affichables(43.31, 6.01, 43.32, 6.02, tmp_path, interroger=lambda texte, **_: carte.elements)
    assert {v["id"]: v["genre"] for v in calque["voies"]} == {sentier: "sentier", piste: "piste", route: "route"}
    assert [(b["id"], b["nature"]) for b in calque["barrieres"]] == [(cloture, "Clôture")]
    assert calque["voies"][0]["pts"][0] == [round(LAT0, 6), round(LON0 - 50 / KX, 6)]


def test_calque_osm_contient_les_franchissements_sans_itineraire(tmp_path):
    carte = Carte()
    portail = carte.noeud(0, 40, barrier="gate")
    carte.voie([carte.noeud(-50, 40), portail, carte.noeud(50, 40)], highway="track")
    carte.chemin((-50, 0), (50, 0))
    cloture = carte.cloture((0, -20), (0, 20))
    donnees = fr.voies_affichables(43.31, 6.01, 43.32, 6.02, tmp_path,
                                   interroger=lambda texte, **_: carte.elements)
    points = donnees["franchissements"]
    assert any(p["osm"] == f"node/{portail}" and p["statut"] == "uncertain" for p in points)
    assert any(p["osm"] == f"way/{cloture}" and p["statut"] == "blocked" for p in points)
    assert {"cle", "statut", "raison", "nature", "lat", "lon", "osm"} == set(points[0])
    assert [(b["id"], b["nature"]) for b in donnees["barrieres"]] == [(cloture, "Clôture")]


def _chemins(*voies):
    """{id: (tags, nœuds, points)} : chaque voie (id, tags, [(nœud, lat, lon), …])."""
    return {ident: (tags, [n for n, _, _ in pts], [(la, lo) for _, la, lo in pts]) for ident, tags, pts in voies}


# La route est reliée au réseau, comme toute route : une bretelle part de son nœud 10.
ROUTE = (1, {"highway": "tertiary"}, [(10, 48.3780, -77.1340), (11, 48.3780, -77.1300)])
BRETELLE = (9, {"highway": "tertiary"}, [(10, 48.3780, -77.1340), (90, 48.3700, -77.1400)])
ZONE = (48.37, -77.14, 48.39, -77.12)


def test_un_sentier_relie_a_rien_qui_finit_a_cinq_metres_d_une_route_est_signale():
    # Le cas de Nico au Québec : le sentier finit à 5 m de la route, et n'est relié
    # à aucun autre chemin. Le calcul ne peut pas y entrer : c'est ce qui le gêne.
    sentier = (2, {"highway": "footway"}, [(20, 48.3790, -77.1320), (21, 48.378045, -77.1320)])
    [j] = fr.jonctions_manquees(_chemins(ROUTE, BRETELLE, sentier), *ZONE)
    assert j["voie"] == 2 and j["vers"] == 1 and j["osm"] == "way/2" and j["cle"] == "jonction-2-isole"
    assert j["isole"] is True and 4.5 < j["distance_m"] < 5.5
    assert (j["lat"], j["lon"]) == (48.378045, -77.132), "le point du sentier le plus proche de la route"


def test_un_sentier_relie_a_rien_est_signale_la_ou_il_passe_le_plus_pres_pas_seulement_a_son_bout():
    # Un sentier isolé qui longe la route à 4 m en son milieu, ses bouts plus loin.
    sentier = (2, {"highway": "path"}, [(20, 48.3790, -77.1330), (21, 48.378036, -77.1320), (22, 48.3790, -77.1310)])
    [j] = fr.jonctions_manquees(_chemins(ROUTE, BRETELLE, sentier), *ZONE)
    assert j["isole"] and 3.5 < j["distance_m"] < 4.5 and abs(j["lon"] - (-77.1320)) < 1e-5
    # Au-delà du seuil (6 m), un chemin isolé n'est qu'un chemin à part.
    loin = (3, {"highway": "path"}, [(30, 48.3790, -77.1320), (31, 48.378072, -77.1320)])       # 8 m
    assert fr.jonctions_manquees(_chemins(ROUTE, BRETELLE, loin), *ZONE) == []


def test_une_impasse_reliee_qui_finit_pres_d_un_chemin_n_est_pas_signalee():
    # L'allée part d'une rue (nœud commun 12) et s'arrête à 3 m d'une autre route :
    # elle reste accessible, et ne gêne aucun itinéraire.
    rue = (5, {"highway": "residential"}, [(12, 48.3800, -77.1320), (13, 48.3800, -77.1300)])
    allee = (6, {"highway": "service"}, [(12, 48.3800, -77.1320), (60, 48.378027, -77.1320)])        # 3 m
    assert fr.jonctions_manquees(_chemins(ROUTE, BRETELLE, rue, allee), *ZONE) == []
    # Mais un bout qui s'arrête presque contre l'autre route, à moins d'un mètre,
    # est une accroche ratée à la saisie : le passage qui devait exister est coupé.
    presque = (7, {"highway": "service"}, [(12, 48.3800, -77.1320), (70, 48.378007, -77.1320)])      # 0,8 m
    [j] = fr.jonctions_manquees(_chemins(ROUTE, BRETELLE, rue, presque), *ZONE)
    assert j["voie"] == 7 and j["vers"] == 1 and j["isole"] is False and j["cle"] == "jonction-7-70"
    assert j["distance_m"] <= fr.SEUIL_RELIE_M


def test_un_cul_de_sac_un_raccord_fait_un_pont_et_une_amorce_ne_sont_pas_signales():
    points_route = [(10, 48.3780, -77.1340), (11, 48.3780, -77.1320), (12, 48.3780, -77.1300)]
    route = (1, {"highway": "tertiary"}, points_route)
    bretelle = BRETELLE
    zone = (48.37, -77.14, 48.39, -77.12)
    # Un cul-de-sac : le sentier finit à 100 m de tout ; il ne touche rien et ce n'est pas une erreur.
    loin = (2, {"highway": "path"}, [(20, 48.3800, -77.1320), (21, 48.3789, -77.1320)])
    assert fr.jonctions_manquees(_chemins(route, bretelle, loin), *zone) == []
    # Raccordé : le bout du sentier est un nœud de la route.
    raccorde = (3, {"highway": "path"}, [(30, 48.3790, -77.1320), (11, 48.3780, -77.1320)])
    assert fr.jonctions_manquees(_chemins(route, bretelle, raccorde), *zone) == []
    # Sous un pont : pas de raccord à attendre.
    pont = (1, {"highway": "tertiary", "bridge": "yes"}, points_route)
    presque = (4, {"highway": "path"}, [(40, 48.3790, -77.1320), (41, 48.378018, -77.1320)])       # à 2 m
    assert len(fr.jonctions_manquees(_chemins(route, bretelle, presque), *zone)) == 1, "sans pont, il serait signalé"
    assert fr.jonctions_manquees(_chemins(pont, bretelle, presque), *zone) == []
    # L'amorce d'une impasse reste près de la rue d'où elle part : elle la touche déjà.
    amorce = (5, {"highway": "service"}, [(11, 48.3780, -77.1320), (50, 48.37808, -77.1320)])
    assert fr.jonctions_manquees(_chemins(route, bretelle, amorce), *zone) == []
    # Hors de la zone lue : la tuile voisine s'en charge.
    assert fr.jonctions_manquees(_chemins(route, bretelle, presque), 48.3785, -77.14, 48.39, -77.12) == []


def test_tuiles_et_requete():
    assert fr.tuiles_zone(43.31, 6.01, 43.34, 6.06) == [(866, 120), (866, 121)]
    assert fr.bornes_tuile(866, 120) == (43.3, 6.0, 43.35, 6.05)
    # 43.30 / 0.05 vaut 865.999… : une borne exacte reste dans sa tuile.
    assert fr.tuiles_zone(43.30, 6.00, 43.3499, 6.0499) == [(866, 120)]
    texte = fr.requete(*fr.bornes_tuile(866, 120))
    assert "(43.300000,6.000000,43.350000,6.050000)" in texte and "motorway" in texte
    assert 'rel(bw.voies)["route"~"^(hiking|foot)$"]' in texte
    # Ce qu'un calque lit vraiment : les tuiles entières autour de la vue.
    assert fr.bornes_zone(43.31, 6.01, 43.34, 6.06) == (43.3, 6.0, 43.35, 6.1)


def test_cache_de_tuile(tmp_path):
    appels = []

    def interroger(texte, **_):
        appels.append(texte)
        carte = Carte()
        carte.chemin((-50, 0), (50, 0))
        carte.cloture((0, -30), (0, 30))
        return carte.elements

    i, j = 866, 120
    horloge = [1000.0]
    options = dict(interroger=interroger, maintenant=lambda: horloge[0])
    premier = fr.franchissements_tuile(i, j, tmp_path, **options)
    assert len(appels) == 1 and [f["statut"] for f in premier] == ["blocked"]
    assert fr.franchissements_tuile(i, j, tmp_path, **options) == premier and len(appels) == 1
    horloge[0] += fr.TTL_S + 1
    fr.franchissements_tuile(i, j, tmp_path, **options)
    assert len(appels) == 2
    with pytest.raises(fr.ErreurDonnees):
        fr.charger_tuile(i, j + 1, tmp_path, en_ligne=False)


def test_overpass_refus_definitif_et_passager(monkeypatch):
    import urllib.error

    tentatives = []

    def refuser(demande, timeout):
        tentatives.append(1)
        raise urllib.error.HTTPError(fr.ENDPOINT, 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(fr.urllib.request, "urlopen", refuser)
    with pytest.raises(fr.ErreurDonnees, match="ne répond pas"):
        fr.interroger("x", attendre=lambda s: None)
    assert len(tentatives) == fr.TENTATIVES


def test_overpass_jamais_plus_de_deux_requetes_a_la_fois(monkeypatch):
    # overpass-api.de répond 429 au-delà de deux requêtes simultanées par
    # adresse : six lectures lancées ensemble passent deux par deux.
    import io
    import threading
    import time

    actives, maximum, verrou = [0], [0], threading.Lock()

    def lire(demande, timeout):
        with verrou:
            actives[0] += 1
            maximum[0] = max(maximum[0], actives[0])
        time.sleep(0.05)
        with verrou:
            actives[0] -= 1
        return io.BytesIO(b'{"elements": []}')

    monkeypatch.setattr(fr.urllib.request, "urlopen", lire)
    fils = [threading.Thread(target=fr.interroger, args=("x",)) for _ in range(6)]
    for fil in fils:
        fil.start()
    for fil in fils:
        fil.join()
    assert maximum[0] == fr.CRENEAUX == 2


def test_vue_quittee_renonce_a_overpass(monkeypatch):
    # Une vue que la carte a quittée n'attend pas de créneau et n'interroge
    # plus Overpass : c'était l'empilement des calques du 2026-10-19.
    monkeypatch.setattr(fr.urllib.request, "urlopen", lambda *a, **o: pytest.fail("Overpass interrogé"))
    with pytest.raises(fr.VueRemplacee):
        fr.interroger("x", continuer=lambda: False)
    for _ in range(fr.CRENEAUX):
        fr._creneaux.acquire()
    try:
        with pytest.raises(fr.VueRemplacee):      # créneaux pris : elle renonce à attendre
            fr.interroger("x", continuer=lambda: False)
    finally:
        for _ in range(fr.CRENEAUX):
            fr._creneaux.release()


def test_une_pause_d_overpass_s_arrete_des_que_la_tuile_n_attend_plus(monkeypatch):
    # Les pauses entre deux essais (15 puis 30 s) s'écoulent seconde par
    # seconde : une vue quittée, ou un extrait installé entre-temps, les arrête.
    import urllib.error

    def refuser(demande, timeout):
        raise urllib.error.HTTPError(fr.ENDPOINT, 502, "Bad Gateway", {}, None)

    monkeypatch.setattr(fr.urllib.request, "urlopen", refuser)
    pauses = []
    with pytest.raises(fr.VueRemplacee):
        fr.interroger("x", attendre=pauses.append, continuer=lambda: len(pauses) < 3)
    assert pauses == [1, 1, 1]


def test_l_extrait_installe_pendant_l_attente_d_overpass_prend_le_relais(tmp_path, monkeypatch):
    # Essai réel du 2026-10-20 : le Var installé au bout de 39 s, la tuile
    # suivante attendait encore Overpass, en HTTP 502, jusqu'à 80 s.
    installe = []
    tuile = {"version": fr.VERSION_DONNEES, "fetched_at": 0.0, "bornes": fr.bornes_tuile(866, 120),
             "elements": [], "source": "geofabrik:fr-var:2026-10-19T01:38:06Z"}
    monkeypatch.setattr(fr, "_couverte", lambda i, j, dossier: bool(installe))
    monkeypatch.setattr(fr, "tuile_de_l_extrait", lambda i, j, dossier: tuile if installe else None)

    def interroger(texte, continuer, **_):
        installe.append(True)                   # l'extrait s'installe pendant l'attente
        if not continuer():
            raise fr.VueRemplacee()
        pytest.fail("la tuile attend encore Overpass, l'extrait installé")

    assert fr.charger_tuile(866, 120, tmp_path, interroger=interroger) is tuile
    # Un extrait présent mais illisible : Overpass, comme avant, sans passer
    # pour une vue quittée.
    monkeypatch.setattr(fr, "tuile_de_l_extrait", lambda i, j, dossier: None)
    vus = []

    def interroger_ensuite(texte, continuer, **_):
        vus.append(continuer())
        if not vus[-1]:
            raise fr.VueRemplacee()
        return []

    assert fr.charger_tuile(866, 121, tmp_path, interroger=interroger_ensuite)["elements"] == []
    assert vus == [False, True]


def test_calque_osm_s_arrete_avant_la_tuile_suivante(tmp_path):
    lues = []

    def interroger(texte, **_):
        lues.append(texte)
        return []

    restantes = iter([True, False])
    with pytest.raises(fr.VueRemplacee):
        fr.voies_affichables(43.31, 6.01, 43.34, 6.06, tmp_path, interroger=interroger,
                             continuer=lambda: next(restantes, False))
    assert len(lues) == 1
