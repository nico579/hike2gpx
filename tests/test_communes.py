"""Recherche de villes : les communes françaises par le service officiel de
découpage administratif, puis le reste du monde par Nominatim."""
import io
import json
from urllib.parse import parse_qs, urlparse

from hike2gpx import communes

MADRID = [
    {"name": "Madrid", "lat": "40.4167820", "lon": "-3.7035070",
     "address": {"city": "Madrid", "state": "Communauté de Madrid", "country": "Espagne"}},
    {"name": "Madrid", "lat": "41.8766526", "lon": "-93.8232813",
     "address": {"county": "Boone County", "state": "Iowa", "country": "États-Unis d'Amérique"}},
    {"name": "Hors carte", "lat": "95", "lon": "0", "address": {}},
]


def repondre(par_hote):
    """Un faux urlopen : la réponse selon l'hôte, et la liste des URL
    demandées."""
    demandes = []

    def ouvrir(demande, timeout):
        assert timeout == 8
        assert demande.get_header("User-agent").startswith("hike2gpx/")
        demandes.append(demande.full_url)
        reponse = par_hote[urlparse(demande.full_url).netloc]
        if isinstance(reponse, Exception):
            raise reponse
        return io.BytesIO(json.dumps(reponse).encode())
    return ouvrir, demandes


def test_commune_recherchee_et_coordonnees_validees():
    ouvrir, demandes = repondre({"geo.api.gouv.fr": [
        {"nom": "Grenoble", "centre": {"coordinates": [5.7155, 45.1842]},
         "departement": {"nom": "Isère"}},
        {"nom": "Invalide", "centre": {"coordinates": [500, 95]}},
    ]})
    assert communes.chercher({"recherche": " Grenoble "}, ouvrir) == {
        "communes": [{"nom": "Grenoble", "detail": "Isère", "lat": 45.1842, "lon": 5.7155}]}
    # Une commune française trouvée : Nominatim n'est pas sollicité.
    assert len(demandes) == 1
    assert parse_qs(urlparse(demandes[0]).query)["nom"] == ["Grenoble"]


def test_hors_de_france_le_reste_du_monde():
    ouvrir, demandes = repondre({"geo.api.gouv.fr": [], "nominatim.openstreetmap.org": MADRID})
    assert communes.chercher({"recherche": "madrid"}, ouvrir) == {"communes": [
        {"nom": "Madrid", "detail": "Communauté de Madrid, Espagne", "lat": 40.416782, "lon": -3.703507},
        {"nom": "Madrid", "detail": "Iowa, États-Unis d'Amérique", "lat": 41.8766526, "lon": -93.8232813},
    ]}
    parametres = parse_qs(urlparse(demandes[1]).query)
    assert parametres["q"] == ["madrid"] and parametres["featureType"] == ["settlement"]
    assert parametres["accept-language"] == ["fr,en"]


def test_service_francais_en_panne_le_monde_prend_le_relais():
    ouvrir, _ = repondre({"geo.api.gouv.fr": TimeoutError(), "nominatim.openstreetmap.org": MADRID})
    assert communes.chercher({"recherche": "Madrid"}, ouvrir)["communes"][0]["detail"].endswith("Espagne")


def test_commune_recherche_vide_ou_services_en_panne():
    assert "erreur" in communes.chercher({"recherche": "x"})
    ouvrir, _ = repondre({"geo.api.gouv.fr": TimeoutError(), "nominatim.openstreetmap.org": TimeoutError()})
    assert "erreur" in communes.chercher({"recherche": "Paris"}, ouvrir)
