"""Contrat des sources officielles et filtrage des voies réellement routables."""
import dataclasses

import pytest

from hike2gpx import application, providers
from hike2gpx.franchissements import ErreurDonnees

# Une source régionale, pour le mécanisme de borne : la BDOT10k bornée à la
# Basse-Silésie, comme elle l'était jusqu'au 2026-11-09.
BASSE_SILESIE = (50.0, 14.7, 51.85, 17.85)


def test_registre_separe_pays_calque_et_source():
    assert {p.pays for p in providers.SOURCES.values()} == {"fr", "de", "cz", "ch", "pl"}
    assert len({p.calque for p in providers.SOURCES.values()}) == len(providers.SOURCES)
    with pytest.raises(ValueError):
        providers.source("inconnue")
    assert providers.source("bdot10k_ds").disponible((52, 16, 52.1, 16.1)), "toute la Pologne"
    regional = dataclasses.replace(providers.source("bdot10k_ds"), borne=BASSE_SILESIE)
    assert regional.disponible((50.7, 15.5, 50.8, 15.6))
    assert not regional.disponible((52, 16, 52.1, 16.1))


def test_le_dossier_et_la_version_du_cache(tmp_path):
    appels = []
    module = providers.TuilesOfficielles("essai", lambda *zone: appels.append(zone) or [], avec_dossier=True,
                                         version=2)
    module.charger_tuile(1000, 300, tmp_path)
    assert appels[0][-1] == tmp_path, "le dossier des données en dernier"
    assert (tmp_path / "essai" / "v2_1000_300.json").is_file()


def test_la_page_ne_demande_que_les_powiats_de_sa_tuile(tmp_path, monkeypatch):
    from hike2gpx import bdot10k_powiaty
    demandes = []
    monkeypatch.setattr(bdot10k_powiaty, "powiats_de_zone", lambda *zone: demandes.append(zone) or [])
    assert providers.bdot10k.lire(52.0, 16.0, 52.05, 16.05, tmp_path) == []
    assert demandes == [(52.0, 16.0, 52.05, 16.05)], "la tuile, et non sa case de 5°"


def test_arcgis_garde_les_identifiants_et_filtre_les_objets(monkeypatch):
    vu = []
    def lire(url):
        vu.append(url)
        return {"features": [
            {"attributes": {"objectid": 7, "rodzaj": "ścieżka", "kategoriaistnienia": "eksploatowany"},
             "geometry": {"paths": [[[15.5, 50.7], [15.6, 50.8]]]}},
            {"attributes": {"objectid": 8, "rodzaj": "aleja", "kategoriaistnienia": "eksploatowany"},
             "geometry": {"paths": [[[15.5, 50.7], [15.6, 50.8]]]}},
        ]}
    monkeypatch.setattr(providers.core, "_json", lire)
    url = "https://geoportal.dolnyslask.pl/gisserver1/rest/services/BDOT10k/FeatureServer/18"
    [troncon] = providers.core._arcgis(((url, "ścieżka"),), (50.7, 15.5, 50.8, 15.6),
                                       lambda a: a.get("rodzaj") == "ścieżka")
    assert troncon["id"] == "18:7:0" and troncon["pts"] == [[50.7, 15.5], [50.8, 15.6]]
    assert "resultOffset=0" in vu[0] and "geometry=15.5%2C50.7%2C15.6%2C50.8" in vu[0]


def test_suisse_exclut_restrictions_et_autres_routes(monkeypatch):
    def lire(_url):
        if lire.appels:
            return {"results": []}
        lire.appels += 1
        return {"results": [
            {"id": 1, "properties": {"objektart": 16, "verkehrsbeschraenkung": 100},
             "geometry": {"type": "LineString", "coordinates": [[8.5, 46.2], [8.6, 46.3]]}},
            {"id": 2, "properties": {"objektart": 16, "verkehrsbeschraenkung": 2000},
             "geometry": {"type": "LineString", "coordinates": [[8.5, 46.2], [8.6, 46.3]]}},
            {"id": 3, "properties": {"objektart": 5, "verkehrsbeschraenkung": 100},
             "geometry": {"type": "LineString", "coordinates": [[8.5, 46.2], [8.6, 46.3]]}},
        ]}
    lire.appels = 0
    monkeypatch.setattr(providers.swisstlm3d, "_json", lire)
    [troncon] = providers.swisstlm3d.lire(46.2, 8.5, 46.3, 8.6)
    assert troncon["id"] == "1:0" and troncon["nature"] == "Weg 16"


def test_cache_de_tuiles_partage_calque_et_brouter(tmp_path):
    appels = []
    module = providers.TuilesOfficielles("essai", lambda *zone: appels.append(zone) or [
        {"id": "un", "pts": [[50, 15], [50.01, 15.01]], "nature": "sentier"}])
    assert module.charger_tuile(1000, 300, tmp_path)[0]["id"] == "un"
    assert module.charger_tuile(1000, 300, tmp_path, en_ligne=False)[0]["id"] == "un"
    assert len(appels) == 1
    with pytest.raises(ErreurDonnees):
        module.charger_tuile(1001, 300, tmp_path, en_ligne=False)


def test_calcul_refuse_la_source_regionale_hors_zone(tmp_path, monkeypatch):
    monkeypatch.setitem(providers.SOURCES, "bdot10k_ds",
                        dataclasses.replace(providers.SOURCES["bdot10k_ds"], borne=BASSE_SILESIE))
    resultat = application.Application(tmp_path).itineraire({
        "points": [[52.0, 16.0], [52.01, 16.01]], "source": "bdot10k_ds", "ign": True})
    assert resultat["code"] == "source_hors_zone"
