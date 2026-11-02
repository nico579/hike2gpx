"""Extraits Geofabrik installés deux à la fois, archives BD TOPO pendant ce temps.

Le 2026-11-01, les 17 extraits d'E0_N45 avaient pris 1 h 44 un par un, puis
les archives BD TOPO se téléchargeaient encore à part : deux attentes de
réseau qui peuvent se recouvrir.
"""
import threading
import time

import pytest

from hike2gpx import fabrication, geofabrik

REGIONS = [{"id": f"r{k}"} for k in range(6)]


def installer_simule(en_cours, maximum, verrou, ecartee=None):
    def installer(dossier, region, continuer=None):
        with verrou:
            en_cours[0] += 1
            maximum[0] = max(maximum[0], en_cours[0])
        time.sleep(0.05)
        with verrou:
            en_cours[0] -= 1
        if region["id"] == ecartee:
            raise geofabrik.ExtraitEcarte("trop gros, Overpass seul")
        return {"id": region["id"]}
    return installer


def lancer(monkeypatch, preparation=None, ecartee=None):
    en_cours, maximum, verrou = [0], [0], threading.Lock()
    monkeypatch.setattr(geofabrik, "installer", installer_simule(en_cours, maximum, verrou, ecartee))
    etapes = []
    fabrication._installer_extraits(None, "E0_N45", REGIONS, lambda e, f, t: etapes.append((e, f, t)),
                                    lambda: True, preparation=preparation)
    return maximum[0], etapes


def test_deux_extraits_a_la_fois_au_plus_et_tous_installes(monkeypatch):
    maximum, etapes = lancer(monkeypatch)
    assert maximum == fabrication.EXTRAITS_EN_PARALLELE == 2
    assert etapes[0] == ("extraits", 0, 6) and etapes[-1] == ("extraits", 6, 6)


def test_les_archives_se_preparent_pendant_les_extraits(monkeypatch):
    fenetre = []

    def preparation():
        fenetre.append(time.monotonic())
        time.sleep(0.6)
        fenetre.append(time.monotonic())
    debut = time.monotonic()
    _, etapes = lancer(monkeypatch, preparation=preparation)
    duree = time.monotonic() - debut
    # Les extraits deux à deux (3 × 0,05 s) puis la préparation (0,6 s)
    # prendraient 0,75 s à la suite ; ensemble, la plus longue des deux.
    assert duree < 0.72, duree
    assert etapes[-1] == ("extraits", 6, 6)


def test_un_extrait_ecarte_ne_fait_pas_echouer_le_lot(monkeypatch):
    _, etapes = lancer(monkeypatch, ecartee="r2")
    assert etapes[-1] == ("extraits", 6, 6)


def test_une_archive_introuvable_fait_echouer_le_lot(monkeypatch):
    def preparation():
        raise RuntimeError("R11 : téléchargement impossible ou altéré.")
    with pytest.raises(RuntimeError, match="R11"):
        lancer(monkeypatch, preparation=preparation)


def test_aucun_fil_ne_survit_pour_laisser_le_damier_possible(monkeypatch):
    avant = threading.active_count()
    lancer(monkeypatch, preparation=lambda: time.sleep(0.05))
    assert threading.active_count() == avant
