import io
import sqlite3
import struct
import xml.etree.ElementTree as ET
import zipfile

import pytest

from hike2gpx import en_bloc
from hike2gpx import zabaged_national as zn

NOM = "ZABAGED-3045-gpkg-20261004"
URL = f"https://openzu.cuzk.gov.cz/opendata/ZABAGED-GPKG/epsg-3045/{NOM}.zip"


def _flux():
    entree = ('<entry><link href="https://openzu.cuzk.gov.cz/opendata/ZABAGED-GPKG/epsg-{epsg}/'
              'ZABAGED-{epsg}-gpkg-20261004.zip" length="{octets}" rel="alternate"/></entry>')
    return ET.fromstring('<feed xmlns="http://www.w3.org/2005/Atom">'
                         + entree.format(epsg=5514, octets=5805826649)
                         + entree.format(epsg=3045, octets=6742892709) + "</feed>")


def test_l_edition_courante_en_tm33():
    edition = zn.derniere_edition(lambda url: _flux())
    assert edition == {"nom": NOM, "date": "2026-10-04",
                       "fichiers": [{"url": URL, "octets": 6742892709, "md5": None}]}, "EPSG 3045, pas S-JTSK"


def test_un_flux_sans_tm33_est_une_erreur():
    vide = ET.fromstring('<feed xmlns="http://www.w3.org/2005/Atom"></feed>')
    with pytest.raises(zn.ErreurArchive):
        zn.derniere_edition(lambda url: vide)


def _geopackage_zabaged(chemin, chemins):
    """Un GeoPackage de même structure que celui de l'ČÚZK pour les tables
    lues : chemins = {table: [(fid_zbg, [(lat, lon), …]), …]}, en EPSG 3045,
    plus une table que la réduction doit laisser."""
    import shapely
    from rasterio.warp import transform
    base = sqlite3.connect(chemin)
    base.execute("CREATE TABLE BudovaP (fid INTEGER PRIMARY KEY, donnees BLOB)")
    base.execute("INSERT INTO BudovaP VALUES (1, zeroblob(200000))")
    for table in zn.COUCHES:
        base.execute(f'CREATE TABLE "{table}" ({zn.CLE} INTEGER PRIMARY KEY, {zn.GEOMETRIE} BLOB, fid_zbg TEXT, '
                     f'jmeno TEXT)')
        base.execute(f'CREATE VIRTUAL TABLE "rtree_{table}_{zn.GEOMETRIE}" USING rtree(id, minx, maxx, miny, maxy)')
        for fid, (fid_zbg, points) in enumerate(chemins.get(table, []), 1):
            xs, ys = transform("EPSG:4326", "EPSG:3045", [lo for la, lo in points], [la for la, lo in points])
            ligne = shapely.MultiLineString([list(zip(xs, ys))])        # MULTILINESTRING, comme l'ČÚZK
            blob = b"GP\x00\x01" + struct.pack("<i", 3045) + shapely.to_wkb(ligne)
            base.execute(f'INSERT INTO "{table}" VALUES (?, ?, ?, NULL)', (fid, blob, fid_zbg))
            x0, y0, x1, y1 = ligne.bounds
            base.execute(f'INSERT INTO "rtree_{table}_{zn.GEOMETRIE}" VALUES (?, ?, ?, ?, ?)', (fid, x0, x1, y0, y1))
    base.commit()
    base.close()


CHEMINS = {"Pesina": [("PE1", [(49.120, 13.470), (49.121, 13.472)]),
                       ("PE2", [(49.300, 13.900), (49.301, 13.901)])],      # hors de l'emprise
           "Cesta": [("CE1", [(49.122, 13.473), (49.123, 13.474), (49.124, 13.476)])]}


@pytest.fixture
def archive(tmp_path):
    gpkg = tmp_path / "source" / "ZABAGED.gpkg"
    gpkg.parent.mkdir()
    _geopackage_zabaged(gpkg, CHEMINS)
    chemin = tmp_path / "source" / f"{NOM}.zip"
    with zipfile.ZipFile(chemin, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(gpkg, "ZABAGED/ZABAGED.gpkg")
        z.writestr("ZABAGED/lisezmoi.txt", "documentation")
    return chemin


def _edition(archive):
    return {"nom": NOM, "date": "2026-10-04", "fichiers": [{"url": URL, "octets": archive.stat().st_size, "md5": None}]}


def test_le_lecteur_rend_sentiers_et_chemins_de_l_emprise(tmp_path, archive, monkeypatch):
    telecharges = []

    def telecharger(fichier, cible, ouvrir=None, essais=3):
        telecharges.append(fichier["url"])
        cible.write_bytes(archive.read_bytes())
    monkeypatch.setattr(en_bloc, "telecharger", telecharger)
    monkeypatch.setattr(zn, "derniere_edition", lambda: _edition(archive))
    racine = tmp_path / "donnees" / zn.DOSSIER
    racine.mkdir(parents=True)
    (racine / "ZABAGED-3045-gpkg-20260704.chemins.sqlite").write_bytes(b"ancienne")
    lecteur = zn.Lecteur(tmp_path / "donnees")
    lus = lecteur(49.11, 13.46, 49.13, 13.48)
    assert [(t["id"], t["nature"]) for t in lus] == [("Pěšina:PE1:0", "Pěšina"), ("Cesta:CE1:0", "Cesta")]
    assert sum(lus[1]["pts"], []) == pytest.approx([49.122, 13.473, 49.123, 13.474, 49.124, 13.476], abs=1e-6)
    lecteur(49.29, 13.89, 49.31, 13.91)
    assert telecharges == [URL], "une seule fois pour la case"
    assert lecteur.date(49.11, 13.46, 49.13, 13.48) == "2026-10-04"
    restes = sorted(p.name for p in racine.iterdir())
    assert restes == [f"{NOM}.chemins.sqlite"], "ni l'archive, ni le GeoPackage complet, ni l'ancienne édition"
    with sqlite3.connect(racine / restes[0]) as base:
        tables = {n for (n,) in base.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "BudovaP" not in tables and set(zn.COUCHES) <= tables


def test_une_archive_alteree_est_refusee(tmp_path, archive):
    abimee = tmp_path / "abimee.zip"
    donnees = bytearray(archive.read_bytes())
    milieu = len(donnees) // 3
    donnees[milieu:milieu + 64] = bytes(64)
    abimee.write_bytes(bytes(donnees))
    with pytest.raises(zn.ErreurArchive):
        zn._extraire(abimee, tmp_path / "extrait")


class Reponse(io.BytesIO):
    def __init__(self, donnees, status=200, coupure=None):
        super().__init__(donnees)
        self.status, self.coupure = status, coupure

    def read(self, n=-1):
        bloc = super().read(n)
        if not bloc and self.coupure:
            raise self.coupure
        return bloc

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_les_coupures_qui_avancent_ne_comptent_pas(tmp_path):
    # Le serveur de l'ČÚZK coupe parfois : cinq coupures, chacune après un
    # morceau, ne doivent pas épuiser trois essais.
    contenu = b"zip de ZABAGED" * 1000
    demandes = []

    def ouvrir(demande, timeout):
        rang = len(demandes)
        demandes.append(demande.get_header("Range"))
        return Reponse(morceaux[rang], 206 if rang else 200,
                       OSError("coupure") if rang < 5 else None)
    morceaux = [contenu[:2000], contenu[2000:4000], contenu[4000:6000], contenu[6000:8000], contenu[8000:10000],
                contenu[10000:]]
    cible = tmp_path / "z.zip"
    en_bloc.telecharger({"url": URL, "octets": len(contenu), "md5": None}, cible, ouvrir)
    assert cible.read_bytes() == contenu and demandes[1] == "bytes=2000-" and len(demandes) == 6


def test_sans_progres_le_telechargement_abandonne(tmp_path):
    def ouvrir(demande, timeout):
        raise OSError("refusé")
    with pytest.raises(en_bloc.ErreurArchive):
        en_bloc.telecharger({"url": URL, "octets": 10, "md5": None}, tmp_path / "z.zip", ouvrir)


def test_zabaged_se_lit_en_bloc():
    from hike2gpx import fabrication
    assert "zabaged" in fabrication.EN_BLOC
    lecteurs, editions = fabrication.lecteurs_en_bloc("donnees")
    assert isinstance(lecteurs["zabaged"], zn.Lecteur) and editions["zabaged"] == lecteurs["zabaged"].date
