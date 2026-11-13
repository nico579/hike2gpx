import io
import json
import urllib.parse

import pytest

from hike2gpx import depot, lot

DEPOT = "https://github.com/nico579/hike2gpx-bundles/releases/download/bundles/catalog.json"


def fabriquer_lot(dossier, case="E5_N40", rd5=b"rd5 de la case" * 100):
    dossier.mkdir(parents=True)
    (dossier / f"{case}.rd5").write_bytes(rd5)
    (dossier / "franchissements.json.gz").write_bytes(b"franchissements")
    (dossier / "calques.mbtiles").write_bytes(b"calques" * 50)
    lot.ecrire_manifeste(dossier, case, [dossier / f"{case}.rd5", dossier / "franchissements.json.gz",
                                         dossier / "calques.mbtiles"],
                         {"osm": "2026-10-25T21:21:21Z", "bdtopo": "2026-09-15"}, type="enrichi",
                         fournisseurs=["ign"], zone=[43.0, 5.0, 44.0, 6.0], emprise_enrichie=[43.0, 5.0, 44.0, 6.0])


def test_catalogue_a_plat_pour_une_publication_github(tmp_path):
    fabriquer_lot(tmp_path / "lots" / "E5_N40")
    chemin = depot.ecrire_catalogue(tmp_path / "lots", tmp_path / "publication")
    catalogue = json.loads(chemin.read_text(encoding="utf-8"))
    [entree] = catalogue["lots"]
    assert entree["case"] == "E5_N40" and entree["fournisseurs"] == ["ign"]
    assert sorted(f["url"] for f in entree["fichiers"]) == [
        "E5_N40.E5_N40.rd5", "E5_N40.calques.mbtiles", "E5_N40.franchissements.json.gz", "E5_N40.manifest.json"]
    assert sorted(p.name for p in (tmp_path / "publication").iterdir()) == [
        "E5_N40.E5_N40.rd5", "E5_N40.calques.mbtiles", "E5_N40.franchissements.json.gz", "E5_N40.manifest.json",
        "catalog.json"], "une liste plate, comme une publication GitHub"
    assert entree["octets"] == sum(f["octets"] for f in entree["fichiers"])


def test_catalogue_en_dossiers_pour_un_pc_qui_sert_ses_lots(tmp_path):
    fabriquer_lot(tmp_path / "lots" / "E5_N40")
    catalogue = json.loads(depot.ecrire_catalogue(tmp_path / "lots").read_text(encoding="utf-8"))
    assert "E5_N40/calques.mbtiles" in {f["url"] for f in catalogue["lots"][0]["fichiers"]}


class Reponse(io.BytesIO):
    def __init__(self, donnees, status=200):
        super().__init__(donnees)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def servir(publication, coupures=()):
    """urlopen simulé : sert les fichiers de la publication sous l'adresse du
    dépôt, Range compris ; un nom de coupures est coupé à mi-chemin une fois."""
    coupes = set(coupures)
    demandes = []

    def ouvrir(demande, timeout):
        nom = urllib.parse.urlparse(demande.full_url).path.rsplit("/", 1)[-1]
        donnees = (publication / nom).read_bytes()
        plage = demande.get_header("Range")
        demandes.append((nom, plage))
        if plage:
            return Reponse(donnees[int(plage[6:-1]):], 206)
        if nom in coupes:
            coupes.discard(nom)

            class Coupee(Reponse):
                def read(self, n=-1):
                    morceau = super().read(len(donnees) // 2 if self.tell() == 0 else 0)
                    if not morceau:
                        raise ConnectionResetError("coupure")
                    return morceau
            return Coupee(donnees)
        return Reponse(donnees)
    return ouvrir, demandes


def test_telecharger_un_lot_reprend_une_coupure_et_verifie_tout(tmp_path, monkeypatch):
    fabriquer_lot(tmp_path / "lots" / "E5_N40")
    depot.ecrire_catalogue(tmp_path / "lots", tmp_path / "publication")
    ouvrir, demandes = servir(tmp_path / "publication", coupures={"E5_N40.E5_N40.rd5"})
    monkeypatch.setattr(depot.time, "sleep", lambda s: None)
    catalogue = depot.lire_catalogue(DEPOT, ouvrir)
    suivi = []
    depot.telecharger(catalogue["lots"][0], DEPOT, tmp_path / "travail", ouvrir=ouvrir,
                      suivi=lambda faites, total: suivi.append((faites, total)))
    assert (tmp_path / "travail" / "E5_N40.rd5").read_bytes() == (tmp_path / "lots" / "E5_N40" / "E5_N40.rd5").read_bytes()
    assert ("E5_N40.E5_N40.rd5", "bytes=700-") in demandes, "la coupure reprend où elle s'était arrêtée"
    assert suivi[-1][0] == suivi[-1][1] == catalogue["lots"][0]["octets"]
    # Une seule barre pour tout le lot : le total couvre tous ses fichiers et
    # l'avancement ne recule jamais d'un fichier au suivant.
    assert {total for _, total in suivi} == {catalogue["lots"][0]["octets"]}
    assert [f for f, _ in suivi] == sorted(f for f, _ in suivi)
    from hike2gpx import hors_ligne
    assert hors_ligne.HorsLigne(tmp_path / "donnees").installer(tmp_path / "travail")["case"] == "E5_N40"


def test_un_fichier_altere_au_depot_est_refuse(tmp_path, monkeypatch):
    fabriquer_lot(tmp_path / "lots" / "E5_N40")
    depot.ecrire_catalogue(tmp_path / "lots", tmp_path / "publication")
    (tmp_path / "publication" / "E5_N40.calques.mbtiles").write_bytes(b"calqueS" * 50)   # même taille
    ouvrir, _ = servir(tmp_path / "publication")
    monkeypatch.setattr(depot.time, "sleep", lambda s: None)
    catalogue = depot.lire_catalogue(DEPOT, ouvrir)
    with pytest.raises(depot.ErreurDepot, match="altéré"):
        depot.telecharger(catalogue["lots"][0], DEPOT, tmp_path / "travail", ouvrir=ouvrir)


def test_l_application_telecharge_et_installe_un_lot_du_depot(tmp_path, monkeypatch):
    from hike2gpx import application as appli
    fabriquer_lot(tmp_path / "lots" / "E5_N40")
    depot.ecrire_catalogue(tmp_path / "lots", tmp_path / "publication")
    ouvrir, _ = servir(tmp_path / "publication")
    monkeypatch.setattr(depot.urllib.request, "urlopen", ouvrir)
    a = appli.Application(tmp_path / "donnees")
    assert [(l["case"], l["etat"]) for l in a.catalogue_lots()["lots"]] == [("E5_N40", "absent")]
    assert a.telecharger_lot({"case": "W5_N45"})["erreur"] == "Ce lot n'est pas au catalogue du dépôt."
    a.telecharger_lot({"case": "E5_N40"})
    a._fil_lot.join(10)
    etat = a.lot_en_cours()
    assert etat["etape"] == "fini" and "erreur" not in etat
    assert [l["case"] for l in a.lots_hors_ligne()["lots"]] == ["E5_N40"]
    assert [l["etat"] for l in a.catalogue_lots()["lots"]] == ["a_jour"]
    assert not list(a.hors_ligne.racine.glob(".telechargement-*")), "aucun reste du téléchargement"


def test_un_depot_injoignable_n_empeche_rien(tmp_path, monkeypatch):
    from hike2gpx import application as appli

    def refuser(demande, timeout):
        raise OSError("hors ligne")
    monkeypatch.setattr(depot.urllib.request, "urlopen", refuser)
    reponse = appli.Application(tmp_path / "donnees").catalogue_lots()
    assert reponse["lots"] == [] and "illisible" in reponse["erreur"]


@pytest.mark.zones_reelles
def test_la_planification_demande_la_zone_du_serveur_quand_aucune_n_est_la(tmp_path, monkeypatch):
    # Nico, 2026-11-13 : plus de téléchargement automatique ; « il suffit de laisser le
    # menu de planification disponible, mais avec une question sur le téléchargement si
    # aucune zone est là localement ».
    from hike2gpx import application as appli, geofabrik
    fabriquer_lot(tmp_path / "lots" / "E5_N40")
    depot.ecrire_catalogue(tmp_path / "lots", tmp_path / "publication")
    ouvrir, _ = servir(tmp_path / "publication")
    monkeypatch.setattr(depot.urllib.request, "urlopen", ouvrir)
    a = appli.Application(tmp_path / "donnees")
    zone = (43.30, 5.50, 43.31, 5.51)
    # Hors des cases du serveur (Montréal, Nico, 2026-11-13 : « j'ai pas le message de
    # création du lot par le pc ») : la page propose de fabriquer le lot ici, rien ne part seul ;
    # puis, ce lot en préparation, elle l'attend. La zone simple de brouter.de part d'abord :
    # sa taille pour la question ; sans elle (la mer, pas de réseau), rien à préparer.
    from hike2gpx import brouter
    monkeypatch.setattr(brouter, "taille_segment", lambda nom: None)
    assert a.zone_planification({"lat": 47.0, "lon": 2.0})["code"] == "brouter_absent"
    monkeypatch.setattr(brouter, "taille_segment", lambda nom: 120_000_000 if nom == "E0_N45" else None)
    assert a.zone_planification({"lat": 47.0, "lon": 2.0}) == {"fabriquer": {"case": "E0_N45", "octets": 120_000_000}}
    assert a._fil_lot is None
    a._lot = {"actif": True, "case": "E0_N45"}
    assert a.zone_planification({"lat": 47.0, "lon": 2.0}) == {"attendre": {"case": "E0_N45"}}
    a._lot = {"actif": False}
    # Une case publiée et absente : la page propose d'abord, et rien ne part seul.
    r = a.zone_planification({"lat": 43.305, "lon": 5.505})
    assert r["proposer"]["case"] == "E5_N40" and r["proposer"]["octets"] > 0
    assert a._fil_lot is None
    # Sans sa zone, pas de tracé (Nico, 2026-11-13 : « on avait dit qu'on bloquait la
    # planification, si pas de données ») : le calcul refuse, sans rien télécharger.
    trace = a.itineraire({"points": [[43.305, 5.505], [43.306, 5.506]], "comparer": False})
    assert trace["code"] == "zone_absente" and trace["valeurs"] == {"cases": "E5_N40"}
    assert a._fil_lot is None
    # Ni chemins superposés à la volée : ni extrait de toute la région, ni Overpass
    # (Nico, 2026-11-13 : « Supprimer » l'affichage à la volée).
    assert a.calque_osm(zone, vue=1.0)["code"] == "calques_sans_zone"
    assert a.calque_officiel("ign", zone, vue=1.0)["code"] == "calques_sans_zone"
    assert not geofabrik.installes(a.dossier), "aucun extrait parti"
    # Acceptée : la page la télécharge, puis s'ouvre.
    assert "lot_en_cours" in a.telecharger_lot({"case": "E5_N40"})
    a._fil_lot.join(10)
    assert a.lot_en_cours()["etape"] == "fini" and a.hors_ligne.origine("E5_N40") == {"depot": a.depot_lots}
    assert a.zone_planification({"lat": 43.305, "lon": 5.505}) == {"ouvrir": True}
    assert a._cases_sans_lot((43.305, 5.505, 43.306, 5.506)) == [], "la zone installée, le tracé passe"
    # Plus récent au serveur : un lot du dépôt est à renouveler (bouton « Mettre à jour »), un lot préparé ici non.
    a._catalogue[1]["lots"][0]["sources"] = {"osm": "2026-11-01T00:00:00Z"}
    assert [e["case"] for e in a._lots_a_telecharger(a._catalogue[1], zone)] == ["E5_N40"]
    (a.hors_ligne.racine / "E5_N40" / "origine.json").unlink()
    assert a._lots_a_telecharger(a._catalogue[1], zone) == []
    assert a.zone_planification({"lat": "nord", "lon": 5})["erreur"]


def _instant(texte):
    import calendar
    import time
    return calendar.timegm(time.strptime(texte, "%Y-%m-%dT%H:%M:%SZ"))


def _lot_osm(case, edition):
    return {"case": case, "sources": {"osm": edition}}


def test_la_fraicheur_signale_les_cases_absentes_et_les_lots_trop_vieux():
    contenu = {"lots": [_lot_osm("E0_N45", "2026-11-09T21:21:36Z"),       # 2 jours : frais
                        _lot_osm("E5_N45", "2026-10-20T21:21:36Z")]}      # 22 jours : trop vieux
    lignes, problemes = depot.fraicheur(contenu, ["E0_N45", "E10_N45"], _instant("2026-11-11T12:00:00Z"), 14)
    # Les cases du catalogue et celles attendues, triées ; une case absente n'a ni édition ni âge.
    assert [l[0] for l in lignes] == ["E0_N45", "E10_N45", "E5_N45"]
    assert round(lignes[0][2]) == 2 and lignes[1][1:] == (None, None)
    assert problemes == ["E10_N45 : absent du catalogue", "E5_N45 : lot de 22 jours (plus de 14)"]
    texte = depot.tableau_fraicheur(lignes, problemes, 14)
    assert "| E10_N45 | absent | |" in texte and "22 j (!)" in texte


def test_un_catalogue_frais_ne_signale_rien():
    lignes, problemes = depot.fraicheur({"lots": [_lot_osm("W5_N40", "2026-11-08T21:21:00Z")]},
                                        ["W5_N40"], _instant("2026-11-11T12:00:00Z"), 14)
    assert problemes == [] and len(lignes) == 1
    assert "Tous les lots ont moins de 14 jours." in depot.tableau_fraicheur(lignes, problemes, 14)


def test_une_edition_illisible_est_signalee_sans_passer_pour_absente():
    lignes, problemes = depot.fraicheur({"lots": [{"case": "E0_N40", "sources": {}}]}, [], 0.0, 14)
    assert lignes == [("E0_N40", "?", None)]
    assert problemes == ["E0_N40 : édition OSM illisible (None)"]
    assert "| E0_N40 | ? | ? (!) |" in depot.tableau_fraicheur(lignes, problemes, 14)


@pytest.mark.zones_reelles
def test_la_zone_simple_ouvre_la_planification_avant_la_zone_etendue(tmp_path, monkeypatch):
    # Nico, 2026-11-13 : « pour ne pas bloquer la planification, sur le pc on commence par la
    # zone simple brouter (vite téléchargée), et en parallèle, la zone étendue se calcule ».
    from hike2gpx import application as appli, fabrication
    a = appli.Application(tmp_path / "donnees")

    def telecharger(nom, vers=None):
        vers.mkdir(parents=True, exist_ok=True)
        (vers / f"{nom}.rd5").write_bytes(b"rd5 de brouter.de")
        return vers / f"{nom}.rd5"
    monkeypatch.setattr(a.installation, "telecharger_segment", telecharger)
    monkeypatch.setattr(a, "_arreter_moteurs", lambda: None)
    vu = {}

    def fabriquer(dossier, installation, case, sortie, **options):
        # La zone étendue commence : la zone simple est déjà là, la page a pu s'ouvrir.
        vu["simple"] = a.lot_en_cours().get("simple_installee")
        vu["couverte"] = a.hors_ligne.lot_couvrant((45.5, -73.6, 45.5, -73.6)) is not None
        raise fabrication.Abandon()            # « Arrêter »
    monkeypatch.setattr(fabrication, "fabriquer", fabriquer)
    assert "lot_en_cours" in a.preparer_lot({"case": "W75_N45", "simple": True})
    a._fil_lot.join(10)
    assert vu == {"simple": True, "couverte": True}
    assert a.lot_en_cours()["erreur"] == "Fabrication arrêtée."
    # Arrêtée, la zone étendue laisse la zone simple : le tracé passe, sans chemins dessinés
    # ni franchissements, et sans rien lire à la volée.
    zone = (45.50, -73.61, 45.51, -73.60)
    assert a._cases_sans_lot(zone) == []
    assert a.calque_osm(zone, vue=1.0)["code"] == "calques_zone_simple"
    manifeste = a.hors_ligne.lot_couvrant(zone)
    assert manifeste["sources"] == {"rd5": "brouter.de"}
    assert a.hors_ligne.franchissements(manifeste, zone) == []
