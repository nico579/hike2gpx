"""Extraits d'OSM France : l'index bâti depuis l'arborescence et les contours,
le département choisi avant sa région, la région en repli (Nico,
2026-10-20 : « départements en priorité, et région en fall back »)."""
import io
import time
import urllib.error

from hike2gpx import franchissements as fr, geofabrik, osmfr

RACINE = """<a href="?C=N;O=D">Name</a> <a href="/extracts/europe/">Parent</a>
<a href="provence_alpes_cote_d_azur-latest.osm.pbf">x</a> <a href="provence_alpes_cote_d_azur.osm.pbf">x</a>
<a href="provence_alpes_cote_d_azur.osm.pbf.md5">x</a> <a href="provence_alpes_cote_d_azur/">x</a>
<a href="vide/">un répertoire sans extrait à son nom</a>"""
PACA = """<a href="var-latest.osm.pbf">x</a> <a href="var.osm.pbf">x</a> <a href="var.osm.pbf.md5">x</a>
<a href="alpes_de_haute_provence.osm.pbf">x</a> <a href="hautes_alpes.osm.pbf">x</a>"""


def carre(sud, ouest, nord, est, trou=None):
    lignes = ["polygon", "1", f"\t{ouest}\t{sud}", f"\t{est}\t{sud}", f"\t{est}\t{nord}", f"\t{ouest}\t{nord}", "END"]
    if trou:
        s, o, n, e = trou
        lignes += ["!2", f"\t{o}\t{s}", f"\t{e}\t{s}", f"\t{e}\t{n}", f"\t{o}\t{n}", "END"]
    return "\n".join(lignes + ["END"])


PAGES = {
    osmfr.EXTRAITS: RACINE,
    osmfr.EXTRAITS + "provence_alpes_cote_d_azur/": PACA,
    osmfr.CONTOURS + "provence_alpes_cote_d_azur.poly": carre(42.9, 4.2, 45.2, 7.8),
    # Le Var et son enclave, où la tuile n'est plus tout entière dans le département.
    osmfr.CONTOURS + "provence_alpes_cote_d_azur/var.poly": carre(43.0, 5.6, 43.8, 6.95, trou=(43.4, 6.0, 43.45, 6.1)),
    osmfr.CONTOURS + "provence_alpes_cote_d_azur/alpes_de_haute_provence.poly": carre(43.7, 5.5, 44.7, 6.9),
    # hautes_alpes.poly manque : ce seul département est écarté.
}


def ouvrir(demande, timeout):
    if demande.full_url not in PAGES:
        raise urllib.error.HTTPError(demande.full_url, 404, "absent", {}, None)
    return io.BytesIO(PAGES[demande.full_url].encode())


def test_l_index_se_batit_depuis_l_arborescence_et_les_contours():
    regions = {r["id"]: r for r in osmfr.batir(ouvrir)}
    assert sorted(regions) == ["fr-alpes-de-haute-provence", "fr-provence-alpes-cote-d-azur", "fr-var"]
    var = regions["fr-var"]
    assert (var["nom"], var["genre"], var["bornes"]) == ("Var", "departement", (43.0, 5.6, 43.8, 6.95))
    # Ses voies s'arrêtent net à sa frontière : la région de Geofabrik prendra le relais.
    assert all(r["voies_coupees"] for r in regions.values())
    # Le nom sans « -latest » : son MD5 est publié à côté (var.osm.pbf.md5).
    assert var["pbf"] == osmfr.EXTRAITS + "provence_alpes_cote_d_azur/var.osm.pbf"
    assert len(var["polygones"][0]) == 2                     # le contour et son enclave
    assert regions["fr-alpes-de-haute-provence"]["nom"] == "Alpes-de-Haute-Provence"
    assert regions["fr-provence-alpes-cote-d-azur"]["genre"] == "region"


def test_le_departement_d_abord_la_region_en_repli():
    regions = osmfr.batir(ouvrir)

    def choix(lat, lon, liste=regions):
        return geofabrik.region_de_tuile(liste, *fr.tuile_du_point(lat, lon))["id"]

    assert choix(43.33, 6.02) == "fr-var"                              # tout entière dans le Var
    assert choix(43.42, 6.02) == "fr-provence-alpes-cote-d-azur"         # dans l'enclave : la région
    assert choix(43.82, 6.02) == "fr-alpes-de-haute-provence"
    assert choix(44.9, 6.5) == "fr-provence-alpes-cote-d-azur"           # Hautes-Alpes écartées : la région
    # Le département vient d'échouer : la région prend sa place, une heure.
    taches = geofabrik.Telechargements("inutile")
    taches._echecs["fr-var"] = time.monotonic()
    assert choix(43.33, 6.02, [r for r in regions if taches.disponible(r["id"])]) == "fr-provence-alpes-cote-d-azur"


def test_l_index_se_garde_un_mois_et_se_rebatit_en_tache_de_fond(tmp_path, monkeypatch):
    preparations = []
    monkeypatch.setattr(osmfr.INDEX, "preparer", lambda dossier, **options: preparations.append(dossier))
    # Pas encore d'index : Geofabrik seul en attendant, et l'index se prépare.
    assert osmfr.regions(tmp_path) == [] and len(preparations) == 1
    osmfr.INDEX._refaire(tmp_path, ouvrir)
    regions = osmfr.regions(tmp_path)
    assert {r["id"] for r in regions} == {"fr-var", "fr-alpes-de-haute-provence", "fr-provence-alpes-cote-d-azur"}
    assert len(preparations) == 1
    assert geofabrik.region_de_tuile(regions, *fr.tuile_du_point(43.33, 6.02))["id"] == "fr-var"
    # Vieux de plus d'un mois : il sert encore pendant qu'il se rebâtit.
    plus_tard = time.time() + geofabrik.INDEX_TTL_S + 60
    assert osmfr.regions(tmp_path, maintenant=lambda: plus_tard) == regions and len(preparations) == 2


def test_un_index_impossible_a_batir_ne_casse_rien(tmp_path, monkeypatch):
    def panne(demande, timeout):
        raise urllib.error.HTTPError(demande.full_url, 404, "absent", {}, None)

    osmfr.INDEX._refaire(tmp_path, panne)
    monkeypatch.setattr(osmfr.INDEX, "preparer", lambda dossier, **options: None)
    assert osmfr.regions(tmp_path) == []
    assert osmfr.INDEX._echec is not None
    osmfr.INDEX._echec = None
