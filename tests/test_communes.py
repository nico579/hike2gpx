"""Recherche de villes via le service officiel de découpage administratif."""
import io
import json
from urllib.parse import parse_qs, urlparse

from hike2gpx import communes


def test_commune_recherchee_et_coordonnees_validees():
    def ouvrir(demande, timeout):
        assert urlparse(demande.full_url).netloc == "geo.api.gouv.fr"
        assert parse_qs(urlparse(demande.full_url).query)["nom"] == ["Grenoble"]
        assert timeout == 8
        return io.BytesIO(json.dumps([
            {"nom": "Grenoble", "centre": {"coordinates": [5.7155, 45.1842]},
             "departement": {"nom": "Isère"}},
            {"nom": "Invalide", "centre": {"coordinates": [500, 95]}},
        ]).encode())

    assert communes.chercher({"recherche": " Grenoble "}, ouvrir) == {
        "communes": [{"nom": "Grenoble", "departement": "Isère", "lat": 45.1842, "lon": 5.7155}]}


def test_commune_recherche_vide_ou_service_en_panne():
    assert "erreur" in communes.chercher({"recherche": "x"})

    def panne(_demande, timeout):
        raise TimeoutError()

    assert "erreur" in communes.chercher({"recherche": "Paris"}, panne)
