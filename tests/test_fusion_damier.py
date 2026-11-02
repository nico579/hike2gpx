"""Fusion en damier : des mailles non voisines sur plusieurs processus.

La fusion d'une case dense (E0_N45) prenait 3 à 4 h 40 sur un cœur, et la
case dépassait la limite de 6 h d'une tâche GitHub Actions. Le damier ne doit
rien changer au réseau : ces tests comparent ce qu'il produit à la boucle
d'origine, maille par maille.
"""
import copy
import multiprocessing
import sys

import pytest

from hike2gpx import case, fabrication

from test_case import A, B, SENTIER, TRONCONS, fabriquer, troncon


def geometries(registre):
    """Le réseau ajouté vu par ses coordonnées : indépendant des identifiants,
    qui diffèrent d'un mode à l'autre."""
    position = lambda n: registre.noeuds.get(n, ("osm", n))
    voies = sorted(tuple(position(n) for n in ids) for ids, _ in registre.voies.values())
    raccords = sorted((wid, rang, registre.noeuds[n]) for wid, par_rang in registre.raccords.items()
                      for rang, positions in par_rang.items() for n in positions)
    return voies, raccords


def partages(registre):
    """Points où deux voies ajoutées partagent un même nœud."""
    vus, communs = {}, set()
    for wid, (ids, _) in registre.voies.items():
        for n in {ids[0], ids[-1]}:
            if n in vus and vus[n] != wid:
                communs.add(registre.noeuds.get(n, n))
            vus.setdefault(n, wid)
    return communs


def compteurs():
    return {"noeud": multiprocessing.Value("q", 1000), "voie": multiprocessing.Value("q", 1000)}


def isolee(registre, partages_, sud, ouest, troncons=TRONCONS, elements=(SENTIER,)):
    """La maille fusionnée sur une copie isolée, comme dans un processus fils :
    même registre de départ, compteurs d'identifiants partagés."""
    fils = copy.deepcopy(registre)
    fils.identifiants = case.IdentifiantsPartages(1000, partages_)
    fils.isoler()
    fils.fusionner(list(elements), troncons, sud, ouest)
    return fils.apport()


def test_apports_integres_donnent_le_reseau_de_la_boucle():
    attendu, _ = fabriquer()
    registre, partages_ = case.Registre(premier_noeud=1000, premiere_voie=1000), compteurs()
    registre.integrer(isolee(registre, partages_, *A))
    registre.integrer(isolee(registre, partages_, *B))
    assert geometries(registre) == geometries(attendu)
    assert partages(registre) == partages(attendu) == {(43.1, 6.0)}


def test_deux_mailles_d_une_phase_au_meme_bout_partagent_un_seul_noeud():
    # Un tronçon long de A qui finit au point même où commence un tronçon de
    # C, deux mailles plus loin : fusionnées en parallèle, chacune y crée un nœud.
    C = (43.0, 6.25)
    long_ = [troncon("a", (43.1, 5.95), (43.1, 6.3)), troncon("c", (43.1, 6.3), (43.1, 6.4))]
    registre, partages_ = case.Registre(premier_noeud=1000, premiere_voie=1000), compteurs()
    # Les deux partent du même registre, avant toute intégration : en parallèle.
    apports = [isolee(registre, partages_, *maille, troncons=long_, elements=()) for maille in (A, C)]
    for apport in apports:
        registre.integrer(apport)
    assert len(registre.voies) == 2
    assert partages(registre) == {(43.1, 6.3)}


def test_identifiants_partages_par_blocs():
    compteurs = {"noeud": multiprocessing.Value("q", 1000), "voie": multiprocessing.Value("q", 50)}
    un, deux = case.IdentifiantsPartages(1000, compteurs), case.IdentifiantsPartages(1000, compteurs)
    assert [un.noeud(), un.noeud(), deux.noeud(), un.voie()] == [1000, 1001, 1000 + case.IdentifiantsPartages.BLOC, 50]
    assert compteurs["noeud"].value == 1000 + 2 * case.IdentifiantsPartages.BLOC


def test_processus_un_seul_hors_linux_ou_avec_d_autres_fils(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert fabrication.processus_fusion() == 1
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(fabrication.threading, "active_count", lambda: 2)
    assert fabrication.processus_fusion() == 1


# Une grille de 3 × 3 mailles : une ligne et une colonne de tronçons qui
# franchissent toutes les limites et se croisent, et des chemins qui finissent
# près d'un sentier OSM dans trois mailles différentes.
GRILLE = (43.0, 5.75, 43.75, 6.5)
LIGNES = ([troncon(f"h{k}", (43.1, round(5.8 + 0.05 * k, 2)), (43.1, round(5.85 + 0.05 * k, 2)))
           for k in range(13)]
          + [troncon(f"v{k}", (round(43.05 + 0.05 * k, 2), 6.1), (round(43.1 + 0.05 * k, 2), 6.1))
             for k in range(13)]
          + [troncon(f"r{k}", (43.41, x), (43.40004, x)) for k, x in enumerate((5.9, 6.1, 6.3))])
SENTIER_GRILLE = {"type": "way", "id": 7, "nodes": [71, 72, 73, 74], "tags": {"highway": "path"},
                  "geometry": [{"lat": 43.4, "lon": x} for x in (5.8, 6.0, 6.2, 6.4)]}


def fusion_grille(processus, monkeypatch):
    monkeypatch.setattr(fabrication, "_elements_maille", lambda dossier, sud, ouest: [SENTIER_GRILLE])
    lire = lambda sud, ouest, nord, est: [t for t in LIGNES if sud <= t["pts"][0][0] < nord
                                          and ouest <= t["pts"][0][1] < est]
    registre = case.Registre(premier_noeud=1000, premiere_voie=1000)
    etapes = []
    fabrication._fusionner_mailles(None, registre, case.mailles(*GRILLE), lire, "ign",
                                   lambda etape, faites, total: etapes.append(etape), lambda: True,
                                   processus=processus)
    return registre, etapes


@pytest.mark.skipif(sys.platform != "linux", reason="le damier repose sur fork, Linux seulement")
def test_damier_donne_le_meme_reseau_que_la_boucle(monkeypatch):
    serie, _ = fusion_grille(1, monkeypatch)
    damier, etapes = fusion_grille(2, monkeypatch)
    assert etapes[0] == "fusion en damier (2 processus)"
    assert len(serie.voies) == len(LIGNES)
    assert geometries(damier) == geometries(serie)
    assert partages(damier) == partages(serie)
    # Chaque jointure garde un seul nœud : 12 sur la ligne, 12 sur la
    # colonne, leur croisement étant commun aux deux.
    assert len(partages(damier)) == 23
    assert len({n for ids, _ in damier.voies.values() for n in ids}) == len(
        {n for ids, _ in serie.voies.values() for n in ids})
