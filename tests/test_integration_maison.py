"""Tuiles maison de bout en bout, avec le vrai créateur de tuiles et le vrai
serveur BRouter, sur un petit réseau inventé près de Garéoult : deux sentiers
OSM parallèles, à 300 m l'un de l'autre, que relient seulement des chemins
IGN. À l'ouest, un chemin IGN libre ; à l'est, le cas B16 de l'audit : un
sentier OSM et un chemin IGN arrêtés de part et d'autre d'une clôture.

Sauté sans Java, sans BRouter installé ou sans les profils de création déjà
téléchargés (une première fabrication dans HIKE2GPX_HOME les apporte) : ce
test ne touche pas au réseau.
"""
import math
import shutil
import time

import pytest
from nico579_commons import atomique

from hike2gpx import application, atkis, bdtopo, brouter, franchissements as fr, maison
from hike2gpx.__main__ import DOSSIERS

REELLE = brouter.Installation(DOSSIERS.dossier_etat())
I, J = 866, 120
LAT0, LON0 = 43.32, 6.02
KX = fr.M_PAR_DEGRE * math.cos(math.radians(LAT0))


def _java() -> bool:
    try:
        brouter.java()
    except brouter.ErreurBRouter:
        return False
    return True


pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not (REELLE.installee() and any((REELLE.programme / "lib").glob("*.jar"))
                                      and all((REELLE.creation / nom).is_file() for nom in brouter.PROFILS_CREATION)
                                      and _java()),
                                 reason="BRouter, ses profils de création ou Java absents (voir HIKE2GPX_HOME)")]


def geo(x, y):
    return LAT0 + y / fr.M_PAR_DEGRE, LON0 + x / KX


def voie(wid, premier_noeud, *points, **tags):
    return {"type": "way", "id": wid, "nodes": list(range(premier_noeud, premier_noeud + len(points))),
            "geometry": [dict(zip(("lat", "lon"), geo(x, y))) for x, y in points], "tags": tags}


OSM = [voie(1, 10, (0, 0), (350, 0), (700, 0), highway="path"),          # sentier sud
       voie(2, 20, (0, 300), (350, 300), (700, 300), highway="path"),    # sentier nord
       voie(3, 30, (600, 300), (600, 150), highway="path"),              # descend du nord, s'arrête...
       voie(4, 40, (550, 150), (650, 150), barrier="fence")]             # ... sur cette clôture
IGN = [{"id": "OUEST-0", "nature": "Chemin", "acces_pieton": None, "pts": [list(geo(200, 0)), list(geo(200, 300))]},
       {"id": "EST-0", "nature": "Sentier", "acces_pieton": None, "pts": [list(geo(600, 0)), list(geo(600, 150))]}]


@pytest.fixture(scope="module", params=["ign", "atkis"])
def maison_essai(tmp_path_factory, request):
    source = request.param
    dossier = tmp_path_factory.mktemp("maison")
    inst = brouter.Installation(DOSSIERS.dossier_etat())
    inst.maison = dossier / "brouter-maison"
    inst.profils_maison, inst.creation = inst.maison / "profils", inst.maison / "creation"
    shutil.copytree(REELLE.creation, inst.creation)
    date = time.time()
    atomique.ecrire_json(dossier / "overpass" / f"v{fr.VERSION_DONNEES}_{I}_{J}.json",
                         {"version": fr.VERSION_DONNEES, "fetched_at": date, "bornes": fr.bornes_tuile(I, J),
                          "elements": OSM})
    if source == "ign":
        atomique.ecrire_json(dossier / "bdtopo" / f"v{bdtopo.VERSION_CACHE}_{I}_{J}.json",
                             {"version": bdtopo.VERSION_CACHE, "fetched_at": date, "troncons": IGN})
    else:
        chemins = [{**t, "id": f"TH:{t['id']}", "land": "TH", "nature": "Wirtschaftsweg"} for t in IGN]
        atomique.ecrire_json(dossier / "atkis" / f"v{atkis.VERSION_CACHE}_{I}_{J}.json",
                             {"version": atkis.VERSION_CACHE, "fetched_at": date, "troncons": chemins})
    segments, liste = maison.TuilesMaison(inst, dossier).preparer([(I, J)], en_ligne=False, source=source)
    serveur = brouter.Serveur(inst, segments=segments, profils=inst.profils_maison)
    serveur.demarrer()
    yield serveur.port, liste, source
    serveur.arreter()


def test_le_raccord_sur_la_cloture_est_bloquant(maison_essai):
    _, liste, _ = maison_essai
    assert [f["statut"] for f in liste] == ["blocked"]


def test_l_itineraire_emprunte_le_chemin_ign(maison_essai):
    port, liste, source = maison_essai
    trace = brouter.calculer(port, [geo(150, 0), geo(150, 300)], liste)
    [portion] = application.portions_ign(trace)
    assert portion["longueur_m"] == pytest.approx(300, abs=5)
    assert portion.get("source", "ign") == source


def test_le_raccord_sur_la_cloture_n_est_pas_franchi(maison_essai):
    port, liste, _ = maison_essai
    trace = brouter.calculer(port, [geo(600, 20), geo(600, 280)], liste)
    coords = trace["geometry"]["coordinates"]
    assert [f for f in application.sur_le_trace(coords, liste) if f["statut"] == "blocked"] == []
    # Le détour passe par le chemin IGN de l'ouest : 400 + 300 + 400 m environ.
    assert float(trace["properties"]["track-length"]) > 1000
    assert min(c[0] for c in coords) < geo(250, 0)[1]
