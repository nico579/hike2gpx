#!/usr/bin/env python3
"""Préparation séquentielle des zones, par SSH ou timer systemd."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from hike2gpx import franchissements, providers


def ecrire_json(chemin: Path, donnees: dict):
    temporaire = chemin.with_suffix(".tmp")
    temporaire.write_text(json.dumps(donnees, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporaire, chemin)


def zones_valides(configuration: dict) -> list[dict]:
    zones = configuration.get("zones")
    if not isinstance(zones, list):
        raise ValueError("La configuration doit contenir une liste zones.")
    identifiants = set()
    for zone in zones:
        if not isinstance(zone, dict) or not isinstance(zone.get("id"), str) or not zone["id"]:
            raise ValueError("Chaque zone exige un id.")
        if zone["id"] in identifiants:
            raise ValueError(f"Identifiant dupliqué : {zone['id']}")
        identifiants.add(zone["id"])
        source = providers.source(zone.get("source"))
        if source.pays != zone.get("pays"):
            raise ValueError(f"Pays incompatible avec {source.cle} : {zone['id']}")
        bornes = zone.get("zone")
        if (not isinstance(bornes, list) or len(bornes) != 4
                or not all(isinstance(v, (int, float)) for v in bornes)
                or not (-90 <= bornes[0] < bornes[2] <= 90 and -180 <= bornes[1] < bornes[3] <= 180)
                or not source.disponible(bornes)
                or len(franchissements.tuiles_zone(*bornes)) > 100):
            raise ValueError(f"Emprise invalide : {zone['id']}")
        jours = zone.get("renouvellement_jours", 30)
        if type(jours) is not int or not 1 <= jours <= 365:
            raise ValueError(f"Cadence invalide : {zone['id']}")
        if not isinstance(zone.get("modes"), list) or not set(zone["modes"]) <= {"strict", "souple"} or not zone["modes"]:
            raise ValueError(f"Modes invalides : {zone['id']}")
    return zones


def nettoyer_paquets(racine: Path, zones: list[dict], maintenant: float | None = None,
                    grace_s: int = 86400) -> int:
    """Retire les anciens paquets remplacés, après un délai pour les téléchargements en cours."""
    maintenant = time.time() if maintenant is None else maintenant
    attendues = {(z["source"], tuple(z["zone"]), mode == "strict")
                 for z in zones for mode in z["modes"]}
    paquets = racine / "paquets"
    if not paquets.is_dir():
        return 0
    groupes: dict[tuple, list[Path]] = {}
    for dossier in paquets.iterdir():
        if (not dossier.is_dir() or dossier.is_symlink()
                or not re.fullmatch(r"[0-9a-f]{32}", dossier.name)):
            continue
        try:
            manifeste = json.loads((dossier / "public.json").read_text(encoding="utf-8"))
            cle = (manifeste["source"], tuple(manifeste["zone"]), manifeste["strict"])
            if cle in attendues and manifeste.get("pret") is True:
                groupes.setdefault(cle, []).append(dossier)
        except (OSError, ValueError, KeyError, TypeError):
            continue
    supprimes = 0
    for dossiers in groupes.values():
        dossiers.sort(key=lambda d: d.stat().st_mtime, reverse=True)
        for dossier in dossiers[1:]:
            if maintenant - dossier.stat().st_mtime >= grace_s:
                shutil.rmtree(dossier)
                supprimes += 1
    return supprimes


def main(argv=None) -> int:
    import fcntl  # Linux uniquement ; la validation de configuration reste testable partout.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("/etc/hike2gpx/zones.json"))
    parser.add_argument("--zone", help="un seul identifiant de zone")
    parser.add_argument("--all", action="store_true", help="forcer toutes les zones sélectionnées")
    args = parser.parse_args(argv)
    configuration = json.loads(args.config.read_text(encoding="utf-8"))
    zones = zones_valides(configuration)
    if args.zone:
        zones = [z for z in zones if z["id"] == args.zone]
        if not zones:
            parser.error(f"zone inconnue : {args.zone}")
    racine = Path(os.environ.get("HIKE2GPX_HOME", "/var/lib/hike2gpx"))
    racine.mkdir(parents=True, exist_ok=True)
    with (racine / "refresh.lock").open("w") as verrou:
        try:
            fcntl.flock(verrou, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Une préparation de zones est déjà en cours.", file=sys.stderr)
            return 1
        etat_path = racine / "refresh.json"
        etat = json.loads(etat_path.read_text(encoding="utf-8")) if etat_path.exists() else {}
        erreurs = 0
        for zone in zones:
            for mode in zone["modes"]:
                cle = f"{zone['id']}:{mode}"
                precedent = etat.get(cle, {})
                jours = zone.get("renouvellement_jours", 30)
                # Les zones lentes ne repartent pas trop souvent ; la fréquence
                # reste au minimum celle demandée par l'administrateur.
                delai = max(jours * 86400, 10 * precedent.get("duree_s", 0))
                if not args.all and time.time() - precedent.get("succes_a", 0) < delai:
                    continue
                commande = ["hike2gpx", "preparer-zone", *(str(v) for v in zone["zone"]),
                            "--source", zone["source"]]
                if mode == "souple":
                    commande.append("--non-strict")
                debut = time.time()
                print(f"Préparation {cle} : {commande}", flush=True)
                resultat = subprocess.run(commande, check=False)
                duree = round(time.time() - debut, 1)
                if resultat.returncode:
                    erreurs += 1
                    etat[cle] = {**precedent, "echec_a": time.time(), "code": resultat.returncode,
                                 "derniere_duree_s": duree}
                else:
                    etat[cle] = {"succes_a": time.time(), "duree_s": duree,
                                 "prochaine_a": time.time() + max(jours * 86400, 10 * duree)}
                ecrire_json(etat_path, etat)
                if resultat.returncode == 0:
                    nettoyes = nettoyer_paquets(racine, zones)
                    if nettoyes:
                        print(f"{nettoyes} ancien(s) paquet(s) supprimé(s)", flush=True)
                print(f"{cle} : code {resultat.returncode}, {duree} s", flush=True)
        # Le timer quotidien purge également les paquets arrivés au délai de
        # grâce lorsqu'aucune zone n'a besoin d'être recalculée ce jour-là.
        nettoyes = nettoyer_paquets(racine, zones)
        if nettoyes:
            print(f"{nettoyes} ancien(s) paquet(s) supprimé(s)", flush=True)
        return 1 if erreurs else 0


if __name__ == "__main__":
    sys.exit(main())
