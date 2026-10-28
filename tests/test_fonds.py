"""Fonds de carte hors ligne (fonds.py), sans réseau : le service WMTS de l'IGN
est simulé, la page lit les tuiles par le serveur local."""
import http.client
import io
import sqlite3
import urllib.error
import urllib.parse
import urllib.request

import pytest

from hike2gpx import fonds, lot, web
from hike2gpx.application import Application

ZONE = (43.30, 5.97, 43.36, 6.11)       # une vue de Garéoult
JPEG = b"\xff\xd8\xff\xe0 tuile"


class Reponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def service(absentes=(), statut=None):
    """urlopen simulé du WMTS : une tuile JPEG par demande, 404 pour les
    tuiles absentes (hors de France), ou le statut donné pour toutes."""
    demandes = []

    def ouvrir(requete, timeout=None):
        demandes.append(requete)
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(requete.full_url).query)
        tuile = tuple(int(q[k][0]) for k in ("TILEMATRIX", "TILECOL", "TILEROW"))
        code = statut or (404 if tuile in absentes else 200)
        if code != 200:
            raise urllib.error.HTTPError(requete.full_url, code, "refus", {}, None)
        return Reponse(JPEG + repr(tuile).encode())
    ouvrir.demandes = demandes
    return ouvrir


def test_l_adresse_des_tuiles_est_celle_de_la_page():
    # Celle de tuileIgn() dans providers/fr.js : service privé et clé pour le SCAN 25.
    assert fonds.url_tuile("scan25", 14, 8466, 5986, "ma_cle") == (
        "https://data.geopf.fr/private/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
        "&LAYER=GEOGRAPHICALGRIDSYSTEMS.MAPS&STYLE=normal&TILEMATRIXSET=PM&FORMAT=image/jpeg"
        "&TILEMATRIX=14&TILECOL=8466&TILEROW=5986&apikey=ma_cle")
    assert fonds.url_tuile("plan", 14, 1, 2).startswith("https://data.geopf.fr/wmts?")
    assert "apikey" not in fonds.url_tuile("plan", 14, 1, 2, "ma_cle")
    assert fonds.source_pour("ma_cle") == "scan25" and fonds.source_pour("") == "plan"


def test_zooms_d_une_vue_et_d_une_case():
    assert fonds.zooms_vue(ZONE) == (6, 16), "une vue d'écran descend au 16"
    assert len(fonds.tuiles(ZONE, (6, 16))) == 631
    # Une vue d'un degré ne tiendrait pas au 16 : elle s'arrête plus haut.
    assert fonds.zooms_vue((43.0, 5.5, 44.0, 6.5))[1] < 16
    assert len(fonds.tuiles(lot.boite_case("E5_N40"), fonds.ZOOMS_CASE)) == 24042


def test_un_fond_s_ecrit_en_mbtiles_et_se_relit(tmp_path):
    ouvrir = service(absentes={(16, 33181, 23933)})
    suivi = []
    chemin = tmp_path / "fonds" / "E5_N40-scan25-vue-abc123.mbtiles"
    decrit = fonds.fabriquer(chemin, "scan25", ZONE, (12, 14), "cle", suivi=lambda f, t: suivi.append((f, t)),
                             ouvrir=ouvrir, debit=0)
    assert decrit == {"nom": "E5_N40-scan25-vue-abc123", "zone": list(ZONE), "zoom": [12, 14],
                      "source": "scan25", "format": "jpg", "octets": chemin.stat().st_size}
    assert suivi[-1] == (61, 61) and len(ouvrir.demandes) == 61
    assert all(r.get_header("User-agent").startswith("hike2gpx/") for r in ouvrir.demandes)
    # MBTiles 1.3 : métadonnées requises, rangées TMS (comptées depuis le sud).
    with sqlite3.connect(chemin) as base:
        meta = dict(base.execute("SELECT name, value FROM metadata"))
        assert meta["format"] == "jpg" and meta["type"] == "baselayer" and meta["bounds"] == "5.97,43.3,6.11,43.36"
        assert "cle" not in str(meta.values()), "la clé IGN ne s'écrit jamais dans le fond"
    base.close()
    x, y = lot.tuile_du_point(14, 6.04, 43.33)
    assert fonds.lire_tuile(chemin, 14, x, y) == JPEG + repr((14, x, y)).encode()
    assert fonds.lire_tuile(chemin, 15, x, y) is None
    assert not chemin.with_name(chemin.name + ".part").exists()


def test_un_fond_arrete_reprend_ou_il_en_etait(tmp_path):
    chemin = tmp_path / "f.mbtiles"
    restantes = [20]

    def continuer():
        restantes[0] -= 1
        return restantes[0] > 0
    with pytest.raises(fonds.Abandon):
        fonds.fabriquer(chemin, "plan", ZONE, (12, 14), ouvrir=service(), debit=0, fils=1, continuer=continuer)
    assert not chemin.exists() and chemin.with_name("f.mbtiles.part").exists()
    ouvrir = service()
    fonds.fabriquer(chemin, "plan", ZONE, (12, 14), ouvrir=ouvrir, debit=0)
    assert 0 < len(ouvrir.demandes) < 61, "les tuiles déjà là ne se redemandent pas"
    with sqlite3.connect(chemin) as base:
        assert base.execute("SELECT COUNT(*) FROM tiles").fetchone()[0] == 61
    base.close()


def test_cle_refusee_et_zone_hors_de_france(tmp_path):
    with pytest.raises(fonds.ErreurFond, match="clé"):
        fonds.fabriquer(tmp_path / "a.mbtiles", "scan25", ZONE, (12, 12), "cle", ouvrir=service(statut=403), debit=0)
    with pytest.raises(fonds.ErreurFond, match="clé IGN"):
        fonds.fabriquer(tmp_path / "b.mbtiles", "scan25", ZONE, (12, 12), "", ouvrir=service(), debit=0)
    with pytest.raises(fonds.ErreurFond, match="Aucune tuile"):
        fonds.fabriquer(tmp_path / "c.mbtiles", "plan", ZONE, (12, 12), ouvrir=service(statut=404), debit=0)


def test_le_debit_reste_modere():
    limiteur = fonds._Debit(50.0)
    import time
    debut = time.monotonic()
    for _ in range(11):
        limiteur.attendre()
    assert time.monotonic() - debut >= 0.15, "11 requêtes à 50/s : 0,2 s (à la granularité de l'horloge près)"


def test_noms_de_fonds_surs():
    assert fonds.nom_fond("E5_N40", "scan25") == "E5_N40-scan25"
    assert fonds.nom_fond("E5_N40", "plan", ZONE).startswith("E5_N40-plan-vue-")
    for nom in ("../preferences", "a/b", "a\\b", "..", "", "x" * 81, "é"):
        assert not fonds.nom_valide(nom), nom


def test_l_application_prepare_un_fond_et_le_liste(tmp_path, monkeypatch):
    a = Application(tmp_path)
    a.enregistrer_reglages({"cle_ign": "ma_cle"})
    ouvrir = service()
    monkeypatch.setattr(urllib.request, "urlopen", ouvrir)
    monkeypatch.setattr(fonds, "DEBIT", 0)
    monkeypatch.setattr(fonds, "ZOOMS_VUE", (12, 13))
    assert "erreur" in a.preparer_fond({"case": "../x"})
    reponse = a.preparer_fond({"case": "E5_N40", "zone": list(ZONE)})
    assert reponse["lot_en_cours"]["etape"] == "fond"
    a._fil_lot.join(10)
    etat = a.lot_en_cours()
    assert etat["etape"] == "fini" and etat["fond"].startswith("E5_N40-scan25-vue-"), etat
    [f] = a.lots_hors_ligne()["fonds"]
    assert f["source"] == "scan25" and f["zoom"] == [12, 13] and f["nom"] == etat["fond"]
    assert "apikey=ma_cle" in ouvrir.demandes[0].full_url
    assert a.hors_ligne.lots() == [], "un fond n'est pas un lot : rien à publier"


def test_la_page_lit_les_tuiles_du_fond_par_le_serveur_local(tmp_path):
    a = Application(tmp_path)
    fonds.fabriquer(a.hors_ligne.dossier_fonds / "E5_N40-plan.mbtiles", "plan", ZONE, (12, 12),
                    ouvrir=service(), debit=0)
    x, y = lot.tuile_du_point(12, 6.04, 43.33)
    serveur, port = web.demarrer(a, port=8860, plage=20)
    try:
        connexion = http.client.HTTPConnection(web.HOST, port, timeout=5)
        try:
            def lire(chemin):
                connexion.request("GET", chemin)
                reponse = connexion.getresponse()
                return reponse.status, reponse.getheader("Content-Type"), reponse.read()
            assert lire(f"/fonds/E5_N40-plan/12/{x}/{y}") == (200, "image/jpeg", JPEG + repr((12, x, y)).encode())
            assert lire(f"/fonds/E5_N40-plan/13/{x}/{y}")[0] == 404
            for chemin in ("/fonds/..%2Fpreferences/12/1/1", "/fonds/../preferences.json", "/fonds/absent/1/1/1",
                           "/fonds/E5_N40-plan/-1/1/1", "/fonds/E5_N40-plan/12/1"):
                assert lire(chemin)[0] == 404, chemin
        finally:
            connexion.close()
    finally:
        serveur.shutdown()
        serveur.server_close()


def test_un_fond_n_entre_jamais_dans_une_publication(tmp_path):
    # Le SCAN 25 n'est pas libre : la publication du dépôt (depot.py) ne prend
    # que des lots, décrits par leur manifeste, jamais le dossier des fonds.
    from hike2gpx import depot
    a = Application(tmp_path)
    fonds.fabriquer(a.hors_ligne.dossier_fonds / "E5_N40-scan25.mbtiles", "scan25", ZONE, (12, 12), "cle",
                    ouvrir=service(), debit=0)
    depot.ecrire_catalogue(a.hors_ligne.racine, tmp_path / "publication")
    assert [p.name for p in (tmp_path / "publication").iterdir()] == ["catalog.json"]
