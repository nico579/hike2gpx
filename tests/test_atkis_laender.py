import sqlite3
import struct

from hike2gpx import atkis_laender as al
from hike2gpx import en_bloc

LISTE = ('<a href="basisviews_bdlm_BE_EPSG4326_2026-11-08.gpkg">x</a>'
         '<a href="basisviews_bdlm_BE_EPSG4326_2026-11-09.gpkg">x</a>'
         '<a href="basisviews_bdlm_BY_EPSG4326_2026-11-09.gpkg">x</a>'
         '<a href="basisviews_bdlm_XX_EPSG4326_2026-11-09.gpkg">x</a>'
         '<a href="autre.gpkg">x</a>')
VOIES = [  # (id, klasse, ebene, points en lon, lat)
    ("W1", "Fußweg", 0, [(13.36, 52.51), (13.37, 52.512)]),
    ("W2", "Wirtschaftsweg", 1, [(13.38, 52.505), (13.385, 52.506), (13.39, 52.507)]),
    ("S1", "Gemeindestraße", 0, [(13.36, 52.515), (13.37, 52.515)]),
    ("W3", "Weg, Pfad, Steig", 0, [(13.70, 52.40), (13.71, 52.41)]),     # hors de l'emprise
]


def _gpkg(chemin):
    def blob(points):
        wkb = struct.pack("<BII", 1, 2, len(points)) + b"".join(struct.pack("<dd", x, y) for x, y in points)
        return b"GP\x00\x01" + struct.pack("<i", 4326) + wkb
    with sqlite3.connect(chemin) as base:
        base.execute("CREATE TABLE verkehrslinie_bdlm (fid INTEGER PRIMARY KEY, geom BLOB, id TEXT, land TEXT, "
                     "objektart TEXT, klasse TEXT, ebene MEDIUMINT)")
        base.execute("CREATE VIRTUAL TABLE rtree_verkehrslinie_bdlm_geom USING rtree(id, minx, maxx, miny, maxy)")
        for fid, (identifiant, klasse, ebene, points) in enumerate(VOIES, 1):
            base.execute("INSERT INTO verkehrslinie_bdlm VALUES (?, ?, ?, 'BE', 'x', ?, ?)",
                         (fid, blob(points), identifiant, klasse, ebene))
            xs, ys = [p[0] for p in points], [p[1] for p in points]
            base.execute("INSERT INTO rtree_verkehrslinie_bdlm_geom VALUES (?, ?, ?, ?, ?)",
                         (fid, min(xs), max(xs), min(ys), max(ys)))


def test_le_fichier_le_plus_recent_de_chaque_land():
    assert al.fichiers(lire=lambda url: LISTE) == {
        "BE": {"date": "2026-11-09", "url": al.LISTE + "basisviews_bdlm_BE_EPSG4326_2026-11-09.gpkg"},
        "BY": {"date": "2026-11-09", "url": al.LISTE + "basisviews_bdlm_BY_EPSG4326_2026-11-09.gpkg"},
    }


def test_les_laender_d_une_case():
    assert al.laender_de_zone(52.4, 13.3, 52.6, 13.5) == ["BB", "BE"]
    assert "SN" in al.laender_de_zone(50, 10, 55, 15) and "BW" not in al.laender_de_zone(50, 10, 55, 15)
    assert al.laender_de_zone(43, 5, 44, 6) == [], "la Provence n'est pas allemande"


def test_le_lecteur_rend_les_chemins_du_land(tmp_path, monkeypatch):
    source = tmp_path / "source.gpkg"
    _gpkg(source)
    telecharges = []

    def telecharger(fichier, cible, ouvrir=None, essais=3, plages=1):
        telecharges.append((fichier["url"], plages))
        cible.write_bytes(source.read_bytes())
    monkeypatch.setattr(en_bloc, "telecharger", telecharger)
    monkeypatch.setattr(al, "fichiers", lambda: {"BE": {"date": "2026-11-09", "url": "https://x/BE.gpkg"}})
    racine = tmp_path / "donnees" / al.DOSSIER
    racine.mkdir(parents=True)
    (racine / "BE_2026-11-01.chemins.sqlite").write_bytes(b"ancienne")
    monkeypatch.setattr(al, "_taille", lambda url: source.stat().st_size)
    lecteur = al.Lecteur(tmp_path / "donnees")
    lus = lecteur(52.50, 13.35, 52.52, 13.40)
    assert sorted((t["id"], t["nature"], t["land"], t["niveau"]) for t in lus) == [
        ("DLM:BE:W1:0", "Weg/Pfad/Steig", "BE", 0), ("DLM:BE:W2:0", "Wirtschaftsweg", "BE", 1)], \
        "ni la rue, ni le sentier hors de l'emprise"
    w2 = next(t for t in lus if t["id"] == "DLM:BE:W2:0")
    assert w2["pts"][0][0] == 52.505 and w2["pts"][0][1] == 13.38 and "bords" not in w2
    lecteur(52.50, 13.35, 52.52, 13.40)
    assert telecharges == [("https://x/BE.gpkg", al.PLAGES)]
    assert lecteur.date(52.5, 13.35, 52.52, 13.4) == "2026-11-09"
    assert sorted(p.name for p in racine.iterdir()) == ["BE_2026-11-09.chemins.sqlite"]


def test_l_allemagne_se_lit_en_bloc():
    from hike2gpx import fabrication
    assert "atkis" in fabrication.EN_BLOC
    lecteurs, _ = fabrication.lecteurs_en_bloc("donnees")
    assert isinstance(lecteurs["atkis"], al.Lecteur) and hasattr(lecteurs["atkis"], "preparer")
