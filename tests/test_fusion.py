import math

import pytest

from hike2gpx import franchissements as fr, fusion

LAT0, LON0 = 43.3, 6.0
KX = 111195.08 * math.cos(math.radians(LAT0))


def geo(x, y):
    return LAT0 + y / 111195.08, LON0 + x / KX


class Osm:
    """Voies OSM au format Overpass (out body geom), en mètres."""

    def __init__(self):
        self.elements, self.suivant = [], 100

    def voie(self, *points, **tags):
        ids = []
        geometrie = []
        for x, y in points:
            self.suivant += 1
            ids.append(self.suivant)
            lat, lon = geo(x, y)
            geometrie.append({"lat": lat, "lon": lon})
        self.suivant += 1
        self.elements.append({"type": "way", "id": self.suivant, "nodes": ids, "geometry": geometrie,
                              "tags": tags or {"highway": "path"}})
        return self.suivant


def troncon(*points, nature="Sentier", ident="T", **attributs):
    return {"id": ident, "nature": nature, "pts": [list(geo(x, y)) for x, y in points], **attributs}


def reseau(osm):
    r = fusion.Reseau()
    r.ajouter_osm(osm.elements)
    return r


def test_chemin_ign_entre_deux_sentiers_osm_est_garde_et_raccorde():
    osm = Osm()
    sud = osm.voie((0, 0), (500, 0))
    nord = osm.voie((0, 200), (500, 200))
    r = reseau(osm)
    assert r.ajouter_ign([troncon((250, 0), (250, 100), (250, 200))]) == 1
    [wid] = r.ign
    ids, tags = r.voies[wid]
    assert tags == fusion.ETIQUETTE
    # Les bouts sont des nœuds insérés au milieu des deux sentiers OSM.
    assert ids[0] in r.voies[sud][0][1:-1] and ids[-1] in r.voies[nord][0][1:-1]
    assert len(r.voies[sud][0]) == 3 and len(r.voies[nord][0]) == 3


def test_chemin_ign_qui_double_un_sentier_osm_est_ecarte():
    osm = Osm()
    osm.voie((0, 0), (500, 0))
    r = reseau(osm)
    assert r.ajouter_ign([troncon((0, 3), (250, 4), (500, 3))]) == 0 and r.ign == []


def test_sommet_osm_proche_reutilise_plutot_qu_un_noeud_insere():
    osm = Osm()
    sud = osm.voie((0, 0), (250, 0), (500, 0))
    r = reseau(osm)
    r.ajouter_ign([troncon((250.4, 0), (250, 300))])
    assert r.voies[r.ign[0]][0][0] == r.voies[sud][0][1] and len(r.voies[sud][0]) == 3


def test_deux_troncons_ign_partagent_leur_point_commun():
    osm = Osm()
    osm.voie((0, 0), (500, 0))
    r = reseau(osm)
    r.ajouter_ign([troncon((250, 0), (250, 300), ident="A"), troncon((250, 300), (400, 600), ident="B")])
    a, b = (r.voies[w][0] for w in r.ign)
    assert a[-1] == b[0]
    assert b[-1] not in {n for w, (ids, _) in r.voies.items() if w not in r.ign for n in ids}


def test_troncons_vectoriels_se_rejoignent_aux_bords_des_tuiles():
    r = fusion.Reseau()
    premier = troncon((0, 0), (100, 0), ident="BM:1", land="SN", niveau=0,
                      bords=[False, True])
    second = troncon((100.6, 0), (200, 0), ident="BM:2", land="SN", niveau=0,
                     bords=[True, False])
    autre_niveau = troncon((100, 0), (200, 50), ident="BM:3", land="SN", niveau=1,
                           bords=[True, False])
    assert r.ajouter_ign([premier, second, autre_niveau], source="atkis") == 3
    a, b, c = (r.voies[wid][0] for wid in r.ign)
    assert a[-1] == b[0]
    assert a[-1] != c[0]


def test_autoroute_et_bac_exclus():
    osm = Osm()
    osm.voie((0, 0), (500, 0))
    r = reseau(osm)
    assert r.ajouter_ign([troncon((250, 0), (250, 300), nature="Type autoroutier"),
                          troncon((250, 0), (250, 300), nature="Bac ou liaison maritime")]) == 0


def test_identifiants_ajoutes_serres_et_elements_pour_les_franchissements():
    osm = Osm()
    osm.voie((0, 0), (500, 0))
    r = reseau(osm)
    plus_grand = max(r.noeuds)
    r.ajouter_ign([troncon((250, 0), (250, 100), (250, 300))])
    assert all(plus_grand < n < plus_grand + 10 for n in r.noeuds if n > plus_grand)
    [element] = [e for e in r.elements() if e["id"] in r.ign]
    assert element["type"] == "way" and element["tags"]["hike2gpx"] == "ign"
    assert len(element["nodes"]) == len(element["geometry"]) == 3


@pytest.mark.parametrize("valeur, foot", [(None, None), ("Libre", None), ("A péage", None),
                                          ("Restreint aux ayants droit", "private"),
                                          ("Valeur jamais vue", "private")])
def test_acces_pieton_ign_conserve(valeur, foot):
    # Audit B14 : une restriction piétonne de la BD TOPO doit survivre à la fusion.
    osm = Osm()
    osm.voie((0, 0), (500, 0))
    r = reseau(osm)
    r.ajouter_ign([troncon((250, 0), (250, 300), acces_pieton=valeur, prive=True)])
    tags = r.voies[r.ign[0]][1]
    assert tags.get("foot") == foot and tags["hike2gpx"] == "ign" and "access" not in tags


def test_part_couverte_ne_depend_pas_du_decoupage():
    # Audit B15 : 100 m de tronçon dont les 20 premiers longent une voie OSM ;
    # deux sommets, ou un sommet tous les 50 cm sur ces 20 m, même géométrie.
    osm = Osm()
    osm.voie((0, 0), (20, 0))
    segments = reseau(osm).segments_osm()
    simple = [list(geo(0, 0)), list(geo(100, 0))]
    dense = [list(geo(k / 2, 0)) for k in range(41)] + [list(geo(100, 0))]
    part, part_dense = fusion.parts_couvertes([simple, dense], segments)
    assert part == pytest.approx(part_dense) and part < fusion.PART_COUVERTE_MAX


def test_parts_couvertes_comme_la_mesure_point_par_point():
    # Le calcul groupé doit rendre exactement la mesure brute, échantillon par
    # échantillon et segment par segment : près du seuil de 12 m, sur un long
    # segment découpé en morceaux, et sur un segment de longueur nulle.
    osm = Osm()
    osm.voie((0, 0), (300, 0))
    osm.voie((0, 50), (5, 50), (5, 50), (400, 60))
    osm.voie((150, -200), (150, 200))
    segments = reseau(osm).segments_osm()
    lignes = [[list(geo(0, d)), list(geo(300, d))] for d in (11.9, 12.1, -11.95, 30, 38)] \
        + [[list(geo(140, -100)), list(geo(160, 100))], [list(geo(-50, 0)), list(geo(-10, 0))]]
    attendu = []
    for pts in lignes:
        lat, lon = fusion._echantillons(pts)
        couverts = sum(min(fr._distance_segment((0.0, 0.0), fusion._xy(s[0], s[1], la, lo), fusion._xy(s[2], s[3], la, lo))
                           for s in segments) <= fusion.COUVERT_M for la, lo in zip(lat, lon))
        attendu.append(couverts / len(lat))
    assert list(fusion.parts_couvertes(lignes, segments)) == attendu
    # Le jeu d'essai passe bien des deux côtés du seuil : à 11,9 m tout est
    # couvert, à 12,1 m seulement l'abord du sentier qui croise.
    assert attendu[0] == 1.0 and 0 < attendu[1] < 0.2


def test_raccord_osm_ign_sur_une_cloture_est_coupe():
    # Audit B16 : un sentier OSM venu du nord et un tronçon IGN venu du sud
    # s'arrêtent tous deux sur une clôture ; leur raccord la traverse.
    osm = Osm()
    osm.voie((-50, 0), (50, 0), barrier="fence")
    osm.voie((0, 100), (0, 0))
    r = reseau(osm)
    assert fr.analyser(osm.elements) == []
    r.ajouter_ign([troncon((0, -100), (0, 0))])
    statuts = [f["statut"] for f in fr.analyser(r.elements())]
    assert statuts == ["blocked"]


def test_pbf_relu(tmp_path):
    osmium = pytest.importorskip("osmium")
    osm = Osm()
    osm.voie((0, 0), (500, 0))
    osm.elements.append({"type": "relation", "id": 7, "tags": {"route": "hiking"},
                         "members": [{"type": "way", "ref": osm.elements[0]["id"], "role": ""}]})
    r = reseau(osm)
    r.ajouter_ign([troncon((250, 0), (250, 300))])
    chemin = tmp_path / "zone.osm.pbf"
    r.ecrire_pbf(chemin)
    voies, relations, ign = 0, 0, []
    for o in osmium.FileProcessor(str(chemin)):
        if o.is_way():
            voies += 1
            if o.tags.get("hike2gpx") == "ign":
                ign.append(o.id)
        relations += o.is_relation()
    assert (voies, relations, ign) == (2, 1, r.ign)
