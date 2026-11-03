"""Partage au téléphone (partage.py), sur la boucle locale : le contrat de
docs/architecture/partage-telephone.md, éprouvé avec le lecteur du dépôt."""
import http.client
import io
import json
import urllib.parse
import urllib.request

import pytest

from hike2gpx import depot, fonds, hors_ligne, lot, partage
from hike2gpx.application import Application

ZONE = (43.30, 5.97, 43.36, 6.11)


class Reponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def preparer(dossier):
    """Un PC avec un lot installé (E5_N40) et un fond de carte."""
    h = hors_ligne.HorsLigne(dossier)
    source = dossier / "lot"
    source.mkdir(parents=True)
    (source / "E5_N40.rd5").write_bytes(b"rd5 de la case" * 1000)
    (source / "franchissements.json.gz").write_bytes(b"franchissements")
    (source / "calques.mbtiles").write_bytes(b"calques" * 50)
    lot.ecrire_manifeste(source, "E5_N40", [source / "E5_N40.rd5", source / "franchissements.json.gz",
                                             source / "calques.mbtiles"],
                         {"osm": "2026-10-25T21:21:21Z"}, type="osm", zone=[43.0, 5.0, 44.0, 6.0])
    h.installer(source)
    fonds.fabriquer(h.dossier_fonds / "E5_N40-scan25.mbtiles", "scan25", ZONE, (12, 12), "cle", debit=0,
                    ouvrir=lambda requete, timeout=None: Reponse(b"\xff\xd8 tuile " + requete.full_url[-30:].encode()))
    return h


@pytest.fixture
def ouvert(tmp_path):
    h = preparer(tmp_path)
    p = partage.Partage(h, port=8880, plage=20, adresse=lambda: "127.0.0.1")
    etat = p.ouvrir()
    yield p, etat, h
    p.fermer()


def requete(p, chemin, jeton=None, methode="GET", entetes=None):
    hote, port = p.serveur.server_address[:2]
    connexion = http.client.HTTPConnection(hote, port, timeout=5)
    try:
        en_tetes = dict(entetes or {})
        if jeton is not None:
            en_tetes["Authorization"] = f"Bearer {jeton}"
        connexion.request(methode, chemin, headers=en_tetes)
        r = connexion.getresponse()
        return r.status, dict(r.getheaders()), r.read()
    finally:
        connexion.close()


def test_le_qr_code_porte_l_adresse_du_catalogue_et_le_jeton(ouvert):
    p, etat, _ = ouvert
    assert etat["ouvert"] and etat["url"] == f"http://127.0.0.1:{p.serveur.server_address[1]}/depot/catalog.json"
    lien = urllib.parse.urlsplit(etat["lien"])
    assert (lien.scheme, lien.netloc, lien.path) == ("hike2gpx", "depot", "")
    q = urllib.parse.parse_qs(lien.query)
    assert q["url"] == [etat["url"]] and q["jeton"] == [p.jeton]
    assert "%3A%2F%2F" in etat["lien"], "l'adresse est encodée dans le lien"
    assert len(p.jeton) >= 43, "32 octets aléatoires en base64 URL"
    assert etat["qr"].startswith("<svg") and etat["lots"] == ["E5_N40"] and etat["fonds"] == ["E5_N40-scan25"]


def test_sans_jeton_valide_tout_est_refuse(ouvert):
    p, _, _ = ouvert
    for jeton in (None, "", "mauvais", p.jeton + "x"):
        statut, entetes, _ = requete(p, "/depot/catalog.json", jeton)
        assert statut == 401 and entetes["WWW-Authenticate"].startswith("Bearer"), jeton
    assert requete(p, "/depot/E5_N40/manifest.json", "mauvais")[0] == 401


def test_le_catalogue_est_celui_du_depot_avec_les_fonds(ouvert):
    p, _, h = ouvert
    statut, _, corps = requete(p, "/depot/catalog.json", p.jeton)
    catalogue = json.loads(corps)
    assert statut == 200 and catalogue["format"] == 1
    [entree] = catalogue["lots"]
    assert sorted(f["url"] for f in entree["fichiers"]) == [
        "E5_N40/E5_N40.rd5", "E5_N40/calques.mbtiles", "E5_N40/franchissements.json.gz", "E5_N40/manifest.json"]
    [fond] = catalogue["fonds"]
    chemin = h.dossier_fonds / "E5_N40-scan25.mbtiles"
    assert fond == {"nom": "E5_N40-scan25", "zone": list(ZONE), "zoom": [12, 12], "source": "scan25",
                    "octets": chemin.stat().st_size, "sha256": lot.empreinte(chemin),
                    "url": "fonds/E5_N40-scan25.mbtiles"}
    # Un lecteur qui ignore « fonds » (celui du PC) lit ce catalogue sans peine.
    lu = depot.lire_catalogue("http://pc/depot/catalog.json", ouvrir=lambda r, timeout=None: Reponse(corps))
    assert lu["lots"][0]["case"] == "E5_N40"


def test_les_fichiers_se_reprennent_par_range(ouvert):
    p, _, h = ouvert
    rd5 = (h.segments_osm / "E5_N40.rd5").read_bytes()
    statut, entetes, corps = requete(p, "/depot/E5_N40/E5_N40.rd5", p.jeton)
    assert statut == 200 and corps == rd5 and entetes["Accept-Ranges"] == "bytes"
    statut, entetes, corps = requete(p, "/depot/E5_N40/E5_N40.rd5", p.jeton, entetes={"Range": "bytes=100-"})
    assert statut == 206 and corps == rd5[100:] and entetes["Content-Range"] == f"bytes 100-{len(rd5) - 1}/{len(rd5)}"
    assert requete(p, "/depot/E5_N40/E5_N40.rd5", p.jeton, entetes={"Range": "bytes=10-19"})[2] == rd5[10:20]
    assert requete(p, "/depot/E5_N40/E5_N40.rd5", p.jeton, entetes={"Range": "bytes=-5"})[2] == rd5[-5:]
    assert requete(p, "/depot/E5_N40/E5_N40.rd5", p.jeton, entetes={"Range": f"bytes={len(rd5)}-"})[0] == 416
    statut, entetes, corps = requete(p, "/depot/fonds/E5_N40-scan25.mbtiles", p.jeton, methode="HEAD")
    assert statut == 200 and corps == b"" and int(entetes["Content-Length"]) > 0


def test_rien_d_autre_que_le_catalogue_n_est_servi(ouvert, tmp_path):
    p, _, _ = ouvert
    (tmp_path / "preferences.json").write_text('{"cle_ign": "secrete"}')
    for chemin in ("/depot/../preferences.json", "/depot/..%2Fpreferences.json", "/depot/%2e%2e/preferences.json",
                   "/depot/E5_N40/../../preferences.json", "/depot/hors-ligne/E5_N40/manifest.json",
                   "/depot/segments-osm/E5_N40.rd5", "/preferences.json", "/depot/", "/depot/C:/Windows/win.ini"):
        assert requete(p, chemin, p.jeton)[0] == 404, chemin
    assert requete(p, "/depot/catalog.json", p.jeton, methode="POST")[0] == 405


def test_bout_en_bout_le_lecteur_du_depot_installe_le_lot_partage(ouvert, tmp_path):
    # Ce que fera le téléphone, joué par le code du PC : catalogue, téléchargement
    # vérifié par SHA-256, installation ; le jeton dans chaque requête.
    p, etat, _ = ouvert

    def ouvrir(requete, timeout=None):
        requete.add_header("Authorization", f"Bearer {p.jeton}")
        return urllib.request.urlopen(requete, timeout=timeout)
    catalogue = depot.lire_catalogue(etat["url"], ouvrir=ouvrir)
    travail = depot.telecharger(catalogue["lots"][0], etat["url"], tmp_path / "telephone" / "recu", ouvrir=ouvrir)
    autre = hors_ligne.HorsLigne(tmp_path / "telephone")
    assert autre.installer(travail)["case"] == "E5_N40"


def test_le_jeton_change_a_chaque_ouverture_et_l_ancien_ne_vaut_plus(tmp_path):
    p = partage.Partage(preparer(tmp_path), port=8880, plage=20, adresse=lambda: "127.0.0.1")
    assert p.etat() == {"ouvert": False}, "fermé par défaut"
    p.ouvrir()
    premier = p.jeton
    p.ouvrir()
    try:
        assert p.jeton != premier
        assert requete(p, "/depot/catalog.json", premier)[0] == 401
        assert requete(p, "/depot/catalog.json", p.jeton)[0] == 200
    finally:
        assert p.fermer() == {"ouvert": False}
    assert p.serveur is None and p.jeton == ""


def test_l_application_ouvre_et_ferme_le_partage(tmp_path, monkeypatch):
    monkeypatch.setattr(partage, "ip_locale", lambda: "127.0.0.1")
    a = Application(tmp_path)
    a.partage.adresse = lambda: "127.0.0.1"
    get, post = a.routes()
    assert get["partage"]() == {"ouvert": False}
    etat = post["partage"]({"ouvrir": True})
    assert etat["ouvert"] and etat["lots"] == [] and etat["fonds"] == []
    a.arreter()
    assert get["partage"]() == {"ouvert": False}, "l'arrêt de hike2gpx ferme le partage"
    a.partage.adresse = lambda: (_ for _ in ()).throw(partage.ErreurPartage("Pas de réseau local."))
    assert post["partage"]({"ouvrir": True}) == {"ouvert": False, "erreur": "Pas de réseau local."}


def test_l_adresse_locale_est_privee_ou_refusee():
    try:
        adresse = partage.ip_locale()
    except partage.ErreurPartage:
        return
    import ipaddress
    assert ipaddress.ip_address(adresse).is_private
