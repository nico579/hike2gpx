from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from hike2gpx import brouter

REFERENCE = Path(__file__).with_name("donnees") / "hiking-mountain-1.7.10.brf"


def test_profil_derive_de_hiking_mountain_par_deux_remplacements():
    source = REFERENCE.read_text(encoding="utf-8")
    profil = brouter.profil_hike2gpx(source)
    for avant, apres in brouter.REMPLACEMENTS:
        assert avant not in profil and profil.count(apres) == 1
    # Rien d'autre ne change : seules les deux lignes et l'en-tête diffèrent.
    differences = set(profil.splitlines()) ^ set(source.splitlines())
    assert {l for l in differences if not l.startswith("#")} == \
        {l for paire in brouter.REMPLACEMENTS for l in paire}


def test_profil_inattendu_refuse():
    with pytest.raises(ValueError):
        brouter.profil_hike2gpx("assign dummy 0\n")


@pytest.mark.parametrize("lat, lon, nom", [(43.3, 6.04, "E5_N40"), (45.0, 5.0, "E5_N45"),
                                           (48.8, 2.3, "E0_N45"), (43.6, -1.4, "W5_N40")])
def test_nom_segment(lat, lon, nom):
    assert brouter.nom_segment(lat, lon) == nom


def test_segments_zone():
    assert brouter.segments_zone(43.2, 5.9, 43.4, 6.1) == ["E5_N40"]
    assert brouter.segments_zone(44.9, 4.9, 45.1, 5.1) == ["E0_N40", "E5_N40", "E0_N45", "E5_N45"]


def test_requete_coupes_interdites_et_ponderees():
    franchissements = [
        {"statut": "blocked", "coupes": [[[6.1, 43.1], [6.2, 43.2]]]},
        {"statut": "uncertain", "coupes": [[[6.3, 43.3], [6.4, 43.4]], [[6.5, 43.5], [6.6, 43.6]]]},
    ]
    q = parse_qs(urlparse(brouter.requete([(43.0, 6.0), (43.5, 6.5)], franchissements)).query)
    assert q["lonlats"] == ["6.000000,43.000000|6.500000,43.500000"]
    assert q["profile"] == ["hike2gpx"] and q["format"] == ["geojson"]
    coupes = q["polylines"][0].split("|")
    assert coupes[0] == "6.1000000,43.1000000,6.2000000,43.2000000"
    assert coupes[1].endswith(f",{brouter.POIDS_A_VERIFIER}") and len(coupes) == 3
    strict = parse_qs(urlparse(brouter.requete([(43.0, 6.0), (43.5, 6.5)], franchissements, strict=True)).query)
    assert all(c.count(",") == 3 for c in strict["polylines"][0].split("|"))


def test_requete_sans_franchissement_sans_polylines():
    assert "polylines" not in brouter.requete([(43.0, 6.0), (43.5, 6.5)])
