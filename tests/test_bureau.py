"""Intégration au bureau par le commun : relance, raccourci, menu de l'icône,
instance unique."""
import sys
import http.client
import urllib.request
from pathlib import Path

import pytest

from hike2gpx import bureau, web


def test_relance_depuis_les_sources_repasse_par_le_module(monkeypatch):
    monkeypatch.setattr(sys, "argv", [r"C:\venv\Scripts\hike2gpx.exe", "serve", "--port", "8800"])
    assert bureau.commande_relance() == [sys.executable, "-m", "hike2gpx", "serve", "--port", "8800"]


def test_raccourci_lance_le_programme_sans_argument(tmp_path):
    lignes = []
    assert bureau.commande_programme()[1:] == ["-m", "hike2gpx"]
    assert bureau.creer_raccourci("fr", tmp_path, simulation=True, dossier_bureau=tmp_path, ecrire=lignes.append) == 0
    assert bureau.ICONE.is_file() and bureau.ICONE.with_suffix(".png").is_file()


def test_raccourci_au_premier_lancement_une_seule_fois(monkeypatch, tmp_path):
    appels = []
    monkeypatch.setattr(bureau, "creer_raccourci", lambda code, dossier: appels.append((code, dossier)))
    assert bureau.raccourci_au_premier_lancement(lambda: "en", tmp_path, fige=True)
    assert not bureau.raccourci_au_premier_lancement(lambda: "en", tmp_path, fige=True)
    assert appels == [("en", tmp_path)]
    assert (tmp_path / bureau.MARQUEUR_RACCOURCI).is_file()


def test_raccourci_au_premier_lancement_rien_depuis_les_sources(monkeypatch, tmp_path):
    appels = []
    monkeypatch.setattr(bureau, "creer_raccourci", lambda *a: appels.append(a))
    assert not bureau.raccourci_au_premier_lancement(lambda: "fr", tmp_path)
    assert appels == [] and not (tmp_path / bureau.MARQUEUR_RACCOURCI).exists()


def test_langue_du_menu(monkeypatch):
    assert bureau.langue(lambda: "en") == "en"
    monkeypatch.setattr(bureau.locale, "getlocale", lambda: ("French_France", "1252"))
    assert bureau.langue(lambda: None) == "fr"


class Verificateur:
    page_des_releases = "https://github.com/nico579/hike2gpx/releases/latest"

    def __init__(self, info=None):
        self.info = info

    def disponible(self):
        return self.info


def test_menu_commun(monkeypatch):
    ouverts = []
    monkeypatch.setattr(bureau.webbrowser, "open", ouverts.append)
    actions = bureau.actions("http://127.0.0.1:8795/", lambda: None,
                             Verificateur({"version": "0.2.0", "page": "https://exemple/v0.2.0"}),
                             lambda: "fr", Path("."))
    assert actions.version_disponible() == "0.2.0" and actions.langue() == "fr"
    actions.ouvrir()
    actions.mettre_a_jour()
    assert ouverts == ["http://127.0.0.1:8795/", "https://exemple/v0.2.0"]
    assert bureau.actions("u", lambda: None, Verificateur(), lambda: None, Path(".")).version_disponible() is None


def test_onglet_de_la_page_porte_l_icone(tmp_path):
    from hike2gpx.application import Application
    serveur, port = web.demarrer(Application(tmp_path), port=8840, plage=20)
    try:
        with urllib.request.urlopen(f"http://{web.HOST}:{port}/favicon.ico", timeout=5) as reponse:
            assert reponse.headers["Content-Type"] == "image/x-icon"
            assert reponse.read() == bureau.ICONE.read_bytes()
        with urllib.request.urlopen(f"http://{web.HOST}:{port}/", timeout=5) as reponse:
            page = reponse.read().decode("utf-8")
            assert '<link rel="icon" href="/favicon.ico"' in page
            assert '<img class="brand-icon" src="/favicon.ico"' in page
    finally:
        serveur.shutdown()
        serveur.server_close()


def test_la_page_charge_les_providers_depuis_leur_dossier(tmp_path):
    from hike2gpx.application import Application
    serveur, port = web.demarrer(Application(tmp_path), port=8840, plage=20)
    try:
        with urllib.request.urlopen(f"http://{web.HOST}:{port}/map-providers.js?v=3", timeout=5) as reponse:
            script = reponse.read().decode("utf-8")
            assert reponse.headers["Content-Type"].startswith("text/javascript")
        for code in ("fr", "es", "ch", "at", "nl", "no", "lu", "us"):
            assert f"HIKE2GPX_MAP_PROVIDERS.{code} =" in script
        connexion = http.client.HTTPConnection(web.HOST, port, timeout=5)
        try:
            connexion.request("GET", "/documentation/pays")
            reponse = connexion.getresponse()
            assert reponse.status == 302
            assert reponse.getheader("Location") == web.url_couverture_pays()
            reponse.read()
            connexion.request("GET", "/documentation/pays?lang=en")
            reponse = connexion.getresponse()
            assert reponse.status == 302
            assert reponse.getheader("Location") == web.url_couverture_pays("en")
        finally:
            connexion.close()
    finally:
        serveur.shutdown()
        serveur.server_close()


def test_mode_serveur_accepte_uniquement_le_domaine_du_proxy(tmp_path):
    from hike2gpx.application import Application

    application = Application(tmp_path, mode_serveur=True)
    serveur, port = web.demarrer(application, port=8840, plage=20, nom_hote="rando.example.org")
    try:
        connexion = http.client.HTTPConnection(web.HOST, port, timeout=5)
        try:
            for hote, origine, attendu in [
                ("rando.example.org", "https://rando.example.org", 200),
                ("autre.example.org", "https://autre.example.org", 403),
                ("rando.example.org", "https://autre.example.org", 403),
            ]:
                connexion.request("GET", "/api/etat", headers={"Host": hote, "Origin": origine})
                reponse = connexion.getresponse()
                assert reponse.status == attendu
                reponse.read()
        finally:
            connexion.close()
        assert serveur.server_address[0] == "127.0.0.1"
    finally:
        serveur.shutdown()
        serveur.server_close()


def test_mode_serveur_ecarte_les_actions_du_bureau(tmp_path):
    from hike2gpx.application import Application

    application = Application(tmp_path, mode_serveur=True)
    get, post = application.routes()
    assert "journal" not in get and "ouvrir_journaux" not in post
    assert application.etat()["mode_serveur"] is True
    assert "dossier" not in application.etat()
    premiere = application._prendre_vue("osm", 100)
    seconde = application._prendre_vue("osm", 100)
    assert premiere != seconde
    assert application.arreter_calques({"calques": ["osm"]}) == {"arretes": []}
    assert "reglages" not in get and "donnees" not in get
    assert "donnees" not in post and "paquet-zone" in get and "paquet-zone" not in post


def test_calcul_serveur_ne_prepare_jamais_une_zone_depuis_une_requete(tmp_path, monkeypatch):
    from hike2gpx.application import Application

    application = Application(tmp_path, mode_serveur=True)
    monkeypatch.setattr(application, "_extrait_automatique", lambda *_: pytest.fail("extrait lancé"))
    monkeypatch.setattr(application.maison, "preparer", lambda *_args, **_kw: pytest.fail("fusion lancée"))
    points = {"points": [[43.4, 6.0], [43.41, 6.01]], "source": "ign", "strict": True}
    assert application._itineraire(points)["code"] == "zone_non_preparee"
    jeton = "a" * 32
    monkeypatch.setattr(application, "lire_paquet", lambda *_: {
        "pret": True, "segments": [{"url": f"/api/paquets/{jeton}/E5_N40.rd5"}]})
    monkeypatch.setattr(application.installation, "installee", lambda: True)
    monkeypatch.setattr(application, "_itineraire_paquet", lambda *_: {"moteur": "cloud-local"})
    assert application._itineraire(points)["moteur"] == "serveur-secours"


def test_mode_serveur_exige_un_nom_dns(tmp_path):
    from hike2gpx.application import Application

    for nom in ("http://rando.example.org", "localhost", "rando.example.org:443"):
        with pytest.raises(ValueError):
            web.demarrer(Application(tmp_path), port=8840, plage=1, nom_hote=nom)


def test_paquet_de_zone_fournit_tuiles_et_coupes_finales(tmp_path, monkeypatch):
    from hike2gpx import brouter, franchissements
    from hike2gpx.application import Application

    application = Application(tmp_path, mode_serveur=True)
    application.installation.segments.mkdir(parents=True)
    (application.installation.segments / "E5_N40.rd5").write_bytes(b"tuile")
    application.installation.profils.mkdir(parents=True)
    (application.installation.profils / f"{brouter.PROFIL}.brf").write_text("profil", encoding="utf-8")
    (application.installation.profils / "lookups.dat").write_text("tags", encoding="utf-8")
    monkeypatch.setattr(application.installation, "installee", lambda: True)
    monkeypatch.setattr(application.installation, "segment_present", lambda _: True)
    monkeypatch.setattr(application, "_extrait_automatique", lambda *_: None)
    monkeypatch.setattr(brouter, "segments_zone", lambda *_: ["E5_N40"])
    franchissement = {"cle": "porte", "statut": "uncertain", "raison": "à vérifier",
                      "nature": "Portail", "lat": 43.4, "lon": 6.0, "osm": "node/1",
                      "coupes": [[[6.0, 43.4], [6.00001, 43.4]]]}
    monkeypatch.setattr(franchissements, "franchissements_zone", lambda *a, **k: [franchissement])
    paquet = application.preparer_paquet({"points": [[43.4, 6.0], [43.401, 6.001]],
                                         "officiel": False, "strict": True})
    assert paquet["pret"] and paquet["source"] == "osm" and paquet["profil"] == "profil"
    assert paquet["polylines"] == "6.0000000,43.4000000,6.0000100,43.4000000"
    assert paquet["segments"][0]["sha256"] and paquet["segments"][0]["octets"] == 5
    assert {a["nom"] for a in paquet["assets"]} == {"hike2gpx.brf", "lookups.dat"}
    assert paquet["franchissements"][0]["nature"] == "Portail"
    assert application.lire_paquet((43.4, 6.0, 43.401, 6.001), "ign", "1", "0")["pret"]
    assert application.lire_paquet(tuple(paquet["zone"]), "ign", "1", "0")["pret"]

    serveur, port = web.demarrer(application, port=8840, plage=20, nom_hote="rando.example.org")
    try:
        connexion = http.client.HTTPConnection(web.HOST, port, timeout=5)
        try:
            connexion.request("GET", paquet["segments"][0]["url"],
                              headers={"Host": "rando.example.org", "Range": "bytes=1-3"})
            reponse = connexion.getresponse()
            assert reponse.status == 206 and reponse.read() == b"uil"
        finally:
            connexion.close()
    finally:
        serveur.shutdown()
        serveur.server_close()


def test_l_archive_de_chaque_systeme_suit_la_convention_publiee():
    # Les noms que build.py publie (il les demande au commun) : la mise à jour
    # automatique cherche ces fichiers dans la release, cette racine dedans.
    from nico579_commons import maj_install

    def archive(systeme, machine):
        return maj_install.archive_standard("hike2gpx", racine_macos=bureau.RACINE_MACOS, systeme=systeme,
                                            machine=machine)

    assert archive("Windows", "AMD64") == ("hike2gpx-windows-x86_64.zip", "zip", "hike2gpx-windows-x86_64")
    assert archive("Linux", "x86_64") == ("hike2gpx-linux-x86_64.tar.gz", "tar", "hike2gpx-linux-x86_64")
    assert archive("Darwin", "arm64") == ("hike2gpx-macos-arm64.zip", "zip", "hike2gpx.app")
    # La même racine macOS que celle que construit build.py.
    build = (Path(__file__).parents[1] / "build.py").read_text(encoding="utf-8")
    assert f'RACINE_MACOS = "{bureau.RACINE_MACOS}"' in build


def test_mettre_a_jour_installe_le_bundle_et_ouvre_la_page_depuis_les_sources(tmp_path, monkeypatch):
    from nico579_commons import maj
    verificateur = maj.Verificateur(bureau.DEPOT, "0.1.0", cache=tmp_path / "maj.json")
    # Depuis les sources, l'installateur du commun refuse : rien à remplacer.
    possible, raison = bureau.installateur(verificateur, quitter=lambda: None).possible()
    assert not possible and raison
    ouvertes, demarrees = [], []
    monkeypatch.setattr(bureau.webbrowser, "open", ouvertes.append)

    class Installateur:
        def __init__(self, possible):
            self.oui = possible

        def possible(self):
            return (self.oui, "" if self.oui else "source_mode")

        def demarrer(self):
            demarrees.append(True)

    bureau.actions("u", lambda: None, verificateur, lambda: None, tmp_path, Installateur(True)).mettre_a_jour()
    assert demarrees == [True] and ouvertes == []
    bureau.actions("u", lambda: None, verificateur, lambda: None, tmp_path, Installateur(False)).mettre_a_jour()
    assert demarrees == [True] and ouvertes == [verificateur.page_des_releases]


def test_le_bandeau_de_mise_a_jour_a_ses_routes(tmp_path):
    import json

    from nico579_commons import maj

    from hike2gpx.application import Application
    verificateur = maj.Verificateur(bureau.DEPOT, "0.1.0", cache=tmp_path / "maj.json")
    installateur = bureau.installateur(verificateur, quitter=lambda: None)
    serveur, port = web.demarrer(Application(tmp_path), port=8840, plage=20, installateur=installateur)
    try:
        with urllib.request.urlopen(f"http://{web.HOST}:{port}/api/maj", timeout=5) as reponse:
            etat = json.loads(reponse.read())
        # Lancé depuis les sources : la version en place, rien de plus récent
        # connu sans question à GitHub, et l'installation refusée en clair.
        assert etat["version_locale"] == "0.1.0" and etat["version"] is None
        assert etat["possible"] is False and etat["raison"] and etat["etat"]["etat"] == "inactif"
        with urllib.request.urlopen(f"http://{web.HOST}:{port}/nico579-maj.js", timeout=5) as reponse:
            assert b"nico579-maj" in reponse.read()
    finally:
        serveur.shutdown()
        serveur.server_close()


def test_relance_rouvre_le_serveur_deja_lance(monkeypatch, tmp_path):
    # Une seule instance : relancé, hike2gpx rouvre la page du serveur en place.
    ouverts = []
    monkeypatch.setattr(web.serveweb, "instance_existante", lambda app, hote, port, timeout=1.0: port == 8797)
    monkeypatch.setattr(web.webbrowser, "open", ouverts.append)
    monkeypatch.setattr(web, "demarrer", lambda *args, **options: pytest.fail("second serveur démarré"))
    web.servir(tmp_path, 8795)
    assert ouverts == ["http://127.0.0.1:8797/"]
