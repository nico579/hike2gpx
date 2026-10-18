"""Test d'intégration avec le vrai BRouter, sur un cas réel figé à Garéoult :
la clôture en béton (way 1558904264) que traverse le trottoir way 1552146409.
L'extrait OSM est dans donnees/gareoult_cloture.json (tools/extraire_cas.py).

Sauté sans Java, sans BRouter installé ou sans sa tuile E5_N40. Pour le
lancer : HIKE2GPX_HOME=D:\\hike2gpx, après « hike2gpx installer E5_N40 ».
Le profil, les coupes et le moteur sont ceux de la page ; seul l'extrait OSM
est figé, les données routières de BRouter suivent ses mises à jour.
"""
import json
from pathlib import Path

import pytest

from hike2gpx import application, brouter, franchissements
from hike2gpx.__main__ import DOSSIERS

CAS = Path(__file__).with_name("donnees") / "gareoult_cloture.json"
# Les deux bouts du trottoir, de part et d'autre de la clôture.
DEPART, ARRIVEE = (43.324163, 6.04207), (43.323743, 6.041067)
INSTALLATION = brouter.Installation(DOSSIERS.dossier_etat())


def _java() -> bool:
    try:
        brouter.java()
    except brouter.ErreurBRouter:
        return False
    return True


pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not (INSTALLATION.installee() and INSTALLATION.segment_present("E5_N40") and _java()),
                                 reason="BRouter, sa tuile E5_N40 ou Java absents (voir HIKE2GPX_HOME)")]


@pytest.fixture(scope="module")
def port():
    serveur = brouter.Serveur(INSTALLATION)
    serveur.demarrer()
    yield serveur.port
    serveur.arreter()


@pytest.fixture(scope="module")
def connus():
    return franchissements.analyser(json.loads(CAS.read_text(encoding="utf-8"))["elements"])


def bloquants_traverses(trace, connus):
    return [f for f in application.sur_le_trace(trace["geometry"]["coordinates"], connus) if f["statut"] == "blocked"]


def test_l_extrait_contient_la_cloture_bloquante(connus):
    assert any(f["osm"] == "way/1558904264" and f["statut"] == "blocked" for f in connus)


def test_le_profil_standard_traverse_la_cloture(port, connus):
    naif = brouter.calculer(port, [DEPART, ARRIVEE], profil="hiking-mountain")
    assert [f["osm"] for f in bloquants_traverses(naif, connus)] == ["way/1558904264"]


def test_hike2gpx_ne_traverse_aucune_coupe_bloquante(port, connus):
    # BRouter compile aussi le profil hike2gpx ici : une erreur de syntaxe
    # dans REMPLACEMENTS ferait échouer ce test.
    trace = brouter.calculer(port, [DEPART, ARRIVEE], connus)
    assert bloquants_traverses(trace, connus) == []


def test_le_mode_strict_ne_traverse_aucune_coupe(port, connus):
    try:
        trace = brouter.calculer(port, [DEPART, ARRIVEE], connus, strict=True)
    except brouter.ErreurBRouter:
        return      # aucun itinéraire : réponse admise en mode strict
    assert application.sur_le_trace(trace["geometry"]["coordinates"], connus) == []
