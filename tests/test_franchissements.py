import math

import pytest

from hike2gpx import franchissements as fr

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
    calque = fr.voies_affichables(43.31, 6.01, 43.32, 6.02, tmp_path, interroger=lambda texte: carte.elements)
    assert {v["id"]: v["genre"] for v in calque["voies"]} == {sentier: "sentier", piste: "piste", route: "route"}
    assert [(b["id"], b["nature"]) for b in calque["barrieres"]] == [(cloture, "Clôture")]
    assert calque["voies"][0]["pts"][0] == [round(LAT0, 6), round(LON0 - 50 / KX, 6)]


def test_tuiles_et_requete():
    assert fr.tuiles_zone(43.31, 6.01, 43.34, 6.06) == [(866, 120), (866, 121)]
    assert fr.bornes_tuile(866, 120) == (43.3, 6.0, 43.35, 6.05)
    # 43.30 / 0.05 vaut 865.999… : une borne exacte reste dans sa tuile.
    assert fr.tuiles_zone(43.30, 6.00, 43.3499, 6.0499) == [(866, 120)]
    texte = fr.requete(*fr.bornes_tuile(866, 120))
    assert "(43.300000,6.000000,43.350000,6.050000)" in texte and "motorway" in texte
    assert 'rel(bw.voies)["route"~"^(hiking|foot)$"]' in texte


def test_cache_de_tuile(tmp_path):
    appels = []

    def interroger(texte):
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
