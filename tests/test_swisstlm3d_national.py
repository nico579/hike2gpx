import zipfile

import pytest
import shapefile

from hike2gpx import en_bloc
from hike2gpx import swisstlm3d_national as sn

URL = "https://data.geo.admin.ch/ch.swisstopo.swisstlm3d/swisstlm3d_2026-02/swisstlm3d_2026-02_2056_5728.shp.zip"
# Près de Locarno, en LV95 : (E, N) autour de 2 695 000, 1 125 000 (8,67° E, 46,27° N).
X, Y = 2_695_000.0, 1_125_000.0
TRONCONS = [  # (objektart, restriction, uuid, points en LV95)
    ("1m Weg", "Keine", "{A1}", [(X, Y, 800.0), (X + 50, Y + 20, 810.0)]),
    ("2m Weg", "Keine", "{A2}", [(X + 10, Y, 800.0), (X + 10, Y + 60, 805.0), (X + 30, Y + 80, 806.0)]),
    ("2m Weg", "Allgemeine Verkehrsbeschraenkung", "{B1}", [(X, Y + 5, 0.0), (X + 40, Y + 5, 0.0)]),
    ("4m Strasse", "Keine", "{B2}", [(X, Y + 9, 0.0), (X + 40, Y + 9, 0.0)]),
    ("1m Wegfragment", "Keine", "{A3}", [(X + 20_000, Y, 0.0), (X + 20_050, Y, 0.0)]),   # hors de l'emprise
]


def _archive(dossier):
    base = dossier / "swissTLM3D_TLM_STRASSE"
    with shapefile.Writer(str(base), shapeType=shapefile.POLYLINEZ, encoding="utf-8") as w:
        w.field("UUID", "C", 38)
        w.field("OBJEKTART", "C", 50)
        w.field("VERKEHRSBE", "C", 50)
        for objektart, restriction, uuid, points in TRONCONS:
            w.linez([points])
            w.record(uuid, objektart, restriction)
    chemin = dossier / "swisstlm3d_2026-02_2056_5728.shp.zip"
    with zipfile.ZipFile(chemin, "w", zipfile.ZIP_DEFLATED) as z:
        for extension in (".shp", ".shx", ".dbf"):
            # Comme l'archive de swisstopo, faite sous Windows : des barres
            # obliques inverses dans les noms, que zipfile ne convertit qu'en
            # lisant sous Windows (le serveur, sous Linux, ne trouvait rien).
            membre = zipfile.ZipInfo("x")
            membre.filename = (sn.COUCHE + extension).replace("/", "\\")
            membre.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(membre, base.with_suffix(extension).read_bytes())
        z.writestr("TLM_BAUTEN/swissTLM3D_TLM_GEBAEUDE.dbf", b"batiments" * 1000)
    return chemin


def test_l_edition_la_plus_recente_du_catalogue():
    pages = {
        sn.STAC: {"features": [{"assets": {"a": {"href": URL.replace("2026-02", "2025-03")}}}],
                  "links": [{"rel": "next", "href": "page2"}]},
        "page2": {"features": [{"assets": {"a": {"href": URL}, "b": {"href": URL.replace(".shp.", ".gdb.")}}}],
                  "links": []},
    }
    edition = sn.derniere_edition(lire=pages.__getitem__, taille=lambda url: 3_591_345_815)
    assert edition == {"nom": "swisstlm3d_2026-02", "date": "2026-02",
                       "fichiers": [{"url": URL, "octets": 3_591_345_815, "md5": None}]}


def test_le_lecteur_rend_les_chemins_comme_l_api(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    archive = _archive(source)
    telecharges = []

    def telecharger(fichier, cible, ouvrir=None, essais=3, plages=1):
        telecharges.append((fichier["url"], plages))
        cible.write_bytes(archive.read_bytes())
    monkeypatch.setattr(en_bloc, "telecharger", telecharger)
    monkeypatch.setattr(sn, "derniere_edition", lambda: {"nom": "swisstlm3d_2026-02", "date": "2026-02",
                                                          "fichiers": [{"url": URL, "octets": 1, "md5": None}]})
    racine = tmp_path / "donnees" / sn.DOSSIER
    racine.mkdir(parents=True)
    (racine / "swisstlm3d_2025-03.chemins.sqlite").write_bytes(b"ancienne")
    lecteur = sn.Lecteur(tmp_path / "donnees")
    lus = lecteur(46.20, 8.62, 46.30, 8.75)
    assert sorted((t["id"], t["nature"]) for t in lus) == [("A1:0", "Weg 16"), ("A2:0", "Weg 15")], \
        "ni le chemin à circulation restreinte, ni la route, ni le fragment hors de l'emprise"
    a2 = next(t for t in lus if t["id"] == "A2:0")
    assert len(a2["pts"]) == 3 and all(46.0 < la < 46.5 and 8.5 < lo < 9.0 for la, lo in a2["pts"])
    lecteur(46.20, 8.62, 46.30, 8.75)
    assert telecharges == [(URL, sn.PLAGES)], "une seule fois, en plages"
    assert lecteur.date(46.2, 8.6, 46.3, 8.7) == "2026-02"
    assert sorted(p.name for p in racine.iterdir()) == ["swisstlm3d_2026-02.chemins.sqlite"], \
        "ni l'archive, ni le Shapefile, ni l'ancienne édition"


def test_une_archive_sans_la_couche_est_refusee(tmp_path):
    chemin = tmp_path / "vide.zip"
    with zipfile.ZipFile(chemin, "w") as z:
        z.writestr("TLM_BAUTEN/x.dbf", b"x")
    with pytest.raises(sn.ErreurArchive):
        sn._extraire(chemin, tmp_path / "extrait")


def test_la_suisse_se_lit_en_bloc():
    from hike2gpx import fabrication
    assert "swisstlm3d" in fabrication.EN_BLOC
    lecteurs, editions = fabrication.lecteurs_en_bloc("donnees")
    assert isinstance(lecteurs["swisstlm3d"], sn.Lecteur) and hasattr(lecteurs["swisstlm3d"], "preparer")
