#!/usr/bin/env python3
"""Prototype : distribuer une RD5 par paquets de 0,25° (8 × 8 microcaches)."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

try:
    from .rd5_shards import INDEX, MASQUE_POSITION, _crc, _sha256
except ImportError:  # exécution directe via SSH sur la VM
    from rd5_shards import INDEX, MASQUE_POSITION, _crc, _sha256

DIVISEUR = 32
PAR_QUART = 8
SOUS_INDEX = DIVISEUR * DIVISEUR * 4


def _indices_quart(x: int, y: int):
    for dy in range(PAR_QUART):
        for dx in range(PAR_QUART):
            yield (y * PAR_QUART + dy) * DIVISEUR + x * PAR_QUART + dx


def decouper(source: Path, destination: Path) -> dict:
    destination.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as entree:
        entete = entree.read(INDEX)
        if len(entete) != INDEX:
            raise ValueError("Index RD5 incomplet")
        positions = [v & MASQUE_POSITION for v in struct.unpack(">25Q", entete)]
        if positions != sorted(positions) or positions[0] < INDEX:
            raise ValueError("Index RD5 invalide")
        entree.seek(positions[-1])
        pied = entree.read()
        if len(pied) < 113 or struct.unpack_from(">I", pied, 8)[0] != _crc(entete) ^ 2:
            raise ValueError("RD5 nouvelle génération attendue")
        fragments = []
        debut = INDEX
        for case, fin in enumerate(positions):
            entree.seek(debut)
            bloc = entree.read(fin - debut)
            debut = fin
            caches = [b""] * (DIVISEUR * DIVISEUR)
            if bloc:
                if len(bloc) < SOUS_INDEX:
                    raise ValueError("Sous-index RD5 incomplet")
                fins = struct.unpack_from(">1024I", bloc)
                if list(fins) != sorted(fins) or fins[0] < SOUS_INDEX or fins[-1] != len(bloc):
                    raise ValueError("Sous-index RD5 invalide")
                precedent = SOUS_INDEX
                caches = []
                for position in fins:
                    caches.append(bloc[precedent:position])
                    precedent = position
            for y in range(4):
                for x in range(4):
                    parties = [caches[i] for i in _indices_quart(x, y)]
                    nom = f"{case:02d}_{x}_{y}.rd5q" if any(parties) else None
                    if nom:
                        contenu = struct.pack(">64I", *(len(partie) for partie in parties)) + b"".join(parties)
                        (destination / nom).write_bytes(contenu)
                    else:
                        contenu = b""
                    fragments.append({"case": case, "x": x, "y": y, "nom": nom,
                                      "octets": len(contenu),
                                      "sha256": hashlib.sha256(contenu).hexdigest() if nom else None})
    manifeste = {"format": 2, "rd5": source.name, "entete": entete.hex(),
                 "pied": pied.hex(), "fragments": fragments, "sha256": _sha256(source)}
    (destination / "manifest.json").write_text(json.dumps(manifeste, indent=2) + "\n", encoding="utf-8")
    return manifeste


def assembler(dossier: Path, destination: Path, quarts: set[tuple[int, int, int]]) -> None:
    manifeste = json.loads((dossier / "manifest.json").read_text(encoding="utf-8"))
    if manifeste.get("format") != 2 or len(manifeste.get("fragments", [])) != 400:
        raise ValueError("Manifeste RD5 invalide")
    original = bytes.fromhex(manifeste["entete"])
    pied_original = bytes.fromhex(manifeste["pied"])
    versions = [v & ~MASQUE_POSITION for v in struct.unpack(">25Q", original)]
    blocs, fins, controles = [], [], []
    position = INDEX
    for case in range(25):
        caches = [b""] * (DIVISEUR * DIVISEUR)
        for y in range(4):
            for x in range(4):
                fragment = manifeste["fragments"][case * 16 + y * 4 + x]
                if (fragment["case"], fragment["x"], fragment["y"]) != (case, x, y):
                    raise ValueError("Ordre des paquets invalide")
                if (case, x, y) not in quarts or not fragment["nom"]:
                    continue
                contenu = (dossier / fragment["nom"]).read_bytes()
                if len(contenu) != fragment["octets"] or hashlib.sha256(contenu).hexdigest() != fragment["sha256"]:
                    raise ValueError("Paquet RD5 altéré")
                longueurs = struct.unpack_from(">64I", contenu)
                if 256 + sum(longueurs) != len(contenu):
                    raise ValueError("Longueur du paquet RD5 invalide")
                debut = 256
                for index, longueur in zip(_indices_quart(x, y), longueurs):
                    caches[index] = contenu[debut:debut + longueur]
                    debut += longueur
        if any(caches):
            sous_positions = []
            sous_position = SOUS_INDEX
            for cache in caches:
                sous_position += len(cache)
                sous_positions.append(sous_position)
            sous_index = struct.pack(">1024I", *sous_positions)
            bloc = sous_index + b"".join(caches)
            controles.append(_crc(sous_index))
        else:
            bloc = b""
            controles.append(0)
        blocs.append(bloc)
        position += len(bloc)
        fins.append(position)
    entete = struct.pack(">25Q", *(v | p for v, p in zip(versions, fins)))
    pied = (pied_original[:8] + struct.pack(">I", _crc(entete) ^ 2)
            + struct.pack(">25I", *controles) + pied_original[112:])
    with destination.open("wb") as sortie:
        sortie.write(entete)
        for bloc in blocs:
            sortie.write(bloc)
        sortie.write(pied)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sous = parser.add_subparsers(dest="action", required=True)
    split = sous.add_parser("decouper")
    split.add_argument("source", type=Path)
    split.add_argument("destination", type=Path)
    join = sous.add_parser("assembler")
    join.add_argument("dossier", type=Path)
    join.add_argument("destination", type=Path)
    join.add_argument("quarts", help="'tous' ou case:x:y séparés par des virgules")
    args = parser.parse_args()
    if args.action == "decouper":
        resultat = decouper(args.source, args.destination)
        fragments = [f for f in resultat["fragments"] if f["nom"]]
        print(f"{len(fragments)} paquets non vides ; maximum {max(f['octets'] for f in fragments)} octets")
    else:
        quarts = ({(c, x, y) for c in range(25) for x in range(4) for y in range(4)}
                  if args.quarts == "tous" else {tuple(map(int, q.split(":"))) for q in args.quarts.split(",")})
        if any(len(q) != 3 or not 0 <= q[0] < 25 or not 0 <= q[1] < 4 or not 0 <= q[2] < 4
               for q in quarts):
            parser.error("Quart invalide")
        assembler(args.dossier, args.destination, quarts)
        print(f"RD5 reconstituée : {args.destination} ({args.destination.stat().st_size} octets)")


if __name__ == "__main__":
    main()
