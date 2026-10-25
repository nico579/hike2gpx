#!/usr/bin/env python3
"""Découpe une RD5 en sous-cases natives de 1° et la recompose localement.

Une case absente reste explicitement absente dans le manifeste. Le fichier
recomposé ne doit servir au routage que dans une couverture téléchargée et
contrôlée par le client : BRouter voit sinon une case manquante comme vide.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path

INDEX = 200
MASQUE_POSITION = (1 << 48) - 1


def _crc(donnees: bytes) -> int:
    # btools.util.Crc32 démarre à 0xffffffff sans inversion finale.
    return zlib.crc32(donnees) ^ 0xffffffff


def _sha256(chemin: Path) -> str:
    empreinte = hashlib.sha256()
    with chemin.open("rb") as entree:
        while bloc := entree.read(1024 * 1024):
            empreinte.update(bloc)
    return empreinte.hexdigest()


def decouper(source: Path, destination: Path) -> dict:
    destination.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as entree:
        entete = entree.read(INDEX)
        if len(entete) != INDEX:
            raise ValueError("Index RD5 incomplet")
        valeurs = struct.unpack(">25Q", entete)
        positions = [valeur & MASQUE_POSITION for valeur in valeurs]
        if positions != sorted(positions) or positions[0] < INDEX:
            raise ValueError("Index RD5 invalide")
        entree.seek(positions[-1])
        pied = entree.read()
        if len(pied) < 112 or struct.unpack_from(">I", pied, 8)[0] not in (
                _crc(entete), _crc(entete) ^ 2):
            raise ValueError("Pied ou somme de contrôle RD5 invalide")
        fragments = []
        debut = INDEX
        for numero, fin in enumerate(positions):
            entree.seek(debut)
            bloc = entree.read(fin - debut)
            if len(bloc) != fin - debut:
                raise ValueError("Sous-case RD5 incomplète")
            nom = f"{numero:02d}.rd5s" if bloc else None
            if nom:
                (destination / nom).write_bytes(bloc)
            fragments.append({"case": numero, "nom": nom, "octets": len(bloc),
                              "sha256": hashlib.sha256(bloc).hexdigest() if bloc else None})
            debut = fin
    manifeste = {"format": 1, "rd5": source.name, "entete": entete.hex(),
                 "pied": pied.hex(), "fragments": fragments,
                 "sha256": _sha256(source)}
    (destination / "manifest.json").write_text(json.dumps(manifeste, indent=2) + "\n", encoding="utf-8")
    return manifeste


def assembler(dossier: Path, destination: Path, cases: set[int]) -> None:
    manifeste = json.loads((dossier / "manifest.json").read_text(encoding="utf-8"))
    if manifeste.get("format") != 1 or len(manifeste.get("fragments", [])) != 25:
        raise ValueError("Manifeste RD5 invalide")
    entete_origine = bytes.fromhex(manifeste["entete"])
    pied_origine = bytes.fromhex(manifeste["pied"])
    if len(entete_origine) != INDEX or len(pied_origine) < 112:
        raise ValueError("Index ou pied RD5 invalide")
    versions = [valeur & ~MASQUE_POSITION for valeur in struct.unpack(">25Q", entete_origine)]
    entetes_crc = struct.unpack_from(">25I", pied_origine, 12)
    morceaux, positions, crc = [], [], []
    position = INDEX
    for numero, fragment in enumerate(manifeste["fragments"]):
        if fragment["case"] != numero:
            raise ValueError("Ordre des sous-cases invalide")
        bloc = b""
        if numero in cases and fragment["nom"]:
            bloc = (dossier / fragment["nom"]).read_bytes()
            if len(bloc) != fragment["octets"] or hashlib.sha256(bloc).hexdigest() != fragment["sha256"]:
                raise ValueError(f"Sous-case {numero} altérée")
        morceaux.append(bloc)
        position += len(bloc)
        positions.append(position)
        crc.append(entetes_crc[numero] if bloc else 0)
    entete = struct.pack(">25Q", *(version | position for version, position in zip(versions, positions)))
    pied = pied_origine[:8] + struct.pack(">I", _crc(entete) ^
            (struct.unpack_from(">I", pied_origine, 8)[0] ^ _crc(entete_origine)))
    pied += struct.pack(">25I", *crc) + pied_origine[112:]
    with destination.open("wb") as sortie:
        sortie.write(entete)
        for bloc in morceaux:
            sortie.write(bloc)
        sortie.write(pied)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sous = parser.add_subparsers(dest="action", required=True)
    decoupe = sous.add_parser("decouper")
    decoupe.add_argument("source", type=Path)
    decoupe.add_argument("destination", type=Path)
    assemble = sous.add_parser("assembler")
    assemble.add_argument("dossier", type=Path)
    assemble.add_argument("destination", type=Path)
    assemble.add_argument("cases", help="indices 0..24 séparés par une virgule, ou 'toutes'")
    args = parser.parse_args()
    if args.action == "decouper":
        resultat = decouper(args.source, args.destination)
        print(f"{resultat['rd5']} : {sum(bool(f['nom']) for f in resultat['fragments'])} sous-cases non vides")
    else:
        cases = set(range(25)) if args.cases == "toutes" else {int(v) for v in args.cases.split(",")}
        if any(v < 0 or v >= 25 for v in cases):
            parser.error("Indice de sous-case hors de 0..24")
        assembler(args.dossier, args.destination, cases)
        print(f"RD5 reconstituée : {args.destination} ({args.destination.stat().st_size} octets)")


if __name__ == "__main__":
    main()
