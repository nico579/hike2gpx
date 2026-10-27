import osmium
import pytest

from hike2gpx import case

# Deux mailles voisines : A = [43,0 ; 5,75 ; 43,25 ; 6,0], B = [43,0 ; 6,0 ; 43,25 ; 6,25].
A, B = (43.0, 5.75), (43.0, 6.0)
# Un sentier OSM qui traverse la limite : trois nœuds, deux segments.
SENTIER = {"type": "way", "id": 1, "nodes": [1, 2, 3], "tags": {"highway": "path"},
           "geometry": [{"lat": 43.2, "lon": 5.9}, {"lat": 43.2, "lon": 6.0}, {"lat": 43.2, "lon": 6.1}]}


def troncon(ident, *pts):
    return {"id": ident, "nature": "Sentier", "acces_pieton": None, "pts": [list(p) for p in pts]}


TRONCONS = [
    # Deux tronçons qui se touchent sur la limite, l'un à A, l'autre à B.
    troncon("t1", (43.1, 5.95), (43.1, 6.0)),
    troncon("t2", (43.1, 6.0), (43.1, 6.05)),
    # Deux chemins qui finissent à 4 m du sentier, l'un sur chaque segment.
    troncon("t3", (43.21, 5.95), (43.20004, 5.95)),
    troncon("t4", (43.21, 6.05), (43.20004, 6.05)),
]


def fabriquer():
    registre = case.Registre(premier_noeud=1000, premiere_voie=1000)
    comptes = [registre.fusionner([SENTIER], TRONCONS, *A), registre.fusionner([SENTIER], TRONCONS, *B)]
    return registre, comptes


def test_mailles_du_var():
    # 42,98 à 43,81 : rangées 42,75 à 43,75 ; 5,65 à 6,94 : colonnes 5,5 à 6,75.
    assert len(case.mailles(42.98, 5.65, 43.81, 6.94)) == 5 * 6
    assert case.mailles(43.0, 6.0, 43.25, 6.25) == [(43.0, 6.0)]


def test_chaque_troncon_ajoute_une_fois_par_la_maille_de_son_premier_point():
    registre, comptes = fabriquer()
    assert [c["troncons"] for c in comptes] == [2, 2]
    assert len(registre.voies) == 4
    assert all(wid >= 1000 for wid in registre.voies) and all(n >= 1000 for n in registre.noeuds)


def test_les_troncons_qui_se_touchent_a_la_limite_gardent_le_meme_noeud():
    registre, _ = fabriquer()
    t1 = next(ids for ids, _ in registre.voies.values() if registre.noeuds[ids[0]] == (43.1, 5.95))
    t2 = next(ids for ids, _ in registre.voies.values() if registre.noeuds[ids[-1]] == (43.1, 6.05))
    assert t1[-1] == t2[0]


def test_raccords_de_deux_mailles_reunis_sur_la_meme_voie_osm():
    registre, comptes = fabriquer()
    assert sum(c["raccords"] for c in comptes) == 2
    assert set(registre.raccords[1]) == {0, 1}
    corriges = registre.noeuds_corriges(1, [1, 2, 3])
    assert len(corriges) == 5 and corriges[0::2] == [1, 2, 3]
    # Chaque chemin finit sur le nœud inséré dans le sentier, pas sur un nœud isolé.
    fins = {ids[-1] for ids, _ in registre.voies.values()} | {ids[0] for ids, _ in registre.voies.values()}
    assert corriges[1] in fins and corriges[3] in fins


def test_pbf_de_la_case_corrige_osm_et_ajoute_les_chemins(tmp_path):
    source, sortie = tmp_path / "case.osm.pbf", tmp_path / "enrichie.osm.pbf"
    with osmium.SimpleWriter(str(source)) as w:
        for g in SENTIER["geometry"]:
            nid = SENTIER["nodes"][SENTIER["geometry"].index(g)]
            w.add_node(osmium.osm.mutable.Node(id=nid, location=osmium.osm.Location(g["lon"], g["lat"]), version=1))
        w.add_way(osmium.osm.mutable.Way(id=1, nodes=SENTIER["nodes"], tags=SENTIER["tags"], version=1))
        w.add_relation(osmium.osm.mutable.Relation(id=5, members=[("w", 1, "")], tags={"route": "hiking"}, version=1))
    registre, _ = fabriquer()
    registre.ecrire_pbf(source, sortie)
    objets = [(o.type_str(), o.id, [n.ref for n in o.nodes] if o.type_str() == "w" else None)
              for o in osmium.FileProcessor(str(sortie))]
    genres = [g for g, _, _ in objets]
    assert genres == sorted(genres, key="nwr".index), "nœuds, puis voies, puis relations"
    for g in "nwr":
        ids = [i for genre, i, _ in objets if genre == g]
        assert ids == sorted(ids)
    assert next(n for g, i, n in objets if g == "w" and i == 1) == registre.noeuds_corriges(1, [1, 2, 3])
    assert sum(1 for g, i, _ in objets if g == "w" and i >= 1000) == 4
    noeuds = {i for g, i, _ in objets if g == "n"}
    assert all(n in noeuds for g, _, ns in objets if g == "w" for n in ns), "aucune voie ne pointe dans le vide"


def test_bouts_coupes_par_basemap_recolles_d_une_maille_a_l_autre():
    # ATKIS par basemap.de : un chemin coupé au bord d'une tuile vectorielle
    # revient en deux morceaux dont les bouts, à 0,5 m l'un de l'autre, ne
    # coïncident pas. Ici la coupure tombe sur la limite de deux mailles.
    gauche = {"id": "g", "nature": "Weg/Pfad/Steig", "land": "BW", "bords": [False, True],
              "pts": [[43.1, 5.95], [43.1, 5.9999970]]}
    droite = {"id": "d", "nature": "Weg/Pfad/Steig", "land": "BW", "bords": [True, False],
              "pts": [[43.1, 6.0000030], [43.1, 6.05]]}
    registre = case.Registre(1000, 1000)
    registre.fusionner([], [gauche, droite], *A, source="atkis")
    registre.fusionner([], [gauche, droite], *B, source="atkis")
    (ids_g, tags), (ids_d, _) = (registre.voies[w] for w in sorted(registre.voies))
    assert ids_g[-1] == ids_d[0], "un seul nœud de part et d'autre de la limite"
    assert tags["hike2gpx"] == "atkis"


def _geopackage_bdtopo(chemin, troncons):
    """Un GeoPackage réduit, de même structure que celui de l'IGN : la table
    des tronçons (géométrie GPKG en Lambert 93) et son index RTree."""
    import sqlite3
    import struct

    import shapely
    from rasterio.warp import transform
    base = sqlite3.connect(chemin)
    base.execute("CREATE TABLE troncon_de_route (fid INTEGER PRIMARY KEY, cleabs TEXT, nature TEXT, "
                 "acces_pieton TEXT, prive INTEGER, insee_commune_gauche TEXT, insee_commune_droite TEXT, "
                 "geometrie BLOB)")
    base.execute("CREATE VIRTUAL TABLE rtree_troncon_de_route_geometrie USING rtree(id, minx, maxx, miny, maxy)")
    for fid, (cleabs, insee, lignes) in enumerate(troncons, 1):
        en_l93 = []
        for ligne in lignes:
            xs, ys = transform("EPSG:4326", "EPSG:2154", [lo for la, lo in ligne], [la for la, lo in ligne])
            en_l93.append(list(zip(xs, ys, [300.0] * len(xs))))      # avec l'altitude, comme la BD TOPO
        geometrie = shapely.MultiLineString(en_l93) if len(en_l93) > 1 else shapely.LineString(en_l93[0])
        blob = b"GP\x00\x01" + struct.pack("<i", 2154) + shapely.to_wkb(geometrie)
        base.execute("INSERT INTO troncon_de_route VALUES (?, ?, 'Sentier', NULL, 0, ?, ?, ?)",
                     (fid, cleabs, insee, insee, blob))
        x0, y0, x1, y1 = geometrie.bounds
        base.execute("INSERT INTO rtree_troncon_de_route_geometrie VALUES (?, ?, ?, ?, ?)", (fid, x0, x1, y0, y1))
    base.commit()
    base.close()


def test_troncons_gpkg_rend_les_troncons_en_coordonnees_gps(tmp_path):
    # Le passage Lambert 93 -> GPS par rasterio, sans pyproj (essai GitHub
    # Actions du 2026-10-27 : pyproj n'est pas une dépendance de l'application).
    gpkg = tmp_path / "bdtopo.gpkg"
    _geopackage_bdtopo(gpkg, [
        ("TRONROUT1", "83063", [[(43.330, 6.040), (43.331, 6.042)]]),
        ("TRONROUT2", "83063", [[(43.332, 6.043), (43.333, 6.044)], [(43.334, 6.045), (43.335, 6.046)]]),
        ("TRONROUT3", "06088", [[(43.336, 6.047), (43.337, 6.048)]])])
    troncons = case.troncons_gpkg(gpkg, 43.32, 6.03, 43.34, 6.05)
    assert [t["id"] for t in troncons] == ["TRONROUT1-0", "TRONROUT2-0", "TRONROUT2-1", "TRONROUT3-0"]
    assert troncons[0]["pts"][0] == pytest.approx([43.330, 6.040], abs=1e-6)
    assert sum(troncons[2]["pts"], []) == pytest.approx([43.334, 6.045, 43.335, 6.046], abs=1e-6), \
        "chaque partie d'un tronçon multiple, à sa place"
    assert {t["id"] for t in case.troncons_gpkg(gpkg, 43.32, 6.03, 43.34, 6.05, "83")} == \
        {"TRONROUT1-0", "TRONROUT2-0", "TRONROUT2-1"}, "le filtre par département"
    assert case.troncons_gpkg(gpkg, 44.0, 7.0, 44.1, 7.1) == []
