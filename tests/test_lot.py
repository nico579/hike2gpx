import gzip
import hashlib
import json
import math
import sqlite3

import mapbox_vector_tile
import pytest
import shapely

from hike2gpx import lot

# Une petite « case » pour les tests : son bord est passe par 6,0005°.
EMPRISE = (43.0, 5.99, 43.01, 6.0005)


def lire_tuiles(chemin):
    with sqlite3.connect(chemin) as base:
        meta = dict(base.execute("SELECT name, value FROM metadata"))
        tuiles = {(x, 2 ** z - 1 - r): mapbox_vector_tile.decode(gzip.decompress(d))
                  for z, x, r, d in base.execute("SELECT * FROM tiles")}
    return meta, tuiles


def test_tuiles_et_bornes_concordent():
    x, y = lot.tuile_du_point(14, 6.0, 43.0)
    o, s, e, n = lot.bornes_tuile(14, x, y)
    assert o <= 6.0 < e and s <= 43.0 < n
    assert lot.tuiles_emprise(14, s + 1e-6, o + 1e-6, n - 1e-6, e - 1e-6) == [(x, y)]
    assert len(lot.blocs(43.0, 5.0, 45.0, 10.0)) > 1


def test_calques_mbtiles_coupes_a_la_case(tmp_path):
    chemin = tmp_path / "calques.mbtiles"
    calques = lot.Calques(chemin, "E5_N40", EMPRISE, "© OpenStreetMap, IGN")
    # Un sentier qui sort de la case à l'est, une barrière dedans, une autre dehors.
    sentier = shapely.LineString([(5.995, 43.005), (6.003, 43.005)])
    couches = {"chemins_osm": [(sentier, {"highway": "path", "vide": None})],
               "barrieres": [(shapely.Point(5.996, 43.006), {"barrier": "gate"}),
                             (shapely.Point(6.002, 43.006), {"barrier": "gate"})]}
    total = sum(calques.ajouter_bloc(x, y, couches) for x, y in lot.blocs(*EMPRISE))
    calques.fermer()
    meta, tuiles = lire_tuiles(chemin)
    assert total == len(tuiles) > 0
    assert meta["format"] == "pbf" and meta["minzoom"] == meta["maxzoom"] == "14"
    couches_meta = {c["id"]: c for c in json.loads(meta["json"])["vector_layers"]}
    assert couches_meta["chemins_osm"]["fields"] == {"highway": "String"}, "valeur vide écartée"
    barrieres = [f for t in tuiles.values() for f in t.get("barrieres", {}).get("features", [])]
    assert len(barrieres) == 1, "la barrière hors de la case n'est pas livrée"
    # Le sentier s'arrête au bord de la case : aucune tuile au-delà de 6,0005°.
    for (x, y), tuile in tuiles.items():
        assert lot.bornes_tuile(14, x, y)[0] < EMPRISE[3]


def test_coordonnees_dans_la_tuile_y_vers_le_bas(tmp_path):
    chemin = tmp_path / "calques.mbtiles"
    x, y = lot.tuile_du_point(14, 5.995, 43.005)
    o, s, e, n = lot.bornes_tuile(14, x, y)
    # Au quart nord-ouest de la tuile, en Mercator : (1024, 1024) dans le repère MVT.
    mx0, my0 = lot.mercator(o, s)
    mx1, my1 = lot.mercator(e, n)
    lon = o + (e - o) / 4
    my = float(my1 - (my1 - my0) / 4)
    lat = math.degrees(2 * math.atan(math.exp(my / lot.RAYON)) - math.pi / 2)
    calques = lot.Calques(chemin, "essai", (s - 1, o - 1, n + 1, e + 1), "")
    calques.ajouter_bloc(*lot.tuile_du_point(10, lon, lat), {"points": [(shapely.Point(lon, lat), {"k": 1})]})
    calques.fermer()
    with sqlite3.connect(chemin) as base:
        (donnees,) = base.execute("SELECT tile_data FROM tiles").fetchone()
    tuile = mapbox_vector_tile.decode(gzip.decompress(donnees), default_options={"y_coord_down": True})
    (px, py), = [f["geometry"]["coordinates"] for f in tuile["points"]["features"]]
    assert px == pytest.approx(1024, abs=2) and py == pytest.approx(1024, abs=2)


def test_sources_lisent_l_index_osm_par_bloc(tmp_path):
    import numpy as np
    from hike2gpx import franchissements as fr, geofabrik
    base = tmp_path / "case.sqlite"
    with sqlite3.connect(base) as con:
        con.executescript(geofabrik.SCHEMA + geofabrik.INDEX_SQL)
        voies = {1: ({"highway": "path", "sac_scale": "hiking", "name": "x"}, [(43.30, 6.00), (43.31, 6.01)]),
                 2: ({"highway": "track", "tracktype": "grade3"}, [(43.30, 6.02), (43.30, 6.03)]),
                 3: ({"highway": "primary"}, [(43.30, 6.00), (43.32, 6.00)]),
                 4: ({"barrier": "fence"}, [(43.305, 6.01), (43.305, 6.02)]),
                 5: ({"barrier": "kerb"}, [(43.306, 6.01), (43.306, 6.02)]),
                 6: ({"highway": "motorway"}, [(43.31, 6.0), (43.31, 6.03)])}
        for ident, (tags, pts) in voies.items():
            points = (np.array(pts) * 1e7).round().astype("<i4").tobytes()
            con.execute("INSERT INTO voies VALUES (?, ?, ?, ?)", (ident, json.dumps(tags), b"", points))
            for i, j in {fr.tuile_du_point(*p) for p in pts}:
                con.execute("INSERT INTO tuiles VALUES (?, ?, ?)", (i, j, ident))
    franchissements_fusion = [
        {"cle": "a", "lat": 43.301, "lon": 6.025, "statut": "blocked", "nature": "Clôture", "raison": "r",
         "osm": "way/4", "coupes": []},
        {"cle": "b", "lat": 43.302, "lon": 6.025, "statut": "passable", "nature": "Portillon", "raison": "r"}]
    sources = lot.Sources(base, franchissements=franchissements_fusion)
    couches = sources.bloc(43.29, 5.99, 43.33, 6.04)
    # Les règles de la page (voies_affichables) : routes comprises, autoroute exclue.
    assert sorted(p["genre"] for _, p in couches["voies"]) == ["piste", "route", "sentier"]
    assert next(p for _, p in couches["voies"] if p["genre"] == "sentier") == {"id": 1, "genre": "sentier"}
    # Une clôture gêne le piéton, une bordure non.
    assert [p for _, p in couches["barrieres"]] == [{"id": 4, "nature": "Clôture"}]
    assert [p for _, p in couches["franchissements"]] == [
        {"cle": "a", "statut": "blocked", "raison": "r", "nature": "Clôture", "osm": "way/4"}]
    assert couches["troncons"] == []
    loin = sources.bloc(44.0, 7.0, 44.1, 7.1)
    assert not any(loin.values())
    sources.fermer()


def test_lire_calque_rend_le_format_de_la_page(tmp_path):
    chemin = tmp_path / "calques.mbtiles"
    case = (43.0, 5.0, 45.0, 10.0)
    calques = lot.Calques(chemin, "E5_N40", case, "")
    voie = shapely.LineString([(6.000, 43.300), (6.004, 43.302)])
    troncon = shapely.LineString([(6.001, 43.301), (6.003, 43.301)])
    franchi = shapely.Point(6.002, 43.3011)
    couches = {"voies": [(voie, {"id": 1, "genre": "sentier"})],
               "barrieres": [],
               "troncons": [(troncon, {"id": "T-0", "nature": "Chemin", "prive": True})],
               "franchissements": [(franchi, {"cle": "a", "statut": "blocked", "nature": "Clôture", "raison": "r"})]}
    for x, y in lot.blocs(43.29, 5.99, 43.31, 6.01):
        calques.ajouter_bloc(x, y, couches)
    calques.fermer()
    osm = lot.lire_calque(chemin, "osm", 43.299, 5.999, 43.303, 6.005)
    assert set(osm) == {"voies", "barrieres", "franchissements"}
    assert {v["genre"] for v in osm["voies"]} == {"sentier"} and osm["barrieres"] == []
    debut = min((p for v in osm["voies"] for p in v["pts"]), key=lambda p: p[1])
    assert debut[0] == pytest.approx(43.300, abs=1e-5) and debut[1] == pytest.approx(6.000, abs=1e-5)
    [f] = osm["franchissements"]
    assert f["cle"] == "a" and f["lat"] == pytest.approx(43.3011, abs=1e-5) and f["lon"] == pytest.approx(6.002, abs=1e-5)
    bdtopo = lot.lire_calque(chemin, "bdtopo", 43.299, 5.999, 43.303, 6.005)
    assert set(bdtopo) == {"troncons"} and bdtopo["troncons"][0]["nature"] == "Chemin"
    assert bdtopo["troncons"][0]["prive"] is True


def test_boite_case():
    assert lot.boite_case("E5_N40") == (40, 5, 45, 10)
    assert lot.boite_case("W5_N45") == (45, -5, 50, 0)


def test_manifeste_decrit_chaque_fichier(tmp_path):
    (tmp_path / "E5_N40.rd5").write_bytes(b"rd5")
    (tmp_path / "calques.mbtiles").write_bytes(b"tuiles")
    chemin = lot.ecrire_manifeste(tmp_path, "E5_N40", [tmp_path / "E5_N40.rd5", tmp_path / "calques.mbtiles"],
                                  {"osm": "2026-10-25T21:21:21Z"}, emprise_enrichie=[42.98, 5.65, 43.81, 6.94])
    m = json.loads(chemin.read_text(encoding="utf-8"))
    assert m["format"] == lot.FORMAT and m["case"] == "E5_N40" and m["sources"]["osm"].startswith("2026")
    assert m["emprise_enrichie"] == [42.98, 5.65, 43.81, 6.94]
    assert m["fichiers"] == [
        {"nom": "E5_N40.rd5", "octets": 3, "sha256": hashlib.sha256(b"rd5").hexdigest()},
        {"nom": "calques.mbtiles", "octets": 6, "sha256": hashlib.sha256(b"tuiles").hexdigest()}]
