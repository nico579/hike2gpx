"""Les calques servis ne consultent que les mailles publiées."""
import pytest
from nico579_commons import atomique

from hike2gpx import cloud, mailles
from hike2gpx.application import Application
from hike2gpx.franchissements import ErreurDonnees


def test_calques_de_deux_mailles_et_absence_explicitement_signalee(tmp_path):
    crossing = {"cle": "portail", "statut": "blocked", "nature": "Portail",
                "lat": 43.30, "lon": 6.25, "coupes": []}
    for j in (24, 25):
        osm = {"voies": [{"id": 10, "genre": "chemin", "pts": [[43.3, 6.24], [43.3, 6.26]]}],
               "barrieres": []}
        officiel = [{"id": f"IGN-{j}", "nature": "Sentier",
                     "pts": [[43.3, 6.245 if j == 24 else 6.255],
                             [43.301, 6.246 if j == 24 else 6.256]]}]
        mailles.publier(tmp_path, "osm", 173, j, osm=osm, officiels=[],
                        franchissements=[crossing])
        mailles.publier(tmp_path, "ign", 173, j, osm={"voies": [], "barrieres": []},
                        officiels=officiel, franchissements=[crossing])
    zone = (43.30, 6.24, 43.31, 6.26)
    application = Application(tmp_path, mode_serveur=True)
    osm = application.calque_osm(zone)
    assert osm["bornes"] == (43.3, 6.2, 43.35, 6.3)
    assert len(osm["voies"]) == 1 and len(osm["franchissements"]) == 1
    officiel = application.calque_officiel("ign", zone)
    assert {t["id"] for t in officiel["troncons"]} == {"IGN-24", "IGN-25"}

    paquet = tmp_path / "paquets" / ("a" * 32)
    paquet.mkdir(parents=True)
    atomique.ecrire_json(paquet / "public.json", {"format": 2, "pret": True,
                          "source": "ign", "strict": True,
                          "mailles": [[173, 24], [173, 25]]})
    catalogue = application.mailles_disponibles()
    assert catalogue == {"pas": 0.25, "mailles": [
        {"maille": [173, j], "osm": True, "sources": ["ign"],
         "itineraires": [{"source": "ign", "strict": True}]} for j in (24, 25)]}

    with pytest.raises(ErreurDonnees):
        mailles.calque("osm", (43.30, 6.49, 43.31, 6.51), tmp_path, "osm")
    assert "absente" in application.calque_osm((43.30, 6.49, 43.31, 6.51))["erreur"]


def test_tunnel_local_http_sans_autoriser_http_distant():
    assert cloud.valider_adresse("http://127.0.0.1:8796/") == "http://127.0.0.1:8796"
    with pytest.raises(ValueError):
        cloud.valider_adresse("http://example.org:8796")
