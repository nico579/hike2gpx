import hashlib
import io
import xml.etree.ElementTree as ET

import pytest

from hike2gpx import bdtopo_regions as br

NOM = "BDTOPO_3-5_TOUSTHEMES_GPKG_LAMB93_R93_2026-09-15"
CONTENU = b"archive 7z de la BD TOPO" * 1000


def _flux(titres):
    entrees = "".join(f"<entry><title>{t}</title></entry>" for t in titres)
    return ET.fromstring(f'<feed xmlns="http://www.w3.org/2005/Atom">{entrees}</feed>')


def _fichiers(nom, md5):
    url = f"{br.TELECHARGEMENT}{nom}/{nom}.7z"
    return ET.fromstring(
        f'<feed xmlns="http://www.w3.org/2005/Atom" xmlns:gpf="https://data.geopf.fr/annexes/ressources/xsd/gpf_dl.xsd">'
        f'<entry><link rel="alternate" href="{url}" gpf:length="{len(CONTENU)}"/><content>{md5}</content></entry>'
        f'</feed>')


def test_la_derniere_edition_de_la_region():
    md5 = hashlib.md5(CONTENU).hexdigest()

    def lire(url):
        if "zone=R93" in url:
            return _flux([NOM.replace("2026-09-15", "2026-06-15"), NOM, "BDTOPO_3-5_TOUSTHEMES_SHP_LAMB93_R93_2026-12-15"])
        return _fichiers(NOM, md5)
    edition = br.derniere_edition("R93", lire)
    assert edition["nom"] == NOM and edition["date"] == "2026-09-15", "le GeoPackage le plus récent, pas le Shapefile"
    assert edition["fichiers"] == [{"url": f"{br.TELECHARGEMENT}{NOM}/{NOM}.7z", "octets": len(CONTENU), "md5": md5}]


class Reponse(io.BytesIO):
    def __init__(self, donnees, status=200):
        super().__init__(donnees)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_un_telechargement_coupe_reprend_ou_il_s_est_arrete(tmp_path):
    cible = tmp_path / "a.7z"
    cible.write_bytes(CONTENU[:5000])          # ce qu'une coupure a laissé
    demandes = []

    def ouvrir(demande, timeout):
        demandes.append(demande.get_header("Range"))
        return Reponse(CONTENU[5000:], 206)
    br._telecharger({"url": "https://x/a.7z", "octets": len(CONTENU), "md5": hashlib.md5(CONTENU).hexdigest()},
                    cible, ouvrir)
    assert demandes == ["bytes=5000-"] and cible.read_bytes() == CONTENU


def test_des_coupures_qui_avancent_ne_font_pas_abandonner(tmp_path):
    # Essai GitHub Actions du 2026-10-28 : R93 et R44, plusieurs Go, abandonnées
    # après trois coupures ; une fermeture propre avant la fin effaçait tout.
    morceaux = [CONTENU[i:i + 3000] for i in range(0, len(CONTENU), 3000)]
    pauses = []

    def ouvrir(demande, timeout):
        plage = demande.get_header("Range")
        debut = int(plage[6:-1]) if plage else 0
        morceau = next(m for i, m in enumerate(morceaux) if i * 3000 == debut)
        if len(pauses) % 2:
            raise ConnectionResetError("coupure")      # une coupure sans le moindre octet
        return Reponse(morceau, 206 if plage else 200)  # fermée proprement après un morceau
    br._telecharger({"url": "https://x/a.7z", "octets": len(CONTENU), "md5": hashlib.md5(CONTENU).hexdigest()},
                    tmp_path / "a.7z", ouvrir, pauses.append)
    assert (tmp_path / "a.7z").read_bytes() == CONTENU
    assert len(pauses) > br.ECHECS_MAX, "bien plus de coupures que d'échecs admis, toutes reprises"


def test_un_fichier_altere_est_refuse(tmp_path):
    with pytest.raises(br.ErreurArchive, match="altéré"):
        br._telecharger({"url": "https://x/a.7z", "octets": len(CONTENU), "md5": "0" * 32}, tmp_path / "a.7z",
                        lambda demande, timeout: Reponse(CONTENU))


def test_le_lecteur_cherche_les_regions_une_fois_par_case(tmp_path, monkeypatch):
    appels = []
    monkeypatch.setattr(br, "regions_de_zone", lambda *bornes: appels.append(bornes) or ["R84", "R93"])
    monkeypatch.setattr(br, "derniere_edition",
                        lambda region: {"nom": region, "date": {"R84": "2026-06-15", "R93": "2026-09-15"}[region]})
    monkeypatch.setattr(br, "geopackage", lambda dossier, region, edition: f"{region}.gpkg")
    from hike2gpx import case
    # Un tronçon qui passe la limite des deux régions est dans les deux archives.
    lus = {"R84.gpkg": [{"id": "T-1-0"}, {"id": "T-2-0"}], "R93.gpkg": [{"id": "T-2-0"}, {"id": "T-3-0"}]}
    monkeypatch.setattr(case, "troncons_gpkg", lambda gpkg, *bornes: lus[gpkg])
    lecteur = br.Lecteur(tmp_path)
    assert [t["id"] for t in lecteur(43.25, 6.0, 43.5, 6.25)] == ["T-1-0", "T-2-0", "T-3-0"]
    lecteur(43.5, 6.0, 43.75, 6.25)
    lecteur(39.999, 4.999, 40.251, 5.251)      # une emprise qui déborde au sud-ouest reste dans la case
    assert appels == [(40.0, 5.0, 45.0, 10.0)], "une seule recherche des régions pour la case"
    assert lecteur.date(43.25, 6.0, 43.5, 6.25) == "2026-09-15", "l'édition la plus récente des régions"


def test_la_commande_refuse_deux_lectures_ign():
    from hike2gpx.__main__ import main
    with pytest.raises(SystemExit):
        main(["bundles", "E5_N40", "--output", "lots", "--gpkg", "a.gpkg", "--bulk"])
    with pytest.raises(SystemExit):
        main(["bundles", "E5_N40", "--output", "lots", "--osm-only", "--bulk"])


def test_seuls_les_troncons_sont_gardes_et_rendent_la_meme_chose(tmp_path):
    # Essai GitHub Actions : une case touchant cinq régions (E0_N45) remplissait
    # le disque avec des GeoPackage « tous thèmes » entiers.
    import sqlite3
    from hike2gpx import case
    from test_case import _geopackage_bdtopo
    complet = tmp_path / "complet.gpkg"
    _geopackage_bdtopo(complet, [("TRONROUT1", "83063", [[(43.330, 6.040), (43.331, 6.042)]]),
                                 ("TRONROUT2", "06088", [[(43.332, 6.043), (43.333, 6.044)]])])
    with sqlite3.connect(complet) as base:          # une autre table du « tous thèmes »
        base.execute("CREATE TABLE batiment (fid INTEGER PRIMARY KEY, donnees BLOB)")
        base.execute("INSERT INTO batiment VALUES (1, zeroblob(200000))")
    br._garder_les_troncons(complet, tmp_path / "troncons.sqlite")
    bornes = (43.32, 6.03, 43.34, 6.05)
    assert case.troncons_gpkg(tmp_path / "troncons.sqlite", *bornes) == case.troncons_gpkg(complet, *bornes)
    assert case.troncons_gpkg(tmp_path / "troncons.sqlite", *bornes, "83")[0]["id"] == "TRONROUT1-0"
    with sqlite3.connect(tmp_path / "troncons.sqlite") as base:
        tables = {n for (n,) in base.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "batiment" not in tables
    assert (tmp_path / "troncons.sqlite").stat().st_size < complet.stat().st_size / 4


def test_une_region_deja_gardee_n_est_pas_retelechargee(tmp_path, monkeypatch):
    racine = tmp_path / "bdtopo-regions"
    racine.mkdir()
    (racine / f"{NOM}.troncons.sqlite").write_bytes(b"base")
    monkeypatch.setattr(br, "_telecharger", lambda *a: pytest.fail("rien à télécharger"))
    assert br.geopackage(tmp_path, "R93", {"nom": NOM, "date": "2026-09-15", "fichiers": []}).name == \
        f"{NOM}.troncons.sqlite"
