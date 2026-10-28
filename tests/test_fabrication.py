import gzip
import json
import sqlite3

import pytest

from hike2gpx import franchissements as fr, geofabrik, hors_ligne, lot, fabrication

ZONE = (43.30, 6.00, 43.35, 6.05)       # une seule tuile de 0,05° : 866, 120
TUILE = fr.tuile_du_point(43.32, 6.02)


class Installation:
    def __init__(self):
        self.demandes = []

    def telecharger_segment(self, nom, vers=None):
        self.demandes.append(nom)
        (vers / f"{nom}.rd5").write_bytes(b"rd5 officielle")
        return vers / f"{nom}.rd5"


@pytest.fixture
def mode_en_ligne(monkeypatch):
    """Le code du mode en ligne, simulé : une tuile couverte par un extrait installé."""
    lus = []
    monkeypatch.setattr(geofabrik, "extraits_de_tuile",
                        lambda dossier, i, j: [{"id": "paca", "date": "2026-10-25T21:21:21Z"}] if (i, j) == TUILE else [])
    monkeypatch.setattr(geofabrik, "regions", lambda dossier: [])
    monkeypatch.setattr(geofabrik, "regions_attendues", lambda dossier: [])
    monkeypatch.setattr(geofabrik, "installes", lambda dossier: [])

    def voies(sud, ouest, nord, est, dossier, **options):
        lus.append((sud, ouest))
        return {"voies": [{"id": 1, "genre": "sentier", "pts": [[43.31, 6.01], [43.32, 6.02]]}],
                "barrieres": [{"id": 2, "nature": "Clôture", "pts": [[43.315, 6.01], [43.315, 6.02]]}],
                "franchissements": []}
    monkeypatch.setattr(fr, "voies_affichables", voies)
    monkeypatch.setattr(fr, "franchissements_tuile", lambda i, j, dossier, **o: [
        {"cle": "a", "statut": "blocked", "raison": "r", "nature": "Clôture", "lat": 43.315, "lon": 6.015,
         "osm": "way/2", "voies": [1], "coupes": [[[6.015, 43.3149], [6.015, 43.3151]]]},
        {"cle": "b", "statut": "passable", "raison": "r", "nature": "Portillon", "lat": 43.316, "lon": 6.016,
         "osm": "node/3", "voies": [1], "coupes": []}])
    return lus


def test_fabrication_reprend_le_mode_en_ligne(tmp_path, mode_en_ligne):
    installation = Installation()
    manifeste = fabrication.fabriquer(tmp_path / "donnees", installation, "E5_N40", tmp_path / "lot", zone=ZONE)
    m = json.loads(manifeste.read_text(encoding="utf-8"))
    assert installation.demandes == ["E5_N40"], "la RD5 officielle de brouter.de, pas une compilation"
    assert m["type"] == "osm" and m["zone"] == list(ZONE) and m["sources"]["osm"] == "2026-10-25T21:21:21Z"
    assert {f["nom"] for f in m["fichiers"]} == {"E5_N40.rd5", "franchissements.json.gz", "calques.mbtiles"}
    assert len(mode_en_ligne) == 1, "seules les tuiles couvertes par un extrait sont lues"
    with gzip.open(tmp_path / "lot" / "franchissements.json.gz", "rt", encoding="utf-8") as f:
        assert {x["cle"] for x in json.load(f)} == {"a", "b"}, "tous, avec leurs coupes, comme pour le calcul"
    calque = lot.lire_calque(tmp_path / "lot" / "calques.mbtiles", "osm", *ZONE)
    assert {v["genre"] for v in calque["voies"]} == {"sentier"}
    assert [b["nature"] for b in calque["barrieres"]] and [f["cle"] for f in calque["franchissements"]] == ["a"]


def test_fabrication_installe_a_part_des_lots_enrichis(tmp_path, mode_en_ligne):
    fabrication.fabriquer(tmp_path / "donnees", Installation(), "E5_N40", tmp_path / "lot", zone=ZONE)
    h = hors_ligne.HorsLigne(tmp_path / "donnees")
    h.installer(tmp_path / "lot")
    assert (h.segments_osm / "E5_N40.rd5").is_file() and not (h.segments / "E5_N40.rd5").exists()
    assert h.lot_couvrant(ZONE)["type"] == "osm", "sa zone suffit pour le calcul"
    assert h.lot_couvrant((43.40, 6.01, 43.42, 6.03)) is None, "hors de la zone fabriquée"
    assert h.lot_du_calque((43.31, 6.01, 43.33, 6.03), "osm")["type"] == "osm"
    assert h.lot_du_calque((43.40, 6.01, 43.42, 6.03), "osm") is None, "hors de la zone fabriquée"


def test_fabrication_s_arrete_a_la_demande(tmp_path, mode_en_ligne):
    with pytest.raises(fabrication.Abandon):
        fabrication.fabriquer(tmp_path / "donnees", Installation(), "E5_N40", tmp_path / "lot", zone=ZONE,
                          continuer=lambda: False)


def attendre(a):
    a._fil_lot.join(10)
    return a.lot_en_cours()


def test_l_application_prepare_et_installe_le_lot(tmp_path, mode_en_ligne, monkeypatch):
    from hike2gpx import application as appli
    a = appli.Application(tmp_path / "donnees")
    monkeypatch.setattr(a, "installation", Installation())
    reponse = a.preparer_lot({"case": "E5_N40", "zone": list(ZONE)})
    assert reponse["lot_en_cours"]["actif"] in (True, False)
    etat = attendre(a)
    assert etat["etape"] == "fini" and not etat["actif"] and "erreur" not in etat
    assert [l["case"] for l in a.lots_hors_ligne()["lots"]] == ["E5_N40"]
    assert not list(a.hors_ligne.racine.glob(".fabrication-*")), "le dossier de travail est effacé"


@pytest.mark.parametrize("corps", [{}, {"case": "../E5_N40"}, {"case": "E5_N40", "zone": [1, 2]}])
def test_preparer_lot_refuse_une_demande_invalide(tmp_path, corps):
    from hike2gpx import application as appli
    assert "erreur" in appli.Application(tmp_path).preparer_lot(corps)


def test_un_seul_lot_a_la_fois_et_arret(tmp_path, mode_en_ligne, monkeypatch):
    import threading
    from hike2gpx import application as appli
    a = appli.Application(tmp_path / "donnees")
    monkeypatch.setattr(a, "installation", Installation())
    libre = threading.Event()
    original = fabrication.fabriquer

    def lent(*args, **options):
        libre.wait(5)
        return original(*args, **options)
    monkeypatch.setattr(fabrication, "fabriquer", lent)
    a.preparer_lot({"case": "E5_N40", "zone": list(ZONE)})
    assert a.preparer_lot({"case": "E5_N40"})["erreur"] == "Un lot se prépare déjà."
    a.arreter_lot()
    libre.set()
    etat = attendre(a)
    assert etat["erreur"] == "Fabrication arrêtée." and a.lots_hors_ligne()["lots"] == []


def test_un_arret_pendant_l_extrait_arrete_le_lot(tmp_path, monkeypatch):
    # Trouvé en essai réel : l'arrêt survenu pendant geofabrik.installer levait
    # geofabrik.Abandon, que l'application prenait pour une erreur sans message.
    region = {"id": "provence-alpes-cote-d-azur"}
    monkeypatch.setattr(fabrication, "regions_a_installer", lambda dossier, zone: [region])

    def installer(dossier, region, continuer=None):
        raise geofabrik.Abandon()
    monkeypatch.setattr(geofabrik, "installer", installer)
    with pytest.raises(fabrication.Abandon):
        fabrication.fabriquer(tmp_path / "donnees", Installation(), "E5_N40", tmp_path / "lot", zone=ZONE)


def test_un_arret_pendant_les_calques_libere_leur_fichier(tmp_path, mode_en_ligne):
    # Trouvé en essai réel sous Windows : la base des calques restait ouverte
    # après un arrêt, et l'essai suivant ne pouvait ni l'effacer ni la réécrire.
    appels = iter([True, False])
    with pytest.raises(fabrication.Abandon):
        fabrication.fabriquer(tmp_path / "donnees", Installation(), "E5_N40", tmp_path / "lot",
                          zone=(43.30, 5.95, 43.35, 6.40), continuer=lambda: next(appels, False))
    (tmp_path / "lot" / "calques.mbtiles").unlink()      # échouerait sous Windows si la base restait ouverte
    fabrication.fabriquer(tmp_path / "donnees", Installation(), "E5_N40", tmp_path / "lot", zone=ZONE)


def test_regions_a_installer_pour_les_tuiles_sans_extrait(tmp_path, monkeypatch):
    region = {"id": "provence-alpes-cote-d-azur", "bornes": (42.9, 4.2, 45.2, 7.8)}
    monkeypatch.setattr(geofabrik, "regions_attendues", lambda dossier: [region])
    monkeypatch.setattr(geofabrik, "installes", lambda dossier: [])
    monkeypatch.setattr(geofabrik, "extraits_de_tuile", lambda dossier, i, j: [])
    monkeypatch.setattr(geofabrik, "regions_de_tuile", lambda regions, i, j: [region])
    assert fabrication.regions_a_installer(tmp_path, ZONE) == [region]
    monkeypatch.setattr(geofabrik, "installes", lambda dossier: [region])
    assert fabrication.regions_a_installer(tmp_path, ZONE) == []


# ------------------------------------------------------------------ lot enrichi

SENTIER = {"type": "way", "id": 10, "nodes": [1, 2], "tags": {"highway": "path"},
           "geometry": [{"lat": 43.31, "lon": 6.01}, {"lat": 43.32, "lon": 6.02}]}
PORTAIL = {"type": "node", "id": 2, "lat": 43.32, "lon": 6.02, "tags": {"barrier": "gate"}}
CHEMIN_IGN = {"id": "T-0", "nature": "Chemin", "acces_pieton": None, "prive": False,
              "pts": [[43.32, 6.02], [43.33, 6.03]]}


def lire_pbf(chemin):
    import osmium
    noeuds, voies, relations = {}, {}, {}
    for o in osmium.FileProcessor(str(chemin)):
        if o.type_str() == "n":
            noeuds[o.id] = dict(o.tags)
        elif o.type_str() == "w":
            voies[o.id] = ([n.ref for n in o.nodes], dict(o.tags))
        else:
            relations[o.id] = [m.ref for m in o.members]
    return noeuds, voies, relations


def test_stock_osm_garde_les_tags_et_ecrit_le_pbf(tmp_path):
    from hike2gpx import case
    stock = case.StockOSM(tmp_path / "osm.sqlite")
    stock.ajouter([SENTIER])
    stock.ajouter([PORTAIL, SENTIER, {"type": "relation", "id": 7, "tags": {"route": "hiking"},
                                      "members": [{"type": "way", "ref": 10}, {"type": "way", "ref": 99}]}])
    stock.ajouter([{**PORTAIL, "tags": {}}])            # une autre tuile ne connaît que sa position
    assert stock.maxima() == (2, 10)
    stock.ecrire_pbf(tmp_path / "osm.pbf")
    stock.fermer()
    noeuds, voies, relations = lire_pbf(tmp_path / "osm.pbf")
    assert noeuds == {1: {}, 2: {"barrier": "gate"}}
    assert voies == {10: ([1, 2], {"highway": "path"})}
    assert relations == {7: [10]}, "seules les voies présentes restent membres"


@pytest.fixture
def osm_installe(monkeypatch, mode_en_ligne):
    """Un extrait installé partout ; seule la tuile des essais a un sentier."""
    monkeypatch.setattr(geofabrik, "extraits_de_tuile",
                        lambda dossier, i, j: [{"id": "paca", "date": "2026-10-25T21:21:21Z", "base": "x"}])
    monkeypatch.setattr(geofabrik, "elements_tuile",
                        lambda extrait, i, j: [PORTAIL, SENTIER] if (i, j) == TUILE else [])


class Compilation(Installation):
    def __init__(self):
        super().__init__()
        self.pbf = None

    def preparer_maison(self):
        pass


def test_lot_enrichi_fusionne_compile_et_montre_les_chemins_officiels(tmp_path, osm_installe, monkeypatch):
    from hike2gpx import brouter, relief
    installation = Compilation()
    reliefs, lus = [], []

    def compiler(inst, pbf, dossier, *, relief=None, tas="1g"):
        installation.pbf = lire_pbf(pbf)
        (dossier / "segments").mkdir(parents=True)
        (dossier / "segments" / "E5_N40.rd5").write_bytes(b"rd5 enrichie")
        return dossier / "segments"
    monkeypatch.setattr(brouter, "fabriquer_tuiles", compiler)
    monkeypatch.setattr(relief, "fabriquer", lambda inst, boite, dossier, cache, **o: reliefs.append(o["zone"])
                        or dossier / "bef")

    def troncons(sud, ouest, nord, est):
        lus.append((sud, ouest, nord, est))
        return [CHEMIN_IGN]
    m = json.loads(fabrication.fabriquer(tmp_path / "donnees", installation, "E5_N40", tmp_path / "lot", zone=ZONE,
                                         fournisseurs=["ign"], troncons={"ign": troncons},
                                         editions={"ign": "2026-09-15"}).read_text("utf-8"))
    assert installation.demandes == [], "pas de RD5 officielle : la RD5 est compilée"
    assert m["type"] == "enrichi" and m["fournisseurs"] == ["ign"] and m["emprise_enrichie"] == list(ZONE)
    assert m["sources"]["bdtopo"] == "2026-09-15" and m["sources"]["osm"] == "2026-10-25T21:21:21Z"
    assert reliefs == [ZONE], "le relief de la zone seule"
    assert (tmp_path / "lot" / "E5_N40.rd5").read_bytes() == b"rd5 enrichie"
    assert not (tmp_path / "lot" / "travail").exists(), "les intermédiaires sont effacés"
    noeuds, voies, _ = installation.pbf
    ajoutees = [tags for wid, (_, tags) in voies.items() if wid > 10]
    assert [t.get("hike2gpx") for t in ajoutees] == ["ign"], "le chemin IGN entre dans le PBF compilé"
    assert noeuds[2] == {"barrier": "gate"}
    calque = lot.lire_calque(tmp_path / "lot" / "calques.mbtiles", "bdtopo", *ZONE)
    assert {t["id"] for t in calque["troncons"]} == {"T-0"}, "un morceau par tuile traversée"
    with gzip.open(tmp_path / "lot" / "franchissements.json.gz", "rt", encoding="utf-8") as f:
        assert {x["cle"] for x in json.load(f)} == {"noeud-2"}, "le portail vu par la fusion, pas l'analyse en ligne"


def test_lot_enrichi_installe_et_lu_comme_les_autres(tmp_path, osm_installe, monkeypatch):
    from hike2gpx import brouter, relief

    def compiler(inst, pbf, dossier, **options):
        (dossier / "segments").mkdir(parents=True)
        (dossier / "segments" / "E5_N40.rd5").write_bytes(b"rd5 enrichie")
        return dossier / "segments"
    monkeypatch.setattr(brouter, "fabriquer_tuiles", compiler)
    monkeypatch.setattr(relief, "fabriquer", lambda *a, **o: tmp_path / "bef")
    fabrication.fabriquer(tmp_path / "donnees", Compilation(), "E5_N40", tmp_path / "lot", zone=ZONE,
                          fournisseurs=["ign"], troncons={"ign": lambda *bornes: [CHEMIN_IGN]})
    h = hors_ligne.HorsLigne(tmp_path / "donnees")
    h.installer(tmp_path / "lot")
    assert (h.segments / "E5_N40.rd5").is_file() and not (h.segments_osm / "E5_N40.rd5").exists()
    assert h.lot_couvrant((43.31, 6.01, 43.33, 6.03))["type"] == "enrichi"
    assert h.lot_du_calque((43.31, 6.01, 43.33, 6.03), "bdtopo")["case"] == "E5_N40"
    assert h.lot_du_calque((43.40, 6.01, 43.42, 6.03), "osm") is None, "le calque OSM s'arrête à la zone"


# Contours simplifiés : la France à l'ouest de 7°, la Suisse à l'est, la Pologne loin.
REGIONS = [{"id": "france", "polygones": [[[(-5, 41), (7, 41), (7, 51), (-5, 51), (-5, 41)]]]},
           {"id": "switzerland", "polygones": [[[(7, 45.8), (10.5, 45.8), (10.5, 47.8), (7, 47.8), (7, 45.8)]]]},
           {"id": "poland", "polygones": [[[(14, 49), (24, 49), (24, 55), (14, 55), (14, 49)]]]}]


def test_les_fournisseurs_d_une_zone_suivent_les_frontieres(tmp_path, monkeypatch):
    monkeypatch.setattr(geofabrik, "regions_attendues", lambda dossier: REGIONS)
    assert fabrication.fournisseurs_de_zone(tmp_path, ZONE) == ["ign"]
    assert fabrication.fournisseurs_de_zone(tmp_path, (46.0, 6.9, 46.1, 7.1)) == ["ign", "swisstlm3d"], \
        "une case frontalière prend les deux"
    assert fabrication.fournisseurs_de_zone(tmp_path, (53.0, 20.0, 53.1, 20.1)) == [], \
        "BDOT10k ne couvre que la Basse-Silésie"
    assert fabrication.fournisseurs_de_zone(tmp_path, (51.0, 16.0, 51.1, 16.1)) == ["bdot10k_ds"]


def test_preparer_lot_laisse_la_fabrication_choisir_les_fournisseurs(tmp_path, monkeypatch):
    from hike2gpx import application as appli
    a = appli.Application(tmp_path / "donnees")
    demandes = []
    monkeypatch.setattr(fabrication, "fabriquer", lambda *args, **options: demandes.append(options) or 1/0)
    a.preparer_lot({"case": "E5_N40", "zone": list(ZONE), "source": "ign"})
    a._fil_lot.join(5)
    assert "fournisseurs" not in demandes[0], "par défaut, ceux qui touchent la zone"


def test_case_frontaliere_fusionne_deux_fournisseurs(tmp_path, osm_installe, monkeypatch):
    from hike2gpx import brouter, relief
    installation = Compilation()

    def compiler(inst, pbf, dossier, **options):
        installation.pbf = lire_pbf(pbf)
        (dossier / "segments").mkdir(parents=True)
        (dossier / "segments" / "E5_N40.rd5").write_bytes(b"rd5")
        return dossier / "segments"
    monkeypatch.setattr(brouter, "fabriquer_tuiles", compiler)
    monkeypatch.setattr(relief, "fabriquer", lambda *a, **o: tmp_path / "bef")
    chemin_suisse = {"id": "CH-1", "nature": "Weg 15", "pts": [[43.33, 6.03], [43.34, 6.04]]}
    m = json.loads(fabrication.fabriquer(
        tmp_path / "donnees", installation, "E5_N40", tmp_path / "lot", zone=ZONE, fournisseurs=["ign", "swisstlm3d"],
        troncons={"ign": lambda *b: [CHEMIN_IGN], "swisstlm3d": lambda *b: [chemin_suisse]}).read_text("utf-8"))
    assert m["fournisseurs"] == ["ign", "swisstlm3d"] and {"bdtopo", "swisstlm3d"} <= set(m["sources"])
    _, voies, _ = installation.pbf
    assert sorted(tags.get("hike2gpx") for wid, (_, tags) in voies.items() if wid > 10) == ["ign", "swisstlm3d"]
    mbtiles = tmp_path / "lot" / "calques.mbtiles"
    assert {t["id"] for t in lot.lire_calque(mbtiles, "bdtopo", *ZONE)["troncons"]} == {"T-0"}
    assert {t["id"] for t in lot.lire_calque(mbtiles, "swisstlm3d", *ZONE)["troncons"]} == {"CH-1"}, \
        "une couche par fournisseur"


def test_relief_ne_rapatrie_que_la_zone(tmp_path, monkeypatch):
    from hike2gpx import relief
    voulues = relief.tuiles_zone(*ZONE)
    assert 4 <= len(voulues) <= 16, "une vue de 0,05° et sa marge"
    monkeypatch.setattr(relief.urllib.request, "urlopen", lambda *a, **o: pytest.fail("aucun téléchargement"))
    x, y = max(voulues)
    assert relief.tuile(tmp_path, x + 5, y, voulues) is None, "hors de la zone : sans donnée"
    assert relief.nom_bef(40, 5) == "srtm_38_04"


def test_relief_et_denivele_partagent_les_tuiles(tmp_path):
    # Nico, 2026-10-27 : les tuiles Mapterhorn ne changent pas et servent au lot
    # comme au dénivelé du parcours : un seul cache, celui de gpx2elev.
    from hike2gpx import relief
    from gpx2elev.providers import Repository
    assert Repository(tmp_path / "gpx2elev").reader.directory == relief.cache(tmp_path)
    assert relief._fichier(relief.cache(tmp_path), 2134, 1497).name == "mapterhorn_12_2134_1497.webp"


# ------------------------------------------------------------------ par lots (CLI)

@pytest.fixture
def serie(tmp_path, monkeypatch):
    """Fabrication simulée : un manifeste minimal, une erreur pour E0_N40.
    Rend l'extrait installé (sa date se change) et les cases fabriquées."""
    extrait = {"id": "paca", "date": "2026-10-20T20:23:47Z"}
    monkeypatch.setattr(geofabrik, "extraits_de_tuile", lambda dossier, i, j: [extrait])
    monkeypatch.setattr(geofabrik, "age_s", lambda e: 0)
    faites = []

    def fabriquer(dossier, installation, case, sortie, *, zone=None, fournisseurs=None, **options):
        if case == "E0_N40":
            raise RuntimeError("WFS indisponible")
        faites.append((case, zone))
        sortie.mkdir(parents=True)
        (sortie / "a.bin").write_bytes(b"x")
        return lot.ecrire_manifeste(sortie, case, [sortie / "a.bin"], {"osm": extrait["date"], "bdtopo": "2026-09-15"},
                                    type="enrichi", fournisseurs=fournisseurs)
    monkeypatch.setattr(fabrication, "fabriquer", fabriquer)
    monkeypatch.setattr(fabrication, "_tuiles", lambda zone: [(0, 0)])
    monkeypatch.setattr(fabrication, "fournisseurs_de_zone", lambda dossier, zone: ["ign"])
    return extrait, faites


def test_fabriquer_lots_reprend_et_isole_les_erreurs(tmp_path, serie):
    extrait, faites = serie
    lignes = []
    lots = lambda **o: fabrication.fabriquer_lots(tmp_path, Installation(), ["E5_N40", "E0_N40"], tmp_path / "lots",
                                                  fournisseurs=["ign"], editions={"ign": "2026-09-15"},
                                                  ecrire=lignes.append, **o)
    bilan = lots()
    assert bilan["E5_N40"] == "fabriqué" and bilan["E0_N40"] == "erreur : WFS indisponible"
    assert (tmp_path / "lots" / "E5_N40" / "manifest.json").is_file()
    assert sorted(p.name for p in (tmp_path / "lots").iterdir()) == ["E5_N40"], "aucun reste provisoire"
    assert lots()["E5_N40"] == "à jour" and len(faites) == 1
    assert lots(forcer=True)["E5_N40"] == "fabriqué"
    extrait["date"] = "2026-10-27T20:00:00Z"                    # un extrait renouvelé
    assert lots()["E5_N40"] == "fabriqué" and len(faites) == 3
    assert any("erreur" in l for l in lignes)


def test_fabriquer_lots_limite_les_cases_a_la_zone(tmp_path, serie):
    _, faites = serie
    bilan = fabrication.fabriquer_lots(tmp_path, Installation(), ["E5_N40", "W5_N45"], tmp_path / "lots",
                                       zone=(42.98, 5.65, 43.81, 6.94), ecrire=lambda t: None)
    assert bilan == {"E5_N40": "fabriqué", "W5_N45": "hors zone"}
    assert faites == [("E5_N40", (42.98, 5.65, 43.81, 6.94))]


def test_lot_a_jour_selon_le_type_et_l_edition(tmp_path):
    lot.ecrire_manifeste(tmp_path, "E5_N40", [], {"osm": "2026-10-20", "bdtopo": "2026-09-15"}, type="enrichi",
                         fournisseurs=["ign"])
    assert fabrication.lot_a_jour(tmp_path, osm="2026-10-20", fournisseurs=["ign"], editions={"ign": "2026-09-15"})
    assert not fabrication.lot_a_jour(tmp_path, osm="2026-10-20", fournisseurs=["ign"], editions={"ign": "2026-12-15"})
    assert not fabrication.lot_a_jour(tmp_path, osm="2026-10-20", fournisseurs=["ign", "swisstlm3d"]), \
        "un fournisseur de plus : le lot est à refaire"
    assert not fabrication.lot_a_jour(tmp_path, osm="2026-10-20"), "un lot OSM n'est pas un lot enrichi"
    assert not fabrication.lot_a_jour(tmp_path / "absent", osm="2026-10-20")


@pytest.mark.parametrize("arguments", [["bundles", "X5_N40", "--output", "lots"],
                                       ["bundles", "E5_N40", "--output", "lots", "--osm-only", "--provider", "ign"],
                                       ["bundles", "E5_N40", "--output", "lots", "--provider", "inconnue"],
                                       ["bundles", "E5_N40", "--output", "lots", "--gpkg", "a.gpkg",
                                        "--provider", "swisstlm3d"],
                                       ["bundles", "E5_N40"]])
def test_la_commande_bundles_refuse_les_options_invalides(arguments):
    from hike2gpx.__main__ import main
    with pytest.raises(SystemExit) as sortie:
        main(arguments)
    assert sortie.value.code == 2


def test_un_extrait_trop_gros_est_saute_pas_fatal(tmp_path, mode_en_ligne, monkeypatch):
    # Essai GitHub Actions du 2026-10-27 : les tuiles en mer de E5_N40 ne sont
    # contenues que par l'Europe (32,9 Go), et le lot entier échouait.
    europe = {"id": "europe", "bornes": (34.0, -25.0, 72.0, 45.0)}
    monkeypatch.setattr(fabrication, "regions_a_installer", lambda dossier, zone: [europe])

    def installer(dossier, region, continuer=None):
        raise geofabrik.ExtraitEcarte("extrait trop gros (32.9 Go), Overpass reste la source")
    monkeypatch.setattr(geofabrik, "installer", installer)
    manifeste = fabrication.fabriquer(tmp_path / "donnees", Installation(), "E5_N40", tmp_path / "lot", zone=ZONE)
    assert manifeste.is_file()


def test_la_fabrication_attend_l_index_des_regions(tmp_path, monkeypatch):
    # Sur une machine neuve, regions() rend [] le temps de bâtir l'index : la
    # page n'attend pas, une fabrication si (sinon aucun fournisseur trouvé).
    regions = [{**r, "bornes": [40.0, -5.0, 51.0, 7.0]} for r in REGIONS]
    index = geofabrik.Index("d'essai", "index-essai.json", lambda ouvrir: regions)
    assert [r["id"] for r in index.attendre(tmp_path)] == ["france", "switzerland", "poland"]


def test_les_calques_ne_lisent_que_la_tuile_demandee(tmp_path, mode_en_ligne, monkeypatch):
    # Essai GitHub Actions du 2026-10-27 : les bornes exactes d'une tuile
    # touchent ses voisines du nord et de l'est ; chaque tuile en lisait quatre,
    # et une voisine en mer, sans extrait, partait vers Overpass (HTTP 502).
    lues = []
    voies = fr.voies_affichables
    monkeypatch.setattr(fr, "voies_affichables",
                        lambda *bornes, **o: lues.append(fr.tuiles_zone(*bornes[:4])) or voies(*bornes, **o))
    fabrication.fabriquer(tmp_path / "donnees", Installation(), "E5_N40", tmp_path / "lot", zone=ZONE)
    assert lues == [[TUILE]]


def test_les_cases_d_un_fournisseur_suivent_son_pays(tmp_path, monkeypatch):
    monkeypatch.setattr(geofabrik, "regions_attendues", lambda dossier: REGIONS)
    assert fabrication.cases_des_fournisseurs(tmp_path, ["swisstlm3d"]) == ["E10_N45", "E5_N45"]
    assert fabrication.cases_des_fournisseurs(tmp_path, ["bdot10k_ds"]) == ["E10_N50", "E15_N50"], \
        "la Basse-Silésie seule, pas toute la Pologne"
    france = fabrication.cases_des_fournisseurs(tmp_path, ["ign"])
    assert "E5_N40" in france and "E10_N45" not in france
    assert set(fabrication.cases_des_fournisseurs(tmp_path)) >= set(france) | {"E10_N45"}


def test_la_commande_cells_et_bundles_bulk(tmp_path, monkeypatch, capsys):
    from hike2gpx import __main__, brouter
    monkeypatch.setenv("HIKE2GPX_HOME", str(tmp_path))
    monkeypatch.setattr(geofabrik, "regions_attendues", lambda dossier: REGIONS)
    assert __main__.main(["cells", "--provider", "swisstlm3d"]) == 0
    assert capsys.readouterr().out.split() == ["E10_N45", "E5_N45"]
    assert __main__.main(["cells", "--provider", "swisstlm3d", "--bulk-only"]) == 0
    assert capsys.readouterr().out.split() == [], "swissTLM3D n'a pas encore de lecture en bloc"
    demandes = {}
    monkeypatch.setattr(brouter.Installation, "installee", lambda self: True)
    monkeypatch.setattr(fabrication, "lecteurs_en_bloc", lambda dossier: ({"ign": "lecteur"}, {"ign": "édition"}))
    monkeypatch.setattr(fabrication, "fabriquer_lots", lambda *a, **o: demandes.update(o) or {"E5_N45": "fabriqué"})
    assert __main__.main(["bundles", "E5_N45", "--bulk", "--output", str(tmp_path / "lots")]) == 0
    assert demandes["fournisseurs"] == ["ign", "zabaged"] and demandes["troncons"] == {"ign": "lecteur"}
    assert "laissés de côté" in capsys.readouterr().out


def test_le_manifeste_ne_declare_que_les_fournisseurs_qui_ont_apporte(tmp_path, osm_installe, monkeypatch):
    # W5_N50 : le contour Geofabrik de la France déborde en mer au-dessus du
    # Cotentin ; la case, anglaise, ne doit pas se dire « IGN ».
    from hike2gpx import brouter, relief

    def compiler(inst, pbf, dossier, **options):
        (dossier / "segments").mkdir(parents=True)
        (dossier / "segments" / "E5_N40.rd5").write_bytes(b"rd5")
        return dossier / "segments"
    monkeypatch.setattr(brouter, "fabriquer_tuiles", compiler)
    monkeypatch.setattr(relief, "fabriquer", lambda *a, **o: tmp_path / "bef")
    m = json.loads(fabrication.fabriquer(
        tmp_path / "donnees", Compilation(), "E5_N40", tmp_path / "lot", zone=ZONE, fournisseurs=["ign", "swisstlm3d"],
        troncons={"ign": lambda *b: [CHEMIN_IGN], "swisstlm3d": lambda *b: []},
        editions={"ign": "2026-09-15", "swisstlm3d": "2026-03-01"}).read_text("utf-8"))
    assert m["fournisseurs"] == ["ign"] and m["fournisseurs_demandes"] == ["ign", "swisstlm3d"]
    assert "swisstlm3d" not in m["sources"] and "swissTLM3D" not in m["attribution"]
    a_jour = lambda **o: fabrication.lot_a_jour(tmp_path / "lot", osm="2026-10-25T21:21:21Z", **o)
    assert a_jour(fournisseurs=["ign", "swisstlm3d"], editions={"ign": "2026-09-15", "swisstlm3d": "2026-03-01"}), \
        "pas refait chaque semaine pour un fournisseur qui n'apporte rien"
    assert not a_jour(fournisseurs=["ign"]), "la demande a changé"


def test_le_relief_d_une_case_entiere_n_est_construit_qu_une_fois(tmp_path, osm_installe, monkeypatch):
    from hike2gpx import brouter, relief
    construits = []

    def construire(inst, boite, dossier, cache, **o):
        construits.append(o["zone"])
        (dossier / "bef").mkdir(parents=True)
        (dossier / "bef" / f"{relief.nom_bef(40, 5)}.bef").write_bytes(b"relief")
        return dossier / "bef"

    def compiler(inst, pbf, dossier, *, relief=None, tas="1g"):
        assert (relief / "srtm_38_04.bef").is_file()
        (dossier / "segments").mkdir(parents=True)
        (dossier / "segments" / "E5_N40.rd5").write_bytes(b"rd5")
        return dossier / "segments"
    monkeypatch.setattr(relief, "fabriquer", construire)
    monkeypatch.setattr(brouter, "fabriquer_tuiles", compiler)
    monkeypatch.setattr(fabrication, "_calques",
                        lambda dossier, case, boite, zone, sortie, *a, **o:
                        (sortie / "calques.mbtiles").write_bytes(b"calques") and ({}, set()))
    fabriquer = lambda sortie, **o: fabrication.fabriquer(tmp_path / "donnees", Compilation(), "E5_N40", sortie,
                                                          fournisseurs=["ign"], troncons={"ign": lambda *b: []}, **o)
    fabriquer(tmp_path / "vue", zone=ZONE)
    assert not relief.fichier_bef(tmp_path / "donnees", (40, 5, 45, 10)).exists(), "une vue garde son relief partiel"
    fabriquer(tmp_path / "case1")
    fabriquer(tmp_path / "case2")
    assert len(construits) == 2, "la vue, puis la case une seule fois"
    assert relief.fichier_bef(tmp_path / "donnees", (40, 5, 45, 10)).read_bytes() == b"relief"
    assert "brouter-" in relief.fichier_bef(tmp_path, (40, 5, 45, 10)).parent.name, "rangé par version de BRouter"

