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
