"""L'archive zip des cases : exportée d'un PC, importée sur un autre (archive.py)."""
import http.client
import io
import json
import zipfile

import pytest

from hike2gpx import archive, hors_ligne, web
from hike2gpx.application import Application

from test_partage import preparer, tuiles_telles_quelles  # noqa: F401  (la fixture vaut ici aussi)

TOUT = {"lots": ["E5_N40"], "carres": ["E5_N40"], "source": None}


def exporter(h, selection=TOUT) -> bytes:
    cible = h.racine.parent / "export.zip"
    archive.ecrire(h, cible, selection)
    contenu = cible.read_bytes()
    cible.unlink()
    return contenu


def test_une_archive_exportee_s_importe_a_l_identique_sur_un_autre_pc(tmp_path):
    source = preparer(tmp_path / "moi")
    contenu = exporter(source)
    noms = zipfile.ZipFile(io.BytesIO(contenu)).namelist()
    assert noms[0] == "catalog.json" and "fonds/E5_N40-scan25.mbtiles" in noms and "E5_N40/E5_N40.rd5" in noms
    # Sans compression, chaque taille avant ses données (bit 3 éteint) : ce que
    # ZipInputStream, le lecteur en flux d'Android, exige d'une entrée non compressée.
    for entree in zipfile.ZipFile(io.BytesIO(contenu)).infolist():
        assert entree.compress_type == zipfile.ZIP_STORED and not entree.flag_bits & 0x08, entree.filename
    (tmp_path / "ami.zip").write_bytes(contenu)
    ami = hors_ligne.HorsLigne(tmp_path / "ami")
    assert archive.importer(ami, tmp_path / "ami.zip") == {"lots": ["E5_N40"], "fonds": ["E5_N40-scan25"]}
    assert [m["case"] for m in ami.lots()] == ["E5_N40"]
    assert [f["nom"] for f in ami.fonds()] == ["E5_N40-scan25"]
    assert (ami.segments_osm / "E5_N40.rd5").read_bytes() == (source.segments_osm / "E5_N40.rd5").read_bytes()
    assert (ami.dossier_fonds / "E5_N40-scan25.mbtiles").read_bytes() \
        == (source.dossier_fonds / "E5_N40-scan25.mbtiles").read_bytes()
    assert not list((tmp_path / "ami" / "hors-ligne").rglob("*.part")), "aucun reste de travail"


def test_l_archive_ne_porte_que_la_selection(tmp_path):
    h = preparer(tmp_path)
    catalogue = json.loads(zipfile.ZipFile(io.BytesIO(exporter(h, {"lots": [], "carres": ["E5_N40"]}))).read(
        "catalog.json"))
    assert catalogue["lots"] == [] and [f["nom"] for f in catalogue["fonds"]] == ["E5_N40-scan25"]


def _reecrire(contenu: bytes, changer) -> bytes:
    """Une copie de l'archive dont changer(nom, octets) modifie le contenu."""
    sortie = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(contenu)) as a, zipfile.ZipFile(sortie, "w") as b:
        for nom in a.namelist():
            b.writestr(nom, changer(nom, a.read(nom)))
    return sortie.getvalue()


def test_un_fichier_altere_ou_un_nom_hors_du_dossier_est_refuse(tmp_path):
    contenu = exporter(preparer(tmp_path / "moi"))
    ami = hors_ligne.HorsLigne(tmp_path / "ami")
    # Un octet de trop dans la carte : son empreinte ne correspond plus.
    (tmp_path / "a.zip").write_bytes(_reecrire(contenu, lambda nom, o: o + b"!" if nom.startswith("fonds/") else o))
    with pytest.raises(archive.ErreurArchive, match="altéré"):
        archive.importer(ami, tmp_path / "a.zip")
    assert ami.fonds() == [] and not list(ami.dossier_fonds.glob("*.part"))

    # Un catalogue qui voudrait écrire hors du dossier des cartes.
    def evasion(nom, o):
        if nom != "catalog.json":
            return o
        catalogue = json.loads(o)
        catalogue["lots"] = []
        catalogue["fonds"][0]["nom"] = "../../ailleurs"
        return json.dumps(catalogue).encode()
    (tmp_path / "b.zip").write_bytes(_reecrire(contenu, evasion))
    with pytest.raises(archive.ErreurArchive, match="invalide"):
        archive.importer(ami, tmp_path / "b.zip")
    assert not (tmp_path / "ailleurs.mbtiles").exists()


def test_un_zip_qui_n_est_pas_une_archive_de_hike2gpx_est_refuse(tmp_path):
    autre = io.BytesIO()
    with zipfile.ZipFile(autre, "w") as z:
        z.writestr("photo.jpg", b"...")
    (tmp_path / "autre.zip").write_bytes(autre.getvalue())
    (tmp_path / "pas-un-zip.zip").write_bytes(b"bonjour")
    h = hors_ligne.HorsLigne(tmp_path)
    with pytest.raises(archive.ErreurArchive, match="catalog.json manque"):
        archive.importer(h, tmp_path / "autre.zip")
    with pytest.raises(archive.ErreurArchive, match="illisible"):
        archive.importer(h, tmp_path / "pas-un-zip.zip")


def test_de_page_a_page_l_archive_part_d_un_pc_et_s_installe_sur_l_autre(tmp_path):
    preparer(tmp_path / "moi")
    moi, port_moi = web.demarrer(Application(tmp_path / "moi"), port=8840, plage=20)
    ami_app = Application(tmp_path / "ami")
    ami, port_ami = web.demarrer(ami_app, port=port_moi + 1, plage=20)
    try:
        connexion = http.client.HTTPConnection(web.HOST, port_moi, timeout=10)
        connexion.request("GET", "/archive.zip?lots=E5_N40&carres=", headers={"Sec-Fetch-Site": "same-origin"})
        reponse = connexion.getresponse()
        assert reponse.status == 200 and reponse.getheader("Content-Type") == "application/zip"
        assert reponse.getheader("Content-Disposition") == 'attachment; filename="hike2gpx-E5_N40.zip"'
        contenu = reponse.read()
        connexion.close()
        # Une page d'un autre site ne déclenche pas d'export ; une sélection invalide non plus.
        for chemin, entetes in (("/archive.zip?lots=E5_N40", {"Sec-Fetch-Site": "cross-site"}),
                                ("/archive.zip?lots=../x", {})):
            connexion = http.client.HTTPConnection(web.HOST, port_moi, timeout=10)
            connexion.request("GET", chemin, headers=entetes)
            assert connexion.getresponse().status in (400, 403)
            connexion.close()
        connexion = http.client.HTTPConnection(web.HOST, port_ami, timeout=10)
        connexion.request("POST", "/api/importer_archive", body=contenu,
                          headers={"Content-Type": "application/zip", "Sec-Fetch-Site": "same-origin"})
        r = json.loads(connexion.getresponse().read())
        connexion.close()
        assert r["importe"] == {"lots": ["E5_N40"], "fonds": []}
        assert [l["case"] for l in r["lots"]] == ["E5_N40"]
        assert not list((tmp_path / "ami" / "hors-ligne").glob(".archive-*")), "le zip reçu ne reste pas"
    finally:
        for serveur in (moi, ami):
            serveur.shutdown()
            serveur.server_close()
