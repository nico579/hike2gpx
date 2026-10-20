"""Construit le programme hike2gpx dans un environnement isolé jetable, comme
le build.py de watch2notif et de blink2video : dépendances verrouillées
(requirements-build.txt), Java de BRouter (JRE Temurin 21, comme lidar2map),
PyInstaller sur hike2gpx.spec, puis l'auto-test du programme construit.

    python build.py              construit dist/hike2gpx (dist/hike2gpx.app sous macOS)
    python build.py --archive    puis l'archive de ce système et son .sha256, dans dist/
    python build.py --propre     repart de zéro : environnement, Java, sorties

Pourquoi un environnement à part : PyInstaller embarque ce qu'il trouve dans
site-packages. Un environnement neuf, rempli du seul verrou, donne le même
programme d'une machine à l'autre, en local comme sur GitHub.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
VENV = BASE / "build_venv"
PYTHON = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
JRE = BASE / "build" / "jre"
TELECHARGEMENTS = BASE / "build" / "telechargements"
DIST = BASE / "dist"
NOM = "hike2gpx"
RACINE_MACOS = "hike2gpx.app"
# La dernière version publiée du JRE Temurin 21, comme lidar2map, avec
# l'empreinte SHA-256 qu'Adoptium donne à côté du lien.
ADOPTIUM = "https://api.adoptium.net/v3/assets/latest/21/hotspot"
TEMURIN = "https://github.com/adoptium/temurin21-binaries/releases/download/"
AGENT = {"User-Agent": "hike2gpx-build"}


def version() -> str:
    texte = (BASE / "hike2gpx" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__ = "([^"]+)"', texte)[1]


def executer(commande: list, titre: str) -> None:
    print(f"\n=== {titre}", flush=True)
    if subprocess.run([str(c) for c in commande], cwd=BASE, check=False).returncode:
        raise SystemExit(f"Échec : {titre}")


def empreinte(chemin: Path) -> str:
    somme = hashlib.sha256()
    with open(chemin, "rb") as fichier:
        while bloc := fichier.read(1 << 20):
            somme.update(bloc)
    return somme.hexdigest()


# ------------------------------------------------------------------ Java

def jre_publie(systeme: str | None = None, machine: str | None = None, ouvrir=urllib.request.urlopen) -> dict:
    """Le dernier JRE Temurin 21 de ce système : nom, lien, empreinte, version."""
    nom_os = {"Windows": "windows", "Darwin": "mac", "Linux": "linux"}[systeme or platform.system()]
    arch = "aarch64" if (machine or platform.machine()).lower() in ("arm64", "aarch64") else "x64"
    demande = urllib.request.Request(f"{ADOPTIUM}?architecture={arch}&image_type=jre&os={nom_os}&vendor=eclipse",
                                     headers=AGENT)
    with ouvrir(demande, timeout=60) as reponse:
        publie = json.load(reponse)[0]
    paquet = publie["binary"]["package"]
    if not paquet["link"].startswith(TEMURIN) or not re.fullmatch(r"[0-9a-f]{64}", paquet["checksum"]):
        raise SystemExit(f"Réponse d'Adoptium inattendue : {paquet['link']}")
    return {"nom": paquet["name"], "lien": paquet["link"], "sha256": paquet["checksum"],
            "version": publie["release_name"]}


def telecharger(url: str, cible: Path, sha256: str) -> Path:
    """Le fichier à son empreinte, repris tel quel s'il est déjà là et intact."""
    if cible.is_file() and empreinte(cible) == sha256:
        return cible
    cible.parent.mkdir(parents=True, exist_ok=True)
    partiel = cible.with_name(cible.name + ".part")
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=120) as reponse, \
            open(partiel, "wb") as sortie:
        shutil.copyfileobj(reponse, sortie, 1 << 20)
    if empreinte(partiel) != sha256:
        partiel.unlink()
        raise SystemExit(f"Empreinte inattendue pour {url} : construction arrêtée.")
    os.replace(partiel, cible)
    return cible


def installer_jre(archive: Path, destination: Path) -> Path:
    """Extrait l'archive du JRE et pose en destination son dossier d'accueil,
    celui qui contient bin/java (sous macOS, Contents/Home : le reste du bundle
    Temurin gênerait la signature du .app)."""
    extraction = destination.with_name(destination.name + ".extraction")
    shutil.rmtree(extraction, ignore_errors=True)
    extraction.mkdir(parents=True)
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as contenu:
            for membre in contenu.namelist():
                if membre.startswith(("/", "\\")) or ":" in membre or ".." in Path(membre).parts:
                    raise SystemExit(f"Archive du JRE suspecte : {membre}")
            contenu.extractall(extraction)
    else:
        with tarfile.open(archive) as contenu:
            try:
                contenu.extractall(extraction, filter="data")    # refuse chemins absolus et liens sortants
            except tarfile.FilterError as exc:
                raise SystemExit(f"Archive du JRE suspecte : {exc}") from exc
    javas = [p for p in extraction.rglob("*") if p.name in ("java", "java.exe") and p.parent.name == "bin"
             and p.is_file()]
    if len(javas) != 1:
        raise SystemExit(f"Archive du JRE inattendue : {len(javas)} exécutables java.")
    shutil.rmtree(destination, ignore_errors=True)
    os.replace(javas[0].parent.parent, destination)
    shutil.rmtree(extraction, ignore_errors=True)
    return destination


def preparer_jre() -> None:
    print("\n=== Java embarqué (JRE Temurin 21)", flush=True)
    publie = jre_publie()
    marque = JRE.with_name("jre.json")       # hors du dossier embarqué
    try:
        deja = json.loads(marque.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        deja = {}
    if deja.get("sha256") != publie["sha256"] or not JRE.is_dir():
        archive = telecharger(publie["lien"], TELECHARGEMENTS / publie["nom"], publie["sha256"])
        installer_jre(archive, JRE)
        marque.write_text(json.dumps(publie, indent=1), encoding="utf-8")
    print(f"{publie['version']} ({publie['nom']})")


# ------------------------------------------------------------------ programme

def executable() -> Path:
    if sys.platform == "darwin":
        return DIST / RACINE_MACOS / "Contents" / "MacOS" / NOM
    return DIST / NOM / (NOM + (".exe" if sys.platform == "win32" else ""))


def auto_test(exe: Path) -> None:
    """--self-test-version sur le programme construit. Sa sortie est captée :
    sans console, l'exécutable Windows n'écrirait nulle part."""
    print("\n=== Auto-test du programme construit", flush=True)
    resultat = subprocess.run([str(exe), "--self-test-version", version()], capture_output=True, text=True,
                              errors="replace", timeout=120, check=False)
    print((resultat.stdout + resultat.stderr).strip())
    if resultat.returncode:
        raise SystemExit(f"Échec de l'auto-test (code {resultat.returncode})")


def construire() -> Path:
    if sys.version_info[:2] != (3, 12):
        raise SystemExit("Python 3.12 requis : c'est celui des verrous et de requires-python.")
    if not PYTHON.exists():
        executer([sys.executable, "-m", "venv", VENV], "création de l'environnement de construction")
    # Le verrou de construction : version exacte et empreinte de chaque paquet,
    # PyInstaller compris.
    executer([PYTHON, "-m", "pip", "install", "--quiet", "--require-hashes", "-r", "requirements-build.txt"],
             "installation des dépendances verrouillées")
    preparer_jre()
    executer([PYTHON, "-m", "PyInstaller", "--noconfirm", "--clean", "hike2gpx.spec"], "construction du programme")
    exe = executable()
    if not exe.is_file():
        raise SystemExit(f"Exécutable introuvable : {exe}")
    auto_test(exe)
    return exe


# ------------------------------------------------------------------ archive

def archive_publiee(python: Path = PYTHON) -> tuple:
    """(fichier, genre, racine) de l'archive de ce système, demandés au commun
    lui-même (maj_install.archive_standard) : la mise à jour automatique la
    cherche sous ce nom, et la règle ne vit qu'à un endroit."""
    code = (f"from nico579_commons.maj_install import archive_standard\n"
            f"print(*archive_standard({NOM!r}, racine_macos={RACINE_MACOS!r}), sep='\\n')")
    sortie = subprocess.run([str(python), "-c", code], capture_output=True, text=True, check=True)
    return tuple(sortie.stdout.split())


def emballer(fichier: str, genre: str, racine: str, dist: Path = DIST) -> Path:
    """L'archive publiée et son empreinte (format de sha256sum). Windows et
    Linux : le dossier du programme sous le nom de l'archive ; macOS : le
    .app signé ad hoc, archivé par ditto, qui garde liens et attributs."""
    archive = dist / fichier
    archive.unlink(missing_ok=True)
    dossier = dist / NOM
    if racine.endswith(".app"):
        app = dist / racine
        executer(["codesign", "--force", "--deep", "--sign", "-", app], "signature ad hoc du .app")
        executer(["codesign", "--verify", "--deep", "--strict", "--verbose=2", app], "vérification de la signature")
        executer(["ditto", "-c", "-k", "--keepParent", app, archive], "archive du .app")
    elif genre == "tar":
        with tarfile.open(archive, "w:gz") as contenu:
            contenu.add(dossier, arcname=racine)
    else:
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as contenu:
            for chemin in sorted(dossier.rglob("*")):
                contenu.write(chemin, Path(racine) / chemin.relative_to(dossier))
    dist.joinpath(fichier + ".sha256").write_text(f"{empreinte(archive)}  {fichier}\n", encoding="ascii")
    return archive


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=version(), help="version de hike2gpx construite")
    parser.add_argument("--archive", action="store_true", help="emballer aussi l'archive publiée et son .sha256")
    parser.add_argument("--propre", action="store_true", help="supprimer environnement, Java et sorties d'abord")
    args = parser.parse_args()
    if args.propre:
        for dossier in (VENV, BASE / "build", DIST):
            shutil.rmtree(dossier, ignore_errors=True)
    exe = construire()
    taille = sum(f.stat().st_size for f in exe.parents[2 if sys.platform == "darwin" else 0].rglob("*")
                 if f.is_file())
    print(f"\nProgramme construit : {exe} ({taille / 1024 / 1024:.0f} Mo)")
    if args.archive:
        archive = emballer(*archive_publiee())
        print(f"Archive : {archive} ({archive.stat().st_size / 1024 / 1024:.0f} Mo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
