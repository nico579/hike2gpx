import xml.etree.ElementTree as ET

from hike2gpx.providers import atkis


def _reponse(positions, identifiant="chemin-1"):
    contenu = (f'<wfs:member><dlm:AX_WEGPFADSTEIG gml:id="{identifiant}">'
               f'<gml:LineString><gml:posList>{positions}</gml:posList></gml:LineString>'
               '</dlm:AX_WEGPFADSTEIG></wfs:member>') if positions else ""
    return ET.fromstring('<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0" '
                         'xmlns:gml="http://www.opengis.net/gml/3.2" xmlns:dlm="urn:test">'
                         f'{contenu}</wfs:FeatureCollection>')


def test_thuringe_et_baviere_ont_le_bon_ordre_de_coordonnees(monkeypatch):
    monkeypatch.setattr(atkis.basemap_atkis, "lire_tuile", lambda bornes: [])
    sources = dict(atkis.SOURCES)
    for land, tuile, positions, attendu, bas_gauche in (
        ("TH", (1014, 205), "10.25 50.717 10.251 50.718", [[50.717, 10.25], [50.718, 10.251]], "10.25 50.7"),
        ("BY", (951, 205), "47.575 10.275 47.576 10.276", [[47.575, 10.275], [47.576, 10.276]], "47.55 10.25"),
    ):
        monkeypatch.setattr(atkis, "SOURCES", {land: sources[land]})
        filtres = []
        def interroger(source, parametres):
            filtres.append(parametres["FILTER"])
            return _reponse(positions if parametres["STARTINDEX"] == 0
                            and parametres["TYPENAMES"].lower().endswith("wegpfadsteig")
                            else None)
        troncons = atkis.lire_tuile(*tuile, interroger=interroger)
        assert len(troncons) == 1
        assert troncons[0]["land"] == land and troncons[0]["pts"] == attendu
        assert bas_gauche in filtres[0]


def test_cache_atkis_se_reutilise_hors_ligne(tmp_path, monkeypatch):
    appels = []
    def lire(i, j, interroger=None):
        appels.append((i, j))
        return [{"id": "TH:chemin-1", "land": "TH", "nature": "Wirtschaftsweg",
                 "pts": [[50.717, 10.25], [50.718, 10.251]]}]
    monkeypatch.setattr(atkis, "lire_tuile", lire)
    premier = atkis.charger_tuile(1014, 205, tmp_path)
    assert atkis.charger_tuile(1014, 205, tmp_path, en_ligne=False) == premier
    assert appels == [(1014, 205)]
