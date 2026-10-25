"""Lecture locale de la BD TOPO avec géométries 3D et index spatial."""
import sqlite3
import struct
import tempfile
from contextlib import closing
from pathlib import Path

from pyproj import Transformer
from shapely import LineString, to_wkb

from hike2gpx.providers import bdtopo


def test_troncons_gpkg_reprojette_et_respecte_emprise():
    with tempfile.TemporaryDirectory() as racine:
        gpkg = Path(racine) / "bdtopo.gpkg"
        proj = Transformer.from_crs(4326, 2154, always_xy=True)
        a = proj.transform(6.04, 43.32)
        b = proj.transform(6.041, 43.321)
        geometrie = to_wkb(LineString([(a[0], a[1], 100), (b[0], b[1], 101)]))
        blob = b"GP\x00\x01" + struct.pack("<I", 2154) + geometrie
        with closing(sqlite3.connect(gpkg)) as base:
            base.execute("CREATE TABLE troncon_de_route (fid INTEGER PRIMARY KEY, cleabs TEXT, "
                         "nature TEXT, acces_pieton TEXT, acces_vehicule_leger TEXT, "
                         "prive INTEGER, geometrie BLOB)")
            base.execute("CREATE VIRTUAL TABLE rtree_troncon_de_route_geometrie USING "
                         "rtree(id, minx, maxx, miny, maxy)")
            base.execute("INSERT INTO troncon_de_route VALUES (1, 'BDT1', 'Sentier', 'Libre', "
                         "NULL, 0, ?)", (blob,))
            base.execute("INSERT INTO rtree_troncon_de_route_geometrie VALUES (1, ?, ?, ?, ?)",
                         (min(a[0], b[0]), max(a[0], b[0]), min(a[1], b[1]), max(a[1], b[1])))
            base.commit()
        troncons = bdtopo.troncons_gpkg(gpkg, 43.25, 6.0, 43.5, 6.25)
        assert len(troncons) == 1
        assert troncons[0]["id"] == "BDT1-0"
        assert troncons[0]["pts"] == [[43.32, 6.04], [43.321, 6.041]]
        assert bdtopo.troncons_gpkg(gpkg, 44.0, 6.0, 44.25, 6.25) == []
