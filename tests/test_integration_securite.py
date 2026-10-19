"""Coupes et profil face au vrai BRouter, sur des cas inventés près de
Garéoult : chaque cas est un tronçon direct de 200 m doublé d'un détour de
800 m, et l'on regarde lequel BRouter choisit (audit B09 et B10).

Sauté sans Java, sans BRouter installé ou sans les profils de création déjà
téléchargés dans HIKE2GPX_HOME, comme test_integration_maison.py ; ce test
ne touche pas au réseau.
"""
import math
import shutil

import pytest

from hike2gpx import brouter, franchissements as fr, fusion
from hike2gpx.__main__ import DOSSIERS

REELLE = brouter.Installation(DOSSIERS.dossier_etat())
LAT0, LON0 = 43.32, 6.02
KX = fr.M_PAR_DEGRE * math.cos(math.radians(LAT0))
ECART_M = 1000          # entre deux cas : aucun détour n'en rejoint un autre

# Étiquettes du tronçon direct de chaque cas.
CAS = {
    "libre": {"highway": "path"},
    "foot=no": {"highway": "path", "foot": "no"},
    "vélo poussé": {"highway": "path", "foot": "no", "bicycle": "dismount"},
    "privé, vélos admis": {"highway": "path", "foot": "private", "bicycle": "yes"},
    "trottoir": {"highway": "residential", "foot": "no", "sidewalk": "both"},
    "clôture puis chaîne": {"highway": "path"},
}


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


def cas_inventes() -> list:
    """Éléments au format Overpass : pour le cas « clôture puis chaîne », une
    clôture à 90 m et une chaîne à 110 m sur le même tronçon direct."""
    elements, positions, compteur = [], {}, iter(range(1000, 10 ** 6))

    def noeud(x, y, **tags):
        nid = next(compteur)
        positions[nid] = geo(x, y)
        if tags:
            elements.append({"type": "node", "id": nid, "lat": positions[nid][0], "lon": positions[nid][1],
                             "tags": tags})
        return nid

    def voie(nids, **tags):
        elements.append({"type": "way", "id": next(compteur), "nodes": nids, "tags": tags,
                         "geometry": [dict(zip(("lat", "lon"), positions[n])) for n in nids]})

    for k, (nom, tags) in enumerate(CAS.items()):
        y = k * ECART_M
        debut, fin = noeud(0, y), noeud(200, y)
        chaine = nom == "clôture puis chaîne"
        voie([debut, noeud(110, y, **({"barrier": "chain"} if chaine else {})), fin], **tags)
        voie([debut, noeud(0, y + 300), noeud(200, y + 300), fin], highway="path")
        if chaine:
            voie([noeud(90, y - 20), noeud(90, y + 20)], barrier="fence")
    return elements


@pytest.fixture(scope="module")
def moteur(tmp_path_factory):
    dossier = tmp_path_factory.mktemp("securite")
    inst = brouter.Installation(DOSSIERS.dossier_etat())
    inst.maison = dossier / "maison"
    inst.profils_maison, inst.creation = inst.maison / "profils", inst.maison / "creation"
    shutil.copytree(REELLE.creation, inst.creation)
    inst.preparer_maison()
    elements = cas_inventes()
    reseau = fusion.Reseau()
    reseau.ajouter_osm(elements)
    reseau.ecrire_pbf(dossier / "cas.osm.pbf")
    segments = brouter.fabriquer_tuiles(inst, dossier / "cas.osm.pbf", dossier / "tuiles")
    serveur = brouter.Serveur(inst, segments=segments, profils=inst.profils_maison)
    serveur.demarrer()
    yield serveur.port, fr.analyser(elements)
    serveur.arreter()


def longueur(port, nom, liste=(), **options) -> float:
    y = list(CAS).index(nom) * ECART_M
    trace = brouter.calculer(port, [geo(10, y), geo(190, y)], liste, **options)
    return float(trace["properties"]["track-length"])


def test_troncon_libre_pris_tout_droit(moteur):
    port, _ = moteur
    assert longueur(port, "libre") < 250


@pytest.mark.parametrize("nom", ["foot=no", "vélo poussé", "privé, vélos admis", "trottoir"])
def test_interdiction_pietonne_respectee_par_le_profil(moteur, nom):
    # Audit B09 : trottoir, vélo poussé ou vélo admis levaient foot=no|private.
    port, _ = moteur
    assert longueur(port, nom) > 600


def test_coupe_ponderee_ne_neutralise_pas_une_coupe_interdite(moteur):
    # Audit B10 : la clôture (bloquante) et la chaîne (à vérifier) coupent le
    # même segment BRouter, et analyser() rend la clôture en premier.
    port, liste = moteur
    assert [f["statut"] for f in liste] == ["blocked", "uncertain"]
    assert longueur(port, "clôture puis chaîne") < 250          # sans coupe : tout droit
    assert longueur(port, "clôture puis chaîne", liste) > 600
    assert longueur(port, "clôture puis chaîne", liste, strict=True) > 600
