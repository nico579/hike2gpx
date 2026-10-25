#!/usr/bin/env python3
"""Télécharge une archive régionale BD TOPO avec reprise et contrôle MD5."""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sqlite3
import subprocess
import time
import urllib.request
from pathlib import Path, PurePosixPath

from ign_catalogue import REGIONS, derniere_edition


def telecharger(fichier: dict, dossier: Path) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    nom = fichier["url"].rsplit("/", 1)[-1]
    cible = dossier / nom
    if cible.is_file() and cible.stat().st_size == fichier["octets"]:
        if empreinte_md5(cible) == fichier["md5"]:
            return cible
    part = dossier / (nom + ".part")
    libres = shutil.disk_usage(dossier).free
    if libres < 20 * 1024**3 + 3 * fichier["octets"]:
        raise RuntimeError(f"Espace insuffisant : {libres / 1024**3:.1f} Gio libres.")
    for essai in range(3):
        offset = part.stat().st_size if part.exists() else 0
        if offset > fichier["octets"]:
            part.unlink()
            offset = 0
        if offset == fichier["octets"]:
            break
        demande = urllib.request.Request(fichier["url"], headers={
            "User-Agent": "hike2gpx/0.3.2", **({"Range": f"bytes={offset}-"} if offset else {})})
        try:
            with urllib.request.urlopen(demande, timeout=120) as reponse:
                if offset and reponse.status != 206:
                    part.unlink(missing_ok=True)
                    offset = 0
                with part.open("ab" if offset else "wb") as sortie:
                    dernier = -1
                    while bloc := reponse.read(1024 * 1024):
                        sortie.write(bloc)
                        offset += len(bloc)
                        palier = int(offset * 20 / fichier["octets"])
                        if palier > dernier:
                            dernier = palier
                            print(f"{nom} : {palier * 5} %, "
                                  f"{shutil.disk_usage(dossier).free / 1024**3:.1f} Gio libres", flush=True)
            if offset == fichier["octets"]:
                break
        except OSError as exc:
            if essai == 2:
                raise
            print(f"Téléchargement interrompu ({exc}), reprise...", flush=True)
            time.sleep(10 * (essai + 1))
    if part.stat().st_size != fichier["octets"]:
        raise RuntimeError(f"Archive incomplète : {part.stat().st_size} / {fichier['octets']} octets.")
    if empreinte_md5(part) != fichier["md5"]:
        raise RuntimeError(f"MD5 incorrect pour {nom}.")
    os.replace(part, cible)
    return cible


def empreinte_md5(chemin: Path) -> str:
    empreinte = hashlib.md5(usedforsecurity=False)
    with chemin.open("rb") as entree:
        while bloc := entree.read(1024 * 1024):
            empreinte.update(bloc)
    return empreinte.hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zone", choices=REGIONS, required=True)
    parser.add_argument("--dossier", type=Path, required=True)
    parser.add_argument("--extraire", action="store_true", help="extraire le GeoPackage et retirer l'archive")
    args = parser.parse_args(argv)
    paquet = derniere_edition(args.zone)
    print(f"{paquet['edition']} : {paquet['octets'] / 1024**3:.2f} Gio", flush=True)
    if len(paquet["fichiers"]) != 1:
        parser.error("Archive régionale multipartie : traitement non encore prévu.")
    archive = telecharger(paquet["fichiers"][0], args.dossier)
    resultat = subprocess.run(["7z", "l", "-slt", str(archive)], check=True,
                             capture_output=True, text=True, encoding="utf-8", errors="replace")
    chemins = [ligne.removeprefix("Path = ") for ligne in resultat.stdout.splitlines()
               if ligne.startswith("Path = ") and ligne.lower().endswith(".gpkg")]
    for chemin in chemins:
        print(f"GeoPackage : {chemin}", flush=True)
    print(f"Archive vérifiée : {archive} ({archive.stat().st_size} octets)", flush=True)
    if args.extraire:
        if len(chemins) != 1:
            parser.error("Un seul GeoPackage est attendu dans l'archive régionale.")
        relatif = PurePosixPath(chemins[0])
        if relatif.is_absolute() or ".." in relatif.parts:
            parser.error("Chemin GeoPackage invalide dans l'archive.")
        sortie = args.dossier / "extrait"
        gpkg = sortie.joinpath(*relatif.parts)
        if not gpkg.is_file():
            if shutil.disk_usage(args.dossier).free < 20 * 1024**3:
                parser.error("Moins de 20 Gio libres avant extraction.")
            subprocess.run(["7z", "x", "-y", "-bd", "-bso0", f"-o{sortie}", str(archive), chemins[0]],
                           check=True)
        with sqlite3.connect(f"file:{gpkg.as_posix()}?mode=ro", uri=True) as base:
            tables = [ligne[0] for ligne in base.execute("SELECT table_name FROM gpkg_contents")]
        if not any("troncon_de_route" in table.lower() for table in tables):
            raise RuntimeError(f"Couche de chemins introuvable : {tables}")
        archive.unlink()
        print(f"GeoPackage vérifié : {gpkg}, {gpkg.stat().st_size / 1024**3:.2f} Gio ; "
              f"archive effacée ; {shutil.disk_usage(args.dossier).free / 1024**3:.1f} Gio libres", flush=True)
        print("Tables : " + ", ".join(table for table in tables if "troncon" in table.lower()), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
