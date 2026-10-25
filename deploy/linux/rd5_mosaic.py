#!/usr/bin/env python3
"""Réunit des quarts de degré issus de fabrications BRouter indépendantes."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

try:
    from .rd5_quarts import assembler
    from .rd5_shards import MASQUE_POSITION
except ImportError:  # exécution directe via SSH
    from rd5_quarts import assembler
    from rd5_shards import MASQUE_POSITION


def reunir(destination: Path, morceaux: list[tuple[Path, int, int, int]]) -> dict:
    if destination.exists():
        raise ValueError("Le dossier de mosaïque doit être neuf")
    manifestes = {}
    for dossier, _, _, _ in morceaux:
        if dossier not in manifestes:
            manifeste = json.loads((dossier / "manifest.json").read_text(encoding="utf-8"))
            if manifeste.get("format") != 2 or len(manifeste.get("fragments", [])) != 400:
                raise ValueError(f"Manifeste invalide : {dossier}")
            manifestes[dossier] = manifeste
    modele = next(iter(manifestes.values()))
    versions = bytes.fromhex(modele["entete"])
    versions = [int.from_bytes(versions[i:i + 8], "big") & ~MASQUE_POSITION
                for i in range(0, 200, 8)]
    for manifeste in manifestes.values():
        entete = bytes.fromhex(manifeste["entete"])
        autre = [int.from_bytes(entete[i:i + 8], "big") & ~MASQUE_POSITION
                 for i in range(0, 200, 8)]
        if (manifeste["rd5"] != modele["rd5"] or autre != versions
                or bytes.fromhex(manifeste["pied"])[-1:] != bytes.fromhex(modele["pied"])[-1:]):
            raise ValueError("Versions ou tuiles RD5 incompatibles")
    destination.mkdir(parents=True)
    fragments = [{"case": case, "x": x, "y": y, "nom": None, "octets": 0, "sha256": None}
                 for case in range(25) for y in range(4) for x in range(4)]
    couverture = set()
    for dossier, case, x, y in morceaux:
        cle = (case, x, y)
        if not 0 <= case < 25 or not 0 <= x < 4 or not 0 <= y < 4 or cle in couverture:
            raise ValueError(f"Quart invalide ou répété : {cle}")
        couverture.add(cle)
        fragment = manifestes[dossier]["fragments"][case * 16 + y * 4 + x]
        if (fragment["case"], fragment["x"], fragment["y"]) != cle:
            raise ValueError(f"Quart incohérent : {cle}")
        fragments[case * 16 + y * 4 + x] = fragment
        if fragment["nom"]:
            shutil.copy2(dossier / fragment["nom"], destination / fragment["nom"])
    manifeste = {"format": 2, "rd5": modele["rd5"], "entete": modele["entete"],
                 "pied": modele["pied"], "fragments": fragments,
                 "couverture": [list(cle) for cle in sorted(couverture)]}
    (destination / "manifest.json").write_text(json.dumps(manifeste, indent=2) + "\n", encoding="utf-8")
    assembler(destination, destination / modele["rd5"], couverture)
    return manifeste


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("quart", nargs="+", help="DOSSIER:CASE:X:Y")
    args = parser.parse_args()
    morceaux = []
    for valeur in args.quart:
        try:
            dossier, case, x, y = valeur.rsplit(":", 3)
            morceaux.append((Path(dossier), int(case), int(x), int(y)))
        except ValueError:
            parser.error(f"Quart invalide : {valeur}")
    manifeste = reunir(args.destination, morceaux)
    rd5 = args.destination / manifeste["rd5"]
    print(f"{len(manifeste['couverture'])} quarts, RD5 {rd5.stat().st_size} octets : {rd5}")


if __name__ == "__main__":
    main()
