#!/usr/bin/env python3
"""Publie par SSH un paquet statique de fragments RD5 et de données associées."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
from pathlib import Path

from hike2gpx import brouter, mailles, providers, rd5_fragments
from nico579_commons import atomique


def empreinte(chemin: Path) -> dict:
    sha = hashlib.sha256()
    with chemin.open("rb") as entree:
        while bloc := entree.read(1024 * 1024):
            sha.update(bloc)
    return {"nom": chemin.name, "octets": chemin.stat().st_size, "sha256": sha.hexdigest()}


def coordonnees_maille(rd5: str, case: int, x: int, y: int) -> tuple[int, int]:
    match = re.fullmatch(r"([EW])(\d+)_([NS])(\d+)\.rd5", rd5)
    if not match:
        raise ValueError("Nom RD5 invalide")
    lon = int(match[2]) * (1 if match[1] == "E" else -1)
    lat = int(match[4]) * (1 if match[3] == "N" else -1)
    return (lat + case % 5) * 4 + y, (lon + case // 5) * 4 + x


def publier(mosaique: Path, donnees: Path, profils: Path, source: str, strict: bool) -> dict:
    fournisseur = providers.source(source)
    manifeste = json.loads((mosaique / "manifest.json").read_text(encoding="utf-8"))
    if (manifeste.get("format") != 2 or len(manifeste.get("fragments", [])) != 400
            or not manifeste.get("couverture") or not rd5_fragments.NOM_RD5.fullmatch(manifeste.get("rd5", ""))):
        raise ValueError("Mosaïque RD5 invalide")
    cellules = [coordonnees_maille(manifeste["rd5"], *quart) for quart in manifeste["couverture"]]
    if len(cellules) != len(set(cellules)):
        raise ValueError("Maille répétée")
    is_, js = [i for i, _ in cellules], [j for _, j in cellules]
    if len(cellules) != (max(is_) - min(is_) + 1) * (max(js) - min(js) + 1):
        raise ValueError("La couverture du paquet doit former un rectangle complet")
    zone = [min(is_) / 4, min(js) / 4, (max(is_) + 1) / 4, (max(js) + 1) / 4]
    if not fournisseur.disponible(zone):
        raise ValueError("Provider absent de cette zone")

    chemins, croisements = {}, {}
    for i, j in cellules:
        officiel = mailles.lire(donnees, source, i, j)
        osm = mailles.lire(donnees, "osm", i, j)
        for chemin in officiel["officiels"]:
            chemins[chemin["id"]] = chemin
        for franchissement in osm["franchissements"]:
            croisements[franchissement["cle"]] = franchissement
    liste = list(croisements.values())
    dossier_paquets = donnees / "paquets"
    dossier_paquets.mkdir(parents=True, exist_ok=True)
    jeton = secrets.token_hex(16)
    provisoire = dossier_paquets / ("preparation-" + jeton)
    cible = dossier_paquets / jeton
    provisoire.mkdir()
    try:
        segments, assets = [], []
        for case, x, y in manifeste["couverture"]:
            fragment = manifeste["fragments"][case * 16 + y * 4 + x]
            nom = fragment["nom"]
            if nom is None:
                continue
            if not rd5_fragments.NOM_FRAGMENT.fullmatch(nom):
                raise ValueError("Nom de fragment invalide")
            shutil.copy2(mosaique / nom, provisoire / nom)
            item = empreinte(provisoire / nom)
            if item["octets"] != fragment["octets"] or item["sha256"] != fragment["sha256"]:
                raise ValueError("Fragment altéré dans la mosaïque")
            segments.append({**item, "url": f"/api/paquets/{jeton}/{nom}"})
        for nom in ("hike2gpx.brf", "lookups.dat"):
            shutil.copy2(profils / nom, provisoire / nom)
            assets.append({**empreinte(provisoire / nom), "url": f"/api/paquets/{jeton}/{nom}"})
        atomique.ecrire_json(provisoire / "chemins-officiels.json",
                            {"troncons": list(chemins.values())}, indent=None)
        nom = "chemins-officiels.json"
        assets.append({**empreinte(provisoire / nom), "url": f"/api/paquets/{jeton}/{nom}"})
        # Reconstitue et vérifie avant publication. Cette copie sert seulement
        # au calcul de secours sur le serveur ; elle ne figure pas au téléchargement.
        rd5_fragments.assembler(manifeste, provisoire, provisoire / manifeste["rd5"])
        contenu = {"pret": True, "format": 2, "source": source, "strict": strict,
                   "zone": zone, "couverture": zone, "mailles": [list(c) for c in sorted(cellules)],
                   "assemblage": manifeste, "profil": (profils / "hike2gpx.brf").read_text(encoding="utf-8"),
                   "polylines": brouter.coupes_parametre(liste, strict=strict),
                   "franchissements": liste, "segments": segments, "assets": assets}
        atomique.ecrire_json(provisoire / "manifest.json",
                            {"fichiers": [f["nom"] for f in segments + assets]})
        atomique.ecrire_json(provisoire / "public.json", contenu)
        os.replace(provisoire, cible)
        return contenu
    finally:
        if provisoire.exists():
            shutil.rmtree(provisoire)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mosaique", type=Path)
    parser.add_argument("donnees", type=Path)
    parser.add_argument("profils", type=Path)
    parser.add_argument("--source", default="ign", choices=sorted(providers.SOURCES))
    parser.add_argument("--souple", action="store_true")
    args = parser.parse_args()
    paquet = publier(args.mosaique, args.donnees, args.profils, args.source, not args.souple)
    print(f"Paquet {paquet['source']} : {len(paquet['mailles'])} mailles, "
          f"{sum(f['octets'] for f in paquet['segments'])} octets RD5 distribués")


if __name__ == "__main__":
    main()
