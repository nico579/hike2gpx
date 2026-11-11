"""Carte OpenStreetMap hors ligne (mapsforge.py), sans réseau ni Java : le
choix des extraits, la ligne d'Osmosis, puis le rangement, la suppression et
le partage d'une carte à côté des fonds en images."""
import json
from pathlib import Path

import pytest

from hike2gpx import brouter, fonds, mapsforge, partage
from hike2gpx.application import Application
from hike2gpx.hors_ligne import HorsLigne

CARRE = "N43E006"
ZONE = fonds.boite_carre(CARRE)


def region(identifiant, sud, ouest, nord, est, parent=None):
    """Une région Geofabrik rectangulaire, comme geofabrik._region la rend."""
    return {"id": identifiant, "nom": identifiant, "pbf": f"https://exemple.test/{identifiant}-latest.osm.pbf",
            "bornes": (sud, ouest, nord, est), "parent": parent,
            "polygones": [[[(ouest, sud), (est, sud), (est, nord), (ouest, nord)]]]}


def test_le_plus_petit_extrait_qui_contient_le_carre():
    regions = [region("europe", 35, -10, 70, 40), region("france", 41, -5, 51, 10, "europe"),
               region("paca", 42.9, 4.2, 45.2, 7.8, "france")]
    assert [r["id"] for r in mapsforge.regions_du_carre(regions, ZONE)] == ["paca"]


def test_un_carre_a_cheval_prend_les_deux_petits_extraits_plutot_que_le_grand():
    # La frontière passe à 6,5° est : aucun petit extrait ne contient tout le carré.
    regions = [region("europe", 35, -10, 70, 40), region("ouest", 42, 4, 45, 6.5, "europe"),
               region("est", 42, 6.5, 45, 9, "europe")]
    assert sorted(r["id"] for r in mapsforge.regions_du_carre(regions, ZONE)) == ["est", "ouest"]


def test_les_points_en_mer_ne_comptent_pas_et_un_carre_tout_en_mer_n_a_pas_d_extrait():
    # La côte à 43,4° nord : le sud du carré est en mer, hors de tout contour.
    cote = [region("littoral", 43.4, 4, 45, 9)]
    assert [r["id"] for r in mapsforge.regions_du_carre(cote, ZONE)] == ["littoral"]
    assert mapsforge.regions_du_carre(cote, fonds.boite_carre("N40E006")) == []


def test_la_ligne_d_osmosis(tmp_path, monkeypatch):
    monkeypatch.setattr(brouter, "java", lambda: "java")
    monkeypatch.setattr(brouter, "memoire_physique", lambda: 16 << 30)
    outils = mapsforge.Outils(tmp_path)
    ligne = mapsforge.commande(outils, [Path("a.osm.pbf"), Path("b.osm.pbf")], tmp_path / "carte.map.part", ZONE)
    assert ligne[:2] == ["java", "-Xmx2048m"], "le quart de la mémoire, 2 Go au plus"
    # Le greffon sur le chemin de classes, et le dossier personnel détourné :
    # la copie du greffon d'un autre logiciel ne se déclare pas une seconde fois.
    assert f"-Duser.home={outils.racine}" in ligne
    # Ses fichiers de travail dans un dossier à lui, pas dans celui des cartes.
    assert f"-Djava.io.tmpdir={outils.travail}" in ligne
    assert ligne[ligne.index("-cp") + 1].endswith(mapsforge.GREFFON)
    assert ligne.count("--read-pbf") == 2 and ligne.count("--merge") == 1
    assert "left=5.95" in ligne and "top=44.05" in ligne, "la boîte lue déborde un peu du carré"
    assert ligne[-3:] == [f"file={tmp_path / 'carte.map.part'}", "bbox=43,6,44,7", "type=hd"]
    isolement = mapsforge.isolement(outils)
    assert isolement["cwd"] == outils.racine and isolement["env"]["APPDATA"] == str(outils.racine)
    # Une machine modeste garde un tas d'au moins 1 Go.
    monkeypatch.setattr(brouter, "memoire_physique", lambda: 1 << 30)
    assert mapsforge.commande(outils, [Path("a.osm.pbf")], tmp_path / "c.part", ZONE)[1] == "-Xmx1024m"


def test_une_carte_se_decrit_par_son_nom(tmp_path):
    carte = tmp_path / f"{mapsforge.nom_carte(CARRE)}.map"
    carte.write_bytes(b"mapsforge binary OSM" + bytes(100))
    assert mapsforge.decrire(carte) == {
        "nom": "N43E006-osm", "zone": [43, 6, 44, 7], "zoom": [0, 21], "source": "osm", "format": "map",
        "attribution": "© les contributeurs d'OpenStreetMap", "octets": 120}
    with pytest.raises(ValueError):
        mapsforge.decrire(tmp_path / "n-importe-quoi.map")


def test_une_carte_est_un_fond_de_plus_rangee_supprimee_et_partagee_a_part(tmp_path):
    hors_ligne = HorsLigne(tmp_path)
    hors_ligne.dossier_fonds.mkdir(parents=True)
    carte = hors_ligne.dossier_fonds / "N43E006-osm.map"
    carte.write_bytes(b"mapsforge binary OSM")
    (hors_ligne.dossier_fonds / "N43E006-osm.map.part").write_bytes(b"en cours")
    [f] = hors_ligne.fonds()
    assert f["nom"] == "N43E006-osm" and f["format"] == "map"
    assert hors_ligne.chemin_fond("N43E006-osm") is None, "pas de tuiles à servir à la page"
    # Le catalogue du partage la range sous « cartes » : un téléphone qui ne
    # connaît que les MBTiles de « fonds » ne la prend pas.
    catalogue, fichiers = partage.dresser(hors_ligne)
    assert catalogue["fonds"] == []
    [c] = catalogue["cartes"]
    assert c["url"] == "fonds/N43E006-osm.map" and fichiers[c["url"]] == carte and len(c["sha256"]) == 64
    assert json.dumps(catalogue)
    # « Supprimer » du volet retire la carte du carré, comme ses fonds en images.
    assert hors_ligne.supprimer_fond(CARRE) == 20
    assert not carte.exists() and hors_ligne.fonds() == []


def test_l_application_fabrique_la_carte_quand_le_fond_est_openstreetmap(tmp_path, monkeypatch):
    a = Application(tmp_path)
    appels = []

    def fabriquer(dossier, chemin, zone, *, suivi, continuer):
        appels.append((dossier, chemin.name, zone))
        suivi("carte", 0, 0)
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_bytes(b"mapsforge binary OSM")
        return mapsforge.decrire(chemin)

    monkeypatch.setattr(mapsforge, "fabriquer", fabriquer)
    assert a.etat()["fonds_hors_ligne"]["osm"] == "OpenStreetMap"
    a.preparer_fond({"carres": [CARRE], "source": "osm"})
    a._fil_lot.join(10)
    assert appels == [(a.dossier, "N43E006-osm.map", ZONE)]
    assert a.lot_en_cours()["fond"] == "N43E006-osm"
    [f] = a.lots_hors_ligne()["fonds"]
    assert f["format"] == "map" and f["source"] == "osm"
    # Une erreur de fabrication va à la page, comme pour un fond en images.
    monkeypatch.setattr(mapsforge, "fabriquer", lambda *a, **k: (_ for _ in ()).throw(mapsforge.ErreurCarte("en mer")))
    a.preparer_fond({"carres": ["N40E006"], "source": "osm"})
    a._fil_lot.join(10)
    assert a.lot_en_cours()["erreur"] == "en mer"


def test_les_restes_d_osmosis_s_effacent_sans_toucher_aux_cartes(tmp_path):
    # Un Osmosis interrompu laisse ses index et ses tas : dans le dossier de
    # travail désormais, dans celui des cartes avec les versions 0.9.8 et 0.9.9.
    outils = mapsforge.Outils(tmp_path)
    cartes = tmp_path / "hors-ligne" / "fonds"
    cartes.mkdir(parents=True)
    (cartes / "N43E006-osm.map").write_bytes(b"carte" * 10)
    (cartes / "N43E006-scan25.mbtiles").write_bytes(b"fond" * 10)
    (cartes / "N43E004-scan25.mbtiles.part").write_bytes(b"reprise")
    (cartes / "idxNodesd123.tmp").write_bytes(b"x" * 100)
    (cartes / "heapWays456.tmp").write_bytes(b"x" * 50)
    outils.travail.mkdir(parents=True)
    (outils.travail / "idxWaysd789.tmp").write_bytes(b"x" * 30)
    assert mapsforge.nettoyer(outils, cartes) == 180
    assert sorted(p.name for p in cartes.iterdir()) == \
        ["N43E004-scan25.mbtiles.part", "N43E006-osm.map", "N43E006-scan25.mbtiles"], \
        "les cartes et le téléchargement à reprendre restent"
    assert not outils.travail.exists()
    assert mapsforge.nettoyer(outils, cartes) == 0, "rien à refaire"
