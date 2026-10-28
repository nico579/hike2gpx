import sqlite3
import struct
import xml.etree.ElementTree as ET
import zipfile

import pytest

from hike2gpx import bdot10k_powiaty as bp
from hike2gpx import en_bloc


def _index(powiats):
    membres = "".join(f"<wfs:member><ms:BDOT10k_powiaty><ms:TERYT>{t}</ms:TERYT>"
                      f"<ms:Data_aktualizacji>{d} 00:00:00</ms:Data_aktualizacji></ms:BDOT10k_powiaty></wfs:member>"
                      for t, d in powiats)
    return ET.fromstring('<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0" '
                         f'xmlns:ms="http://mapserver.gis.umn.edu/mapserver">{membres}</wfs:FeatureCollection>')


def test_les_powiats_de_basse_silesie_d_apres_l_index_officiel():
    demandes = []
    index = _index([("0212", "2023-10-23"), ("0201", "2024-02-27"), ("3005", "2024-01-01")])
    powiats = bp.powiats_de_zone(50, 15, 55, 20, lambda url: demandes.append(url) or index)
    assert powiats == [{"teryt": "0201", "date": "2024-02-27",
                        "url": "https://opendata.geoportal.gov.pl/bdot10k/schemat2021/GPKG/02/0201_GPKG.zip"},
                       {"teryt": "0212", "date": "2023-10-23",
                        "url": "https://opendata.geoportal.gov.pl/bdot10k/schemat2021/GPKG/02/0212_GPKG.zip"}], \
        "la Grande-Pologne (30) reste hors du périmètre de bdot10k_ds"
    assert "BBOX=50%2C15%2C55%2C20" in demandes[0]


def _skrp(chemin, voies):
    """Le GeoPackage OT_SKRP_L d'un powiat, de même structure que celui du
    GUGiK : voies = [(lokalny, rodzaj, existence, [(lat, lon), …])], en EPSG 2180."""
    import shapely
    from rasterio.warp import transform
    base = sqlite3.connect(chemin)
    base.execute(f'CREATE TABLE "{bp.TABLE}" (id INTEGER PRIMARY KEY, geometria BLOB, TERYT TEXT, LOKALNYID TEXT, '
                 'KATEGORIAISTNIENIA TEXT, RODZAJ TEXT, NAZWA TEXT)')
    base.execute(f'CREATE VIRTUAL TABLE "rtree_{bp.TABLE}_geometria" USING rtree(id, minx, maxx, miny, maxy)')
    for fid, (lokalny, rodzaj, existence, points) in enumerate(voies, 1):
        xs, ys = transform("EPSG:4326", "EPSG:2180", [lo for la, lo in points], [la for la, lo in points])
        ligne = shapely.LineString(list(zip(xs, ys)))
        blob = b"GP\x00\x03" + struct.pack("<i", 2180) + struct.pack("<4d", *ligne.bounds) + shapely.to_wkb(ligne)
        base.execute(f"INSERT INTO \"{bp.TABLE}\" VALUES (?, ?, '0201', ?, ?, ?, NULL)",
                     (fid, blob, lokalny, existence, rodzaj))
        x0, y0, x1, y1 = ligne.bounds
        base.execute(f'INSERT INTO "rtree_{bp.TABLE}_geometria" VALUES (?, ?, ?, ?, ?)', (fid, x0, x1, y0, y1))
    base.commit()
    base.close()


VOIES = [("S1", "ścieżka", "eksploatowany", [(51.250, 15.550), (51.251, 15.552)]),
         ("S2", "aleja lub pasaż", "eksploatowany", [(51.252, 15.553), (51.253, 15.554)]),
         ("S3", "ścieżka", "projektowany", [(51.254, 15.555), (51.255, 15.556)]),
         ("S4", "ścieżka", None, [(51.256, 15.557), (51.257, 15.558)])]


def test_le_lecteur_rend_les_sentiers_en_service(tmp_path, monkeypatch):
    gpkg = tmp_path / "source" / f"PL.PZGiK.337.BDOT10k.0201__{bp.TABLE}.gpkg"
    gpkg.parent.mkdir()
    _skrp(gpkg, VOIES)
    archive = tmp_path / "source" / "0201_GPKG.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(gpkg, gpkg.name)
        z.writestr("PL.PZGiK.337.BDOT10k.0201__OT_BUBD_A.gpkg", b"batiments" * 1000)
    telecharges = []

    def telecharger(fichier, cible, ouvrir=None, essais=3):
        telecharges.append(fichier["url"])
        cible.write_bytes(archive.read_bytes())
    monkeypatch.setattr(en_bloc, "telecharger", telecharger)
    monkeypatch.setattr(bp, "_taille", lambda url: archive.stat().st_size)
    powiat = {"teryt": "0201", "date": "2024-02-27", "url": "https://x/0201_GPKG.zip"}
    monkeypatch.setattr(bp, "powiats_de_zone", lambda *bornes: [powiat])
    racine = tmp_path / "donnees" / bp.DOSSIER
    racine.mkdir(parents=True)
    (racine / "0201_2023-01-01.sciezki.sqlite").write_bytes(b"ancienne")
    lecteur = bp.Lecteur(tmp_path / "donnees")
    lus = lecteur(51.24, 15.54, 51.26, 15.56)
    assert [(t["id"], t["nature"]) for t in lus] == [("S1:0", "ścieżka"), ("S4:0", "ścieżka")], \
        "ni l'allée, ni le sentier en projet"
    assert sum(lus[0]["pts"], []) == pytest.approx([51.250, 15.550, 51.251, 15.552], abs=1e-6)
    lecteur(51.24, 15.54, 51.26, 15.56)
    assert telecharges == ["https://x/0201_GPKG.zip"]
    assert lecteur.date(51.24, 15.54, 51.26, 15.56) == "2024-02-27"
    assert sorted(p.name for p in racine.iterdir()) == ["0201_2024-02-27.sciezki.sqlite"]


def test_la_basse_silesie_se_lit_en_bloc():
    from hike2gpx import fabrication
    assert "bdot10k_ds" in fabrication.EN_BLOC
    lecteurs, editions = fabrication.lecteurs_en_bloc("donnees")
    assert isinstance(lecteurs["bdot10k_ds"], bp.Lecteur) and editions["bdot10k_ds"] == lecteurs["bdot10k_ds"].date
