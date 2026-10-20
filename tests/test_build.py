"""build.py : le Java embarqué et l'archive publiée. La construction elle-même
(PyInstaller, auto-test du programme) tourne dans release.yml."""
import hashlib
import importlib.util
import io
import json
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest
from nico579_commons import maj_install

RACINE = Path(__file__).resolve().parents[1]
_charge = importlib.util.spec_from_file_location("build_hike2gpx", RACINE / "build.py")
build = importlib.util.module_from_spec(_charge)
_charge.loader.exec_module(build)


def test_version_lue_dans_le_paquet():
    from hike2gpx import __version__
    assert build.version() == __version__


def test_nom_de_l_archive_donne_par_le_commun():
    # La mise à jour automatique cherche l'archive sous le nom d'archive_standard.
    attendu = maj_install.archive_standard("hike2gpx", racine_macos="hike2gpx.app")
    assert build.archive_publiee(Path(sys.executable)) == attendu


class Reponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_jre_publie_par_adoptium_avec_son_empreinte():
    lien = build.TEMURIN + "jdk-21.0.9%2B10/OpenJDK21U-jre_x64_windows_hotspot_21.0.9_10.zip"
    publie = [{"release_name": "jdk-21.0.9+10", "binary": {"package": {
        "name": "OpenJDK21U-jre_x64_windows_hotspot_21.0.9_10.zip", "link": lien, "checksum": "a" * 64}}}]
    demandes = []
    ouvrir = lambda demande, timeout: demandes.append(demande.full_url) or Reponse(json.dumps(publie).encode())
    jre = build.jre_publie("Windows", "AMD64", ouvrir=ouvrir)
    assert jre == {"nom": "OpenJDK21U-jre_x64_windows_hotspot_21.0.9_10.zip", "lien": lien, "sha256": "a" * 64,
                   "version": "jdk-21.0.9+10"}
    assert "architecture=x64&image_type=jre&os=windows" in demandes[0]
    build.jre_publie("Darwin", "arm64", ouvrir=ouvrir)
    assert "architecture=aarch64&image_type=jre&os=mac" in demandes[1]
    publie[0]["binary"]["package"]["link"] = "https://exemple.org/jre.zip"
    with pytest.raises(SystemExit, match="inattendue"):
        build.jre_publie("Windows", "AMD64", ouvrir=ouvrir)


def _tar(chemin: Path, membres: dict) -> Path:
    with tarfile.open(chemin, "w:gz") as contenu:
        for nom, donnees in membres.items():
            info = tarfile.TarInfo(nom)
            info.size, info.mode = len(donnees), 0o755
            contenu.addfile(info, io.BytesIO(donnees))
    return chemin


def test_jre_macos_pose_son_seul_contents_home(tmp_path):
    # Le reste du bundle Temurin ferait refuser la signature du .app (lidar2map).
    archive = _tar(tmp_path / "jre.tar.gz", {"jdk-21.0.9+10-jre/Contents/Home/bin/java": b"java",
                                             "jdk-21.0.9+10-jre/Contents/Home/lib/modules": b"m",
                                             "jdk-21.0.9+10-jre/Contents/Info.plist": b"p"})
    jre = build.installer_jre(archive, tmp_path / "jre")
    assert sorted(p.relative_to(jre).as_posix() for p in jre.rglob("*") if p.is_file()) == ["bin/java", "lib/modules"]
    assert not (tmp_path / "jre.extraction").exists()


def test_jre_windows_depuis_un_zip(tmp_path):
    archive = tmp_path / "jre.zip"
    with zipfile.ZipFile(archive, "w") as contenu:
        contenu.writestr("jdk-21.0.9+10-jre/bin/java.exe", b"java")
        contenu.writestr("jdk-21.0.9+10-jre/bin/javaw.exe", b"javaw")
    jre = build.installer_jre(archive, tmp_path / "jre")
    assert (jre / "bin" / "java.exe").read_bytes() == b"java"


def test_jre_refuse_une_archive_suspecte(tmp_path):
    archive = tmp_path / "jre.zip"
    with zipfile.ZipFile(archive, "w") as contenu:
        contenu.writestr("jdk/bin/java.exe", b"java")
        contenu.writestr("../ailleurs.txt", b"x")
    with pytest.raises(SystemExit, match="suspecte"):
        build.installer_jre(archive, tmp_path / "jre")
    with pytest.raises(SystemExit, match="suspecte"):
        build.installer_jre(_tar(tmp_path / "jre.tar.gz", {"jdk/bin/java": b"java", "../ailleurs": b"x"}),
                            tmp_path / "jre")
    assert not (tmp_path / "ailleurs").exists()


def test_telechargement_verifie_et_repris(tmp_path, monkeypatch):
    contenu = b"archive du JRE"
    somme = hashlib.sha256(contenu).hexdigest()
    monkeypatch.setattr(build.urllib.request, "urlopen", lambda demande, timeout: Reponse(contenu))
    cible = build.telecharger("https://exemple/jre.zip", tmp_path / "jre.zip", somme)
    assert cible.read_bytes() == contenu
    monkeypatch.setattr(build.urllib.request, "urlopen", lambda *a, **o: pytest.fail("retéléchargé"))
    assert build.telecharger("https://exemple/jre.zip", cible, somme) == cible
    monkeypatch.setattr(build.urllib.request, "urlopen", lambda demande, timeout: Reponse(b"autre chose"))
    with pytest.raises(SystemExit, match="Empreinte"):
        build.telecharger("https://exemple/jre2.zip", tmp_path / "jre2.zip", somme)
    assert not list(tmp_path.glob("jre2*"))


def _programme(dist: Path) -> None:
    (dist / "hike2gpx" / "_internal" / "jre" / "bin").mkdir(parents=True)
    (dist / "hike2gpx" / "hike2gpx.exe").write_bytes(b"exe")
    (dist / "hike2gpx" / "_internal" / "jre" / "bin" / "java.exe").write_bytes(b"java")


def test_archive_windows_et_son_empreinte(tmp_path):
    _programme(tmp_path)
    archive = build.emballer("hike2gpx-windows-x86_64.zip", "zip", "hike2gpx-windows-x86_64", dist=tmp_path)
    with zipfile.ZipFile(archive) as contenu:
        noms = set(contenu.namelist())
    assert {"hike2gpx-windows-x86_64/hike2gpx.exe", "hike2gpx-windows-x86_64/_internal/jre/bin/java.exe"} <= noms
    assert (tmp_path / "hike2gpx-windows-x86_64.zip.sha256").read_text(encoding="ascii") == \
        f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  hike2gpx-windows-x86_64.zip\n"


def test_archive_linux_garde_le_dossier_racine(tmp_path):
    _programme(tmp_path)
    archive = build.emballer("hike2gpx-linux-x86_64.tar.gz", "tar", "hike2gpx-linux-x86_64", dist=tmp_path)
    with tarfile.open(archive) as contenu:
        assert "hike2gpx-linux-x86_64/_internal/jre/bin/java.exe" in contenu.getnames()
