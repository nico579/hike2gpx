"""Extraits Geofabrik : choix de la région, import par pyosmium, tuiles au
format d'Overpass, téléchargement vérifié, tâche de fond."""
import hashlib
import io
import json
import time

import numpy as np
import pytest

osmium = pytest.importorskip("osmium")

from hike2gpx import franchissements as fr, geofabrik  # noqa: E402
from test_franchissements import Carte  # noqa: E402

DATE = "2026-10-18T20:25:06Z"


def carre(sud, ouest, nord, est):
    return [[[(ouest, sud), (est, sud), (est, nord), (ouest, nord), (ouest, sud)]]]


def region(identifiant, sud, ouest, nord, est, polygones=None):
    return {"id": identifiant, "nom": identifiant.title(), "pbf": f"https://exemple/{identifiant}-latest.osm.pbf",
            "bornes": (sud, ouest, nord, est), "polygones": polygones or carre(sud, ouest, nord, est)}


REGION = region("essai", 43.0, 5.5, 43.6, 6.5)


def ecrire_pbf(chemin, carte, date=DATE, autres_voies=()):
    """La carte d'essai au format PBF, comme un extrait de Geofabrik : tous les
    nœuds positionnés, puis les voies, puis les relations, triés."""
    entete = osmium.io.Header()
    entete.set("osmosis_replication_timestamp", date)
    tags_noeuds = {e["id"]: e["tags"] for e in carte.elements if e["type"] == "node"}
    ecrivain = osmium.SimpleWriter(str(chemin), header=entete)
    for nid, (lat, lon) in sorted(carte.positions.items()):
        ecrivain.add_node(osmium.osm.mutable.Node(id=nid, location=osmium.osm.Location(lon, lat),
                                                  tags=tags_noeuds.get(nid, {}), version=1))
    voies = [e for e in carte.elements if e["type"] == "way"] + list(autres_voies)
    for e in sorted(voies, key=lambda e: e["id"]):
        ecrivain.add_way(osmium.osm.mutable.Way(id=e["id"], nodes=e["nodes"], tags=e["tags"], version=1))
    for e in sorted((e for e in carte.elements if e["type"] == "relation"), key=lambda e: e["id"]):
        ecrivain.add_relation(osmium.osm.mutable.Relation(
            id=e["id"], members=[("w", m["ref"], m["role"]) for m in e["members"]], tags=e["tags"], version=1))
    ecrivain.close()


def installer_carte(dossier, carte, **options):
    pbf = dossier / "essai.osm.pbf"
    ecrire_pbf(pbf, carte, **options)
    base = geofabrik.dossier_extraits(dossier) / "essai.sqlite"
    base.parent.mkdir(parents=True, exist_ok=True)
    return geofabrik.importer(pbf, base, REGION, DATE)


def carte_d_essai():
    carte = Carte()
    sentier = carte.chemin((-60, 30), (60, 30))
    cloture = carte.cloture((0, 0), (0, 60))
    portail = carte.noeud(30, 0, barrier="gate", access="private")
    carte.voie([carte.noeud(20, -10), portail, carte.noeud(40, 10)], highway="track")
    carte.chemin((-60, 80), (60, 80), highway="motorway")
    carte.itineraire(sentier)
    return carte, sentier, cloture


def elements_zone(dossier, extrait):
    vus = {}
    for i, j in fr.tuiles_zone(43.29, 5.99, 43.31, 6.01):
        for e in geofabrik.elements_tuile(extrait, i, j):
            vus[(e["type"], e["id"])] = e
    return list(vus.values())


def test_l_extrait_rend_ce_que_rendrait_overpass(tmp_path):
    carte, sentier, cloture = carte_d_essai()
    batiment = {"type": "way", "id": 999, "nodes": [carte.noeud(5, 5), carte.noeud(9, 9)], "tags": {"building": "yes"}}
    assert installer_carte(tmp_path, carte, autres_voies=[batiment])["voies"] == 3
    extrait = geofabrik.extrait_de_tuile(tmp_path, 866, 120)
    assert extrait["id"] == "essai" and extrait["date"] == DATE
    elements = elements_zone(tmp_path, extrait)
    types = {(e["type"], e["id"]) for e in elements}
    # Ni bâtiment, ni autoroute, ni nœud sans étiquette ; la relation du sentier balisé, oui.
    assert ("way", 999) not in types and ("way", sentier) in types and ("way", cloture) in types
    assert {e["id"] for e in elements if e["type"] == "node"} == {e["id"] for e in carte.elements
                                                                 if e["type"] == "node"}
    assert [e["tags"]["route"] for e in elements if e["type"] == "relation"] == ["hiking"]
    attendu = Carte.__new__(Carte)
    attendu.elements = [e for e in carte.elements if not (e["type"] == "way" and e["tags"].get("highway") == "motorway")]
    cle = lambda f: (round(f["lat"], 6), round(f["lon"], 6), f["statut"], f["nature"])
    assert sorted(map(cle, fr.analyser(elements))) == sorted(map(cle, fr.analyser(attendu.elements)))


def test_charger_tuile_prend_l_extrait_sans_overpass(tmp_path):
    carte, _, _ = carte_d_essai()
    installer_carte(tmp_path, carte)
    jamais = lambda *a, **o: pytest.fail("Overpass interrogé")
    tuile = fr.charger_tuile(866, 120, tmp_path, interroger=jamais)
    assert tuile["source"] == f"geofabrik:essai:{DATE}" and tuile["fetched_at"] == geofabrik.horodatage(
        {"date": DATE})
    # Hors connexion aussi, et l'analyse en cache reste valable d'un appel à l'autre.
    assert fr.charger_tuile(866, 120, tmp_path, en_ligne=False, interroger=jamais)["elements"] == tuile["elements"]
    premiere = fr.franchissements_tuile(866, 120, tmp_path, interroger=jamais)
    assert fr.franchissements_tuile(866, 120, tmp_path, interroger=jamais) == premiere
    # Une tuile hors de la région reste à Overpass.
    assert fr.charger_tuile(900, 120, tmp_path, interroger=lambda texte, **_: [])["elements"] == []


def test_la_plus_petite_region_qui_contient_toute_la_tuile():
    europe = region("europe", 35.0, -10.0, 60.0, 30.0)
    france = region("france", 42.0, -5.0, 51.0, 8.0)
    paca = region("paca", 43.0, 5.0, 45.0, 7.5)
    trouee = region("trouee", 40.0, 0.0, 46.0, 10.0,
                    polygones=[carre(40.0, 0.0, 46.0, 10.0)[0] + [carre(43.2, 5.9, 43.4, 6.1)[0][0][::-1]]])
    regions = [europe, france, paca]
    assert geofabrik.region_de_tuile(regions, 866, 120)["id"] == "paca"
    # Tuile à cheval sur le bord de la PACA : c'est la France qui la contient.
    assert geofabrik.region_de_tuile(regions, 899, 120)["id"] == "france"
    assert geofabrik.region_de_tuile(regions, 1060, 120)["id"] == "europe"      # 53° N : au-delà de la France
    assert geofabrik.region_de_tuile(regions, 2000, 120) is None
    # Une tuile dans le trou d'un contour n'y est pas.
    assert not geofabrik.contient_tuile(trouee, 866, 120) and geofabrik.contient_tuile(trouee, 820, 120)


def test_tuiles_par_lots_comme_ligne_par_ligne():
    # Le calcul groupé de l'import rend exactement les tuiles du calcul exact,
    # voie par voie, sur des lignes au hasard autour de grille.
    import random
    tirage = random.Random(19)
    voies = [[(43.3 + tirage.uniform(-0.12, 0.12), 6.0 + tirage.uniform(-0.12, 0.12))
              for _ in range(tirage.randint(2, 6))] for _ in range(300)]
    attendu = {(i, j, v) for v, ligne in enumerate(voies) for i, j in geofabrik.tuiles_ligne(ligne)}
    points = [p for ligne in voies for p in ligne]
    obtenu = geofabrik.tuiles_des_voies(np.arange(len(voies)), np.array([len(ligne) for ligne in voies]),
                                        np.array([p[0] for p in points]), np.array([p[1] for p in points]))
    assert {tuple(ligne) for ligne in obtenu.tolist()} == attendu


def test_une_ligne_compte_dans_chaque_tuile_qu_elle_traverse():
    # De la tuile (866, 119) à la (867, 120), en frôlant le coin de la (867, 119).
    cases = geofabrik.tuiles_ligne([(43.349, 5.999), (43.351, 6.0005)])
    assert cases == {(866, 119), (867, 119), (867, 120)}
    assert geofabrik.tuiles_ligne([(43.31, 6.01), (43.32, 6.02)]) == {(866, 120)}


class Reponse(io.BytesIO):
    def __init__(self, donnees, entetes=None):
        super().__init__(donnees)
        self.headers = entetes or {}


def faux_geofabrik(fichiers):
    def ouvrir(demande, timeout):
        contenu = fichiers[demande.full_url]
        return Reponse(contenu, {"Content-Length": str(len(contenu))})
    return ouvrir


def test_telechargement_verifie_par_le_md5(tmp_path):
    contenu = b"PBF"
    md5 = hashlib.md5(contenu).hexdigest()
    url = "https://exemple/essai-latest.osm.pbf"
    cible = tmp_path / "essai.osm.pbf"
    with pytest.raises(geofabrik.ErreurExtrait, match="MD5"):
        geofabrik._telecharger(url, cible, ouvrir=faux_geofabrik({url: contenu, url + ".md5": b"0" * 32 + b"  x"}))
    assert not list(tmp_path.iterdir())
    vu = []
    geofabrik._telecharger(url, cible, suivi=vu.append,
                           ouvrir=faux_geofabrik({url: contenu, url + ".md5": f"{md5}  essai".encode()}))
    assert cible.read_bytes() == contenu and vu == [1.0]


def test_installation_en_tache_de_fond_puis_renouvellement(tmp_path, monkeypatch):
    carte, _, _ = carte_d_essai()
    pbf = tmp_path / "source.osm.pbf"
    ecrire_pbf(pbf, carte)
    contenu = pbf.read_bytes()
    fichiers = {REGION["pbf"]: contenu, REGION["pbf"] + ".md5": hashlib.md5(contenu).hexdigest().encode()}
    monkeypatch.setattr(geofabrik.urllib.request, "urlopen", faux_geofabrik(fichiers))
    taches = geofabrik.Telechargements(tmp_path / "donnees")
    assert taches.lancer(REGION)
    taches._fil.join(30)
    assert taches.etat()["etape"] == "fini" and taches.etat()["date"] == DATE
    extrait = geofabrik.extrait_de_tuile(tmp_path / "donnees", 866, 120)
    assert extrait["date"] == DATE and not list(geofabrik.dossier_extraits(tmp_path / "donnees").glob("*.pbf"))
    # L'import a tourné dans un processus à part : rien ne reste de son index.
    assert not list(geofabrik.dossier_extraits(tmp_path / "donnees").glob("*.noeuds"))
    # Plus vieil que RENOUVELLEMENT_S, l'extrait part se renouveler ; l'ancien sert.
    lances = []
    monkeypatch.setattr(taches, "lancer", lances.append)
    taches.renouveler_si_perime(extrait)
    vieux = {**extrait, "date": "2026-09-01T00:00:00Z"}
    taches.renouveler_si_perime(vieux)
    assert lances == [vieux]


def test_index_des_regions_garde_un_mois(tmp_path):
    index = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"id": "essai", "name": "Essai", "urls": {"pbf": REGION["pbf"]}},
         "geometry": {"type": "Polygon", "coordinates": [[[5.5, 43.0], [6.5, 43.0], [6.5, 43.6], [5.5, 43.6],
                                                          [5.5, 43.0]]]}},
        {"type": "Feature", "properties": {"id": "sans-pbf", "urls": {}}, "geometry": None}]}
    appels = []

    def ouvrir(demande, timeout):
        appels.append(demande.full_url)
        return Reponse(json.dumps(index).encode())

    regions = geofabrik.regions(tmp_path, ouvrir=ouvrir)
    assert [r["id"] for r in regions] == ["essai"] and regions[0]["bornes"] == (43.0, 5.5, 43.6, 6.5)
    assert geofabrik.regions(tmp_path, ouvrir=ouvrir) == regions and len(appels) == 1
    plus_tard = time.time() + geofabrik.INDEX_TTL_S + 1
    geofabrik.regions(tmp_path, ouvrir=ouvrir, maintenant=lambda: plus_tard)
    assert len(appels) == 2
