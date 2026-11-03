"""Un lot enrichi fabriqué en étapes sur plusieurs machines : calcul, K parts
de calques, fin. Le résultat doit être celui d'une fabrication d'un seul tenant.

E0_N45 prenait 4 h 14 d'une traite, dont près d'une heure et demie de calques :
répartis sur K machines, la plus longue tâche laisse de la marge sous les 6 h.
"""
import gzip
import json
import shutil
import sqlite3

import pytest

from hike2gpx import fabrication, lot

from test_fabrication import CHEMIN_IGN, ZONE, Compilation


@pytest.fixture
def compilation(monkeypatch):
    from hike2gpx import brouter, relief

    def compiler(inst, pbf, dossier, *, relief=None, tas="1g"):
        (dossier / "segments").mkdir(parents=True)
        (dossier / "segments" / "E5_N40.rd5").write_bytes(b"rd5 enrichie")
        return dossier / "segments"
    monkeypatch.setattr(brouter, "fabriquer_tuiles", compiler)
    monkeypatch.setattr(relief, "fabriquer", lambda inst, boite, dossier, cache, **o: dossier / "bef")


def fabriquer(tmp_path, sortie, etape="tout", part=None):
    return fabrication.fabriquer(tmp_path / "donnees", Compilation(), "E5_N40", sortie, zone=ZONE,
                                 fournisseurs=["ign"], troncons={"ign": lambda *b: [CHEMIN_IGN]},
                                 editions={"ign": "2026-09-15"}, etape=etape, part=part)


def contenu(dossier):
    with sqlite3.connect(dossier / "calques.mbtiles") as base:
        tuiles = sorted(base.execute("SELECT * FROM tiles"))
        metadonnees = dict(base.execute("SELECT name, value FROM metadata"))
    with gzip.open(dossier / "franchissements.json.gz", "rt", encoding="utf-8") as f:
        franchissements = json.load(f)
    manifeste = json.loads((dossier / "manifest.json").read_text(encoding="utf-8"))
    return {"tuiles": tuiles, "metadonnees": metadonnees, "franchissements": franchissements,
            "rd5": (dossier / "E5_N40.rd5").read_bytes(),
            "sources": manifeste["sources"], "fournisseurs": manifeste["fournisseurs"],
            "fichiers": sorted(f["nom"] for f in manifeste["fichiers"])}


def test_en_etapes_comme_d_un_seul_tenant(tmp_path, osm_installe, compilation):
    d_un_tenant = tmp_path / "tout"
    fabriquer(tmp_path, d_un_tenant)
    reparti, k = tmp_path / "reparti", 3
    assert fabriquer(tmp_path, reparti, "calcul") is None
    assert (reparti / fabrication.ETAT_CALCUL).is_file()
    for i in range(1, k + 1):
        # Chaque part sur sa machine : une copie du dossier, comme un artefact.
        machine = tmp_path / f"machine{i}"
        shutil.copytree(reparti, machine)
        assert fabriquer(tmp_path, machine, "calques", (i, k)) is None
        for nom in (fabrication.nom_part(i, k), fabrication.nom_part(i, k) + ".json"):
            shutil.copy(machine / nom, reparti / nom)
    assert fabriquer(tmp_path, reparti, "fin", (k, k)).name == "manifest.json"
    attendu, obtenu = contenu(d_un_tenant), contenu(reparti)
    assert obtenu["tuiles"] and obtenu == attendu
    # Rien des étapes ne part avec le lot.
    assert sorted(p.name for p in reparti.iterdir() if p.is_file()) == sorted(
        p.name for p in d_un_tenant.iterdir() if p.is_file())


def test_la_fin_refuse_des_calques_incomplets(tmp_path, osm_installe, compilation):
    reparti = tmp_path / "reparti"
    fabriquer(tmp_path, reparti, "calcul")
    fabriquer(tmp_path, reparti, "calques", (1, 2))
    with pytest.raises(fabrication.ErreurEtape, match=r"il manque calques\.2-2\.mbtiles"):
        fabriquer(tmp_path, reparti, "fin", (2, 2))
    assert not (reparti / "manifest.json").exists()


def test_les_calques_sans_calcul_disent_ce_qui_manque(tmp_path, osm_installe, compilation):
    with pytest.raises(fabrication.ErreurEtape, match="calcul"):
        fabriquer(tmp_path, tmp_path / "vide", "calques", (1, 2))


def test_assembler_reprend_tuiles_et_champs(tmp_path):
    import shapely
    boite = lot.boite_case("E5_N40")
    parts = []
    for k, (lon, lat) in enumerate(((6.015, 43.315), (6.315, 43.615))):
        chemin = tmp_path / f"p{k}.mbtiles"
        calques = lot.Calques(chemin, "p", boite, "")
        x10, y10 = lot.tuile_du_point(lot.ZOOM_BLOC, lon, lat)
        calques.ajouter_bloc(x10, y10, {"voies": [(shapely.LineString([(lon - 0.005, lat - 0.005),
                                                                        (lon + 0.005, lat + 0.005)]),
                                                     {"id": k, "genre" if k else "nature": "x"})]})
        calques.fermer()
        parts.append(chemin)
    total = lot.assembler_calques(parts, tmp_path / "tout.mbtiles", "tout", boite, "")
    with sqlite3.connect(tmp_path / "tout.mbtiles") as base:
        assert base.execute("SELECT COUNT(*) FROM tiles").fetchone()[0] == total > 1
        champs = json.loads(base.execute("SELECT value FROM metadata WHERE name='json'").fetchone()[0])
    assert champs["vector_layers"][0]["fields"] == {"id": "Number", "nature": "String", "genre": "String"}
