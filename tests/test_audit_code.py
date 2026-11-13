"""Les constats de l'audit du code du 2026-11-13 (rapports/audit-code-2026-11-13),
un essai par constat corrigé, sur le cas même que l'audit avait reproduit."""
import gzip
import io
import json
import xml.etree.ElementTree as ET

import pytest

from hike2gpx import application as appli, atkis_laender as al, en_bloc, fabrication, geofabrik, hors_ligne, lot
from hike2gpx import zabaged_national as zn


def test_a01_un_nom_de_fichier_qui_sort_du_lot_est_refuse(tmp_path):
    # Le contrôle lisait le nom nettoyé, la copie le nom brut : « ../x » écrivait hors du lot.
    source = tmp_path / "source"
    source.mkdir()
    (source / "E5_N40.rd5").write_bytes(b"rd5")
    (tmp_path / "evil.bin").write_bytes(b"dehors")
    (source / "evil.bin").write_bytes(b"dedans")
    lot.ecrire_manifeste(source, "E5_N40", [source / "E5_N40.rd5", source / "evil.bin"], {"rd5": "brouter.de"},
                         type="osm", zone=[40.0, 5.0, 45.0, 10.0])
    manifeste = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    manifeste["fichiers"][1]["nom"] = "../evil.bin"
    (source / "manifest.json").write_text(json.dumps(manifeste), encoding="utf-8")
    h = hors_ligne.HorsLigne(tmp_path / "donnees")
    with pytest.raises(hors_ligne.ErreurLot, match="Nom de fichier invalide"):
        h.installer(source)
    assert not (h.racine / "evil.bin").exists() and not (tmp_path / "donnees" / "evil.bin").exists()
    for nom in ("C:\\evil.bin", "/evil.bin", "sous/evil.bin", ".."):
        manifeste["fichiers"][1]["nom"] = nom
        (source / "manifest.json").write_text(json.dumps(manifeste), encoding="utf-8")
        with pytest.raises(hors_ligne.ErreurLot):
            h.installer(source)


def test_a02_un_etat_brouter_vide_par_son_fil_ne_fait_pas_planter(tmp_path):
    # Le fil vide l'état dans son finally, encore vivant pour un instant : KeyError('segments').
    a = appli.Application(tmp_path)
    a._fil_brouter = type("Fil", (), {"is_alive": lambda self: True})()
    a._brouter_en_cours = {}
    assert a._brouter_automatique(["E5_N40"]) == {"moteur": False, "segments": []}


def test_a03_a04_une_taille_inconnue_est_une_erreur_claire(tmp_path):
    # 0 passait pour un fichier vide, puis le contrôle final levait FileNotFoundError.
    with pytest.raises(en_bloc.ErreurArchive, match="taille inconnue"):
        en_bloc.telecharger({"url": "https://exemple/a.gpkg", "octets": 0, "md5": None}, tmp_path / "a.gpkg")
    assert not (tmp_path / "a.gpkg").exists()

    class Reponse(io.BytesIO):
        def __init__(self, entetes):
            super().__init__(b"")
            self.headers = entetes

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False
    with pytest.raises(en_bloc.ErreurArchive, match="Content-Length"):
        en_bloc.taille("https://exemple/a.gpkg", ouvrir=lambda demande, timeout: Reponse({}))
    assert en_bloc.taille("https://exemple/a.gpkg", ouvrir=lambda demande, timeout: Reponse(
        {"Content-Length": "1234"})) == 1234


def test_a05_une_action_absente_n_est_pas_une_erreur_500(tmp_path):
    a = appli.Application(tmp_path)
    assert a.agir_donnees({}) == {"erreur": "Action inconnue."}
    assert a.agir_donnees({"action": 3}) == {"erreur": "Action inconnue."}


def test_a06_zabaged_prend_l_edition_la_plus_recente_et_demande_sa_taille():
    # Rien ne garantit l'ordre du flux : la première entrée n'est pas la plus récente.
    entree = ('<entry><link href="https://openzu.cuzk.gov.cz/opendata/ZABAGED-GPKG/epsg-3045/'
              'ZABAGED-3045-gpkg-{date}.zip"{longueur} rel="alternate"/></entry>')
    flux = ET.fromstring('<feed xmlns="http://www.w3.org/2005/Atom">'
                         + entree.format(date="20240101", longueur=' length="5"')
                         + entree.format(date="20261004", longueur="") + "</feed>")
    demandees = []
    edition = zn.derniere_edition(lambda url: flux, taille=lambda url: demandees.append(url) or 6742892709)
    assert edition["date"] == "2026-10-04" and edition["nom"] == "ZABAGED-3045-gpkg-20261004"
    assert edition["fichiers"][0]["octets"] == 6742892709 and demandees == [edition["fichiers"][0]["url"]], \
        "sans attribut length, la taille se demande au serveur"


def test_a07_des_franchissements_illisibles_ne_passent_pas_pour_aucune_barriere(tmp_path):
    h = hors_ligne.HorsLigne(tmp_path)
    (h.racine / "E5_N40").mkdir(parents=True)
    (h.racine / "E5_N40" / "franchissements.json.gz").write_bytes(b"pas du gzip")
    with pytest.raises(hors_ligne.ErreurLot, match="illisibles"):
        h.franchissements({"case": "E5_N40"}, (43.0, 5.0, 44.0, 6.0))
    with gzip.open(h.racine / "E5_N40" / "franchissements.json.gz", "wt", encoding="utf-8") as f:
        f.write("{tronqué")
    with pytest.raises(hors_ligne.ErreurLot):
        h.franchissements({"case": "E5_N40"}, (43.0, 5.0, 44.0, 6.0))


def test_a08_un_troncon_frontalier_des_laender_n_est_lu_qu_une_fois(tmp_path, monkeypatch):
    klasse = next(iter(al.CLASSES))
    monkeypatch.setattr(en_bloc, "lignes_gpkg",
                        lambda base, *args, **options: [(("DEBE-W1", 0, klasse), 0, [[52.5, 13.3], [52.6, 13.4]])])
    lecteur = al.Lecteur(tmp_path)
    monkeypatch.setattr(lecteur, "preparer", lambda *zone: None)
    monkeypatch.setattr(lecteur, "laender", lambda *zone: ["BE", "BB"])
    lecteur._bases = {"BE": "be.sqlite", "BB": "bb.sqlite"}
    lus = lecteur(52.4, 13.2, 52.7, 13.5)
    assert [t["id"] for t in lus] == ["DLM:BE:DEBE-W1:0"]


def test_a09_un_lot_fait_sans_osm_est_a_jour_sans_extrait(tmp_path):
    (tmp_path / "E5_N40.rd5").write_bytes(b"rd5")
    lot.ecrire_manifeste(tmp_path, "E5_N40", [tmp_path / "E5_N40.rd5"], {"osm": None}, type="osm")
    assert fabrication.lot_a_jour(tmp_path, osm=None), "il se refaisait à chaque passage"
    lot.ecrire_manifeste(tmp_path, "E5_N40", [tmp_path / "E5_N40.rd5"], {"osm": "2026-10-25T21:21:21Z"}, type="osm")
    assert not fabrication.lot_a_jour(tmp_path, osm=None), "un lot avec OSM, face à des extraits inconnus : à refaire"


def test_a10_un_extrait_disparu_ne_fait_pas_echouer_la_section(tmp_path, monkeypatch):
    disparu = {"id": "paca", "nom": "PACA", "date": "2026-10-18T20:25:06Z", "base": tmp_path / "absent.sqlite"}
    monkeypatch.setattr(geofabrik, "installes", lambda dossier: [disparu])
    assert appli.Application(tmp_path).donnees()["extraits"] == []


def test_a12_les_manifestes_ne_se_relisent_que_s_ils_changent(tmp_path, monkeypatch):
    h = hors_ligne.HorsLigne(tmp_path)
    (h.racine / "E5_N40").mkdir(parents=True)
    manifeste = h.racine / "E5_N40" / "manifest.json"
    manifeste.write_text(json.dumps({"case": "E5_N40", "format": 3}), encoding="utf-8")
    lus = []
    charger = json.loads
    monkeypatch.setattr(hors_ligne.json, "loads", lambda texte: lus.append(1) or charger(texte))
    assert [m["case"] for m in h.lots()] == ["E5_N40"]
    h.lots()[0]["case"] = "abîmé"           # une copie : le cache ne s'abîme pas
    assert h.lots()[0]["case"] == "E5_N40" and len(lus) == 1
    manifeste.write_text(json.dumps({"case": "E5_N40", "format": 3, "zone": [1, 2, 3, 4]}), encoding="utf-8")
    assert h.lots()[0]["zone"] == [1, 2, 3, 4] and len(lus) == 2, "un manifeste changé se relit"
