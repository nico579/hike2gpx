import urllib.error

import pytest

from hike2gpx import bdtopo
from hike2gpx.franchissements import ErreurDonnees


def entite(cleabs, coordonnees, nature="Sentier", genre="LineString", **proprietes):
    return {"type": "Feature", "id": f"troncon_de_route.{cleabs}",
            "geometry": {"type": genre, "coordinates": coordonnees},
            "properties": {"cleabs": cleabs, "nature": nature, **proprietes}}


def test_lignes_inversent_lon_lat_et_ignorent_l_altitude():
    assert bdtopo._lignes({"type": "LineString", "coordinates": [[6.01, 43.3, 500.5], [6.02, 43.31, 510]]}) == \
        [[[43.3, 6.01], [43.31, 6.02]]]
    multi = {"type": "MultiLineString", "coordinates": [[[6, 43], [6.1, 43.1]], [[7, 44], [7.1, 44.1]]]}
    assert len(bdtopo._lignes(multi)) == 2
    assert bdtopo._lignes({"type": "Point", "coordinates": [6, 43]}) == []
    assert bdtopo._lignes({"type": "LineString", "coordinates": [[6, 43], ["x", 43]]}) == []


def test_pagination(monkeypatch):
    monkeypatch.setattr(bdtopo, "PAGE", 2)
    pages = [[entite("A", [[6, 43], [6.1, 43.1]]), entite("B", [[6, 43], [6.1, 43.1]], nature="Chemin",
                                                              acces_pieton="Libre")],
             [entite("C", [[6, 43], [6.1, 43.1]], nature="Route à 1 chaussée", prive=True)]]
    vus = []

    def interroger(parametres):
        vus.append(parametres)
        return {"features": pages[parametres["STARTINDEX"] // 2]}

    troncons = bdtopo.lire_tuile(866, 120, interroger)
    assert [t["nature"] for t in troncons] == ["Sentier", "Chemin", "Route à 1 chaussée"]
    assert troncons[1]["acces_pieton"] == "Libre" and troncons[2]["prive"] is True
    assert [p["STARTINDEX"] for p in vus] == [0, 2] and vus[0]["SORTBY"] == "cleabs"
    assert vus[0]["BBOX"] == "43.3,6.0,43.35,6.05,urn:ogc:def:crs:EPSG::4326"


def test_trop_de_pages(monkeypatch):
    monkeypatch.setattr(bdtopo, "PAGE", 1)
    monkeypatch.setattr(bdtopo, "PAGES_MAX", 3)
    with pytest.raises(ErreurDonnees):
        bdtopo.lire_tuile(866, 120, lambda p: {"features": [entite(str(p["STARTINDEX"]), [[6, 43], [6.1, 43.1]])]})


def test_cache_de_trente_jours(tmp_path):
    appels, horloge = [], [1000.0]

    def interroger(parametres):
        appels.append(1)
        return {"features": [entite("A", [[6, 43], [6.1, 43.1]])]}

    options = dict(interroger=interroger, maintenant=lambda: horloge[0])
    assert len(bdtopo.charger_tuile(866, 120, tmp_path, **options)) == 1
    bdtopo.charger_tuile(866, 120, tmp_path, **options)
    assert len(appels) == 1
    horloge[0] += bdtopo.TTL_S + 1
    bdtopo.charger_tuile(866, 120, tmp_path, **options)
    assert len(appels) == 2
    with pytest.raises(ErreurDonnees):
        bdtopo.charger_tuile(866, 121, tmp_path, en_ligne=False)


def test_un_troncon_a_cheval_sur_deux_tuiles_n_est_rendu_qu_une_fois(tmp_path):
    commun = entite("A", [[6.04, 43.31], [6.06, 43.31]])
    propre = {"866_120": [commun], "866_121": [commun, entite("B", [[6.06, 43.31], [6.07, 43.32]])]}

    def interroger(parametres):
        sud, ouest = parametres["BBOX"].split(",")[:2]
        cle = "866_120" if ouest.startswith("6.0") and not ouest.startswith("6.05") else "866_121"
        return {"features": propre[cle]}

    troncons = bdtopo.troncons_zone(43.31, 6.04, 43.32, 6.06, tmp_path, interroger=interroger)
    assert sorted(t["id"] for t in troncons) == ["A-0", "B-0"]
    # Vue quittée : la lecture s'arrête avant la tuile suivante.
    restantes = iter([True, False])
    with pytest.raises(bdtopo.VueRemplacee):
        bdtopo.troncons_zone(43.31, 6.04, 43.32, 6.06, tmp_path / "autre", interroger=interroger,
                             continuer=lambda: next(restantes))


def test_reponse_inattendue(monkeypatch):
    def refuser(demande, timeout):
        raise urllib.error.URLError("hors ligne")

    monkeypatch.setattr(bdtopo.urllib.request, "urlopen", refuser)
    with pytest.raises(ErreurDonnees, match="BD TOPO indisponible"):
        bdtopo.interroger({"SERVICE": "WFS"})
