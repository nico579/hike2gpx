"""Dénivelé par le vrai moteur de gpx2elev, avec un terrain simulé : le
lecteur des modèles d'altitude est remplacé, le protocole (5 m, gaussienne
de 20 m, hystérésis de 2 m) et le cache de profils sont les vrais."""
import math

import numpy as np
import pytest

from gpx2elev import core
from hike2gpx import denivele

LAT0, LON0 = 43.3, 6.0
KX = 111195.08 * math.cos(math.radians(LAT0))


def trace_est_ouest(longueur_m=1000.0, pas_m=50.0):
    return [[LON0 + d / KX, LAT0, 0.0] for d in np.arange(0, longueur_m + pas_m / 2, pas_m)]


class Rampe:
    """Altitude de 100 m au départ, puis 10 % de pente vers l'est."""

    def __init__(self):
        self.lectures = 0

    def read(self, source, coordinates, progress):
        self.lectures += 1
        return 100.0 + 0.1 * (np.asarray(coordinates)[:, 1] - LON0) * KX


class Panne:
    def read(self, source, coordinates, progress):
        raise ValueError(f"{source.label} : hors couverture")


def test_gpx_relu_par_gpx2elev():
    coordonnees = trace_est_ouest()
    piste = core.parse_gpx(denivele.gpx(coordonnees))
    assert piste.point_count == len(coordonnees)


def test_rampe_de_dix_pour_cent_sur_un_kilometre(tmp_path):
    lecteur = Rampe()
    r = denivele.calculer(trace_est_ouest(), tmp_path, lecteur=lecteur)
    assert r["montee_m"] == pytest.approx(100, abs=2) and r["descente_m"] <= 1
    assert (r["altitude_min_m"], r["altitude_max_m"]) == (100, 200)
    assert r["modele"] == "IGN LiDAR HD" and r["protocole"] == core.PROTOCOL
    assert r["depuis_le_cache"] is False
    assert r["profil"][0] == pytest.approx([0, 100], abs=0.2)
    assert r["profil"][-1] == pytest.approx([1000, 200], abs=1)
    # Le même tracé ne relit pas le terrain : le profil vient du cache de gpx2elev.
    assert denivele.calculer(trace_est_ouest(), tmp_path, lecteur=lecteur)["depuis_le_cache"] is True
    assert lecteur.lectures == 1


def test_profil_reduit_garde_les_extremites(tmp_path):
    r = denivele.calculer(trace_est_ouest(5000), tmp_path, lecteur=Rampe())
    assert 2 < len(r["profil"]) <= denivele.PROFIL_MAX_POINTS
    assert r["profil"][0][0] == 0
    assert r["profil"][-1][0] == pytest.approx(5000, abs=1)


def test_aucun_modele_disponible(tmp_path):
    with pytest.raises(denivele.ErreurDenivele):
        denivele.calculer(trace_est_ouest(), tmp_path, lecteur=Panne())


@pytest.mark.parametrize("coordonnees", [None, [], [[6.0, 43.3]], [[6.0, 43.3], ["x", 43.3]],
                                         [[6.0, 43.3], [6.0, 95.0]], [[6.0, 43.3], [6.0, float("nan")]]])
def test_trace_invalide(coordonnees):
    with pytest.raises(ValueError):
        denivele.valider(coordonnees)
