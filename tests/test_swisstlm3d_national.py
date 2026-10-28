import hashlib
import sqlite3
import struct
import zipfile

import pytest

from hike2gpx import en_bloc
from hike2gpx import swisstlm3d_national as sn

BASE = "https://data.geo.admin.ch/ch.swisstopo.swisstlm3d"


def _item(edition, formats):
    return {"id": f"swisstlm3d_{edition}", "properties": {"datetime": f"{edition}-01T00:00:00Z"},
            "assets": {f"swisstlm3d_{edition}_2056_5728.{f}.zip":
                       {"href": f"{BASE}/swisstlm3d_{edition}/swisstlm3d_{edition}_2056_5728.{f}.zip",
                        "checksum:multihash": "1220" + "AB" * 32} for f in formats}}


def test_la_derniere_edition_en_geopackage():
    catalogue = {"features": [_item("2025-03", ["gdb", "gpkg"]), _item("2026-02", ["gdb", "gpkg", "shp"]),
                              _item("2026-09", ["gdb"])]}
    edition = sn.derniere_edition(lambda url: catalogue)
    assert edition == {"nom": "swisstlm3d_2026-02_2056_5728", "date": "2026-02-01",
                       "fichiers": [{"url": f"{BASE}/swisstlm3d_2026-02/swisstlm3d_2026-02_2056_5728.gpkg.zip",
                                     "octets": None, "sha256": "ab" * 32}]}, \
        "la plus récente qui a un GeoPackage, pas une géodatabase seule"


def _geopackage_tlm(chemin, routes):
    """Un GeoPackage de même structure que celui de swisstopo pour la table
    lue : routes = [(uuid, objektart, verkehrsbeschraenkung, [(lat, lon), …])],
    en EPSG 2056."""
    import shapely
    from rasterio.warp import transform
    base = sqlite3.connect(chemin)
    base.execute(f'CREATE TABLE "{sn.TABLE}" (id INTEGER PRIMARY KEY, geom BLOB, uuid TEXT, objektart TEXT, '
                 'wanderwege TEXT, verkehrsbeschraenkung TEXT)')
    base.execute(f'CREATE VIRTUAL TABLE "rtree_{sn.TABLE}_geom" USING rtree(id, minx, maxx, miny, maxy)')
    for fid, (uuid, objektart, restriction, points) in enumerate(routes, 1):
        xs, ys = transform("EPSG:4326", "EPSG:2056", [lo for la, lo in points], [la for la, lo in points])
        ligne = shapely.LineString(list(zip(xs, ys)))
        blob = b"GP\x00\x01" + struct.pack("<i", 2056) + shapely.to_wkb(ligne)
        base.execute(f'INSERT INTO "{sn.TABLE}" VALUES (?, ?, ?, ?, NULL, ?)', (fid, blob, uuid, objektart, restriction))
        x0, y0, x1, y1 = ligne.bounds
        base.execute(f'INSERT INTO "rtree_{sn.TABLE}_geom" VALUES (?, ?, ?, ?, ?)', (fid, x0, x1, y0, y1))
    base.commit()
    base.close()


ROUTES = [("{A}", "1m Weg", "Keine", [(46.200, 8.700), (46.201, 8.702)]),
          ("{B}", "4m Strasse", "Keine", [(46.202, 8.703), (46.203, 8.704)]),
          ("{C}", "2m Weg", "Allgemeine Verkehrsbeschraenkung", [(46.204, 8.705), (46.205, 8.706)]),
          ("{D}", "2m Wegfragment", "Keine", [(46.206, 8.707), (46.207, 8.708)])]


def test_le_lecteur_rend_les_chemins_sans_restriction(tmp_path, monkeypatch):
    gpkg = tmp_path / "source" / "SWISSTLM3D_2026_LV95_LN02.gpkg"
    gpkg.parent.mkdir()
    _geopackage_tlm(gpkg, ROUTES)
    archive = tmp_path / "source" / "swisstlm3d_2026-02_2056_5728.gpkg.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(gpkg, gpkg.name)
    contenu = archive.read_bytes()
    edition = {"nom": "swisstlm3d_2026-02_2056_5728", "date": "2026-02-24",
               "fichiers": [{"url": "https://x/t.gpkg.zip", "octets": None,
                             "sha256": hashlib.sha256(contenu).hexdigest()}]}
    telecharges = []

    def telecharger(fichier, cible, ouvrir=None, essais=3):
        telecharges.append(fichier)
        cible.write_bytes(contenu)
    monkeypatch.setattr(en_bloc, "telecharger", telecharger)
    monkeypatch.setattr(sn, "_taille", lambda url: len(contenu))
    monkeypatch.setattr(sn, "derniere_edition", lambda: edition)
    lecteur = sn.Lecteur(tmp_path / "donnees")
    lus = lecteur(46.19, 8.69, 46.21, 8.71)
    assert [(t["id"], t["nature"]) for t in lus] == [("{A}:0", "Weg 16"), ("{D}:0", "Weg 18")], \
        "ni la route, ni le chemin à circulation restreinte"
    assert sum(lus[0]["pts"], []) == pytest.approx([46.200, 8.700, 46.201, 8.702], abs=1e-6)
    assert telecharges[0]["octets"] == len(contenu), "la taille demandée au serveur, le catalogue ne la donne pas"
    assert lecteur.date(46.19, 8.69, 46.21, 8.71) == "2026-02-24"
    racine = tmp_path / "donnees" / sn.DOSSIER
    assert sorted(p.name for p in racine.iterdir()) == ["swisstlm3d_2026-02_2056_5728.chemins.sqlite"]
    with sqlite3.connect(racine / "swisstlm3d_2026-02_2056_5728.chemins.sqlite") as base:
        assert base.execute(f'SELECT count(*) FROM "rtree_{sn.TABLE}_geom"').fetchone() == (2,), \
            "l'index ne garde que les chemins retenus"


class Reponse:
    def __init__(self, donnees):
        self.donnees, self.status = donnees, 200

    def read(self, n=-1):
        bloc, self.donnees = self.donnees, b""
        return bloc

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_le_sha256_du_catalogue_controle_le_telechargement(tmp_path):
    contenu = b"archive swissTLM3D" * 100
    fichier = {"url": "https://x/t.zip", "octets": len(contenu), "sha256": hashlib.sha256(contenu).hexdigest()}
    en_bloc.telecharger(fichier, tmp_path / "bon.zip", lambda demande, timeout: Reponse(contenu))
    assert (tmp_path / "bon.zip").read_bytes() == contenu
    with pytest.raises(en_bloc.ErreurArchive):
        en_bloc.telecharger({**fichier, "sha256": "0" * 64}, tmp_path / "faux.zip",
                            lambda demande, timeout: Reponse(contenu))


def test_swisstlm3d_se_lit_en_bloc():
    from hike2gpx import fabrication
    assert "swisstlm3d" in fabrication.EN_BLOC
    lecteurs, editions = fabrication.lecteurs_en_bloc("donnees")
    assert isinstance(lecteurs["swisstlm3d"], sn.Lecteur) and editions["swisstlm3d"] == lecteurs["swisstlm3d"].date
