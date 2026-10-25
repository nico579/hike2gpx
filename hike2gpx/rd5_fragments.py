"""Recompose sur le client une RD5 depuis des fragments de 0,25°."""
from __future__ import annotations

import hashlib
import os
import re
import struct
import zlib
from pathlib import Path

INDEX = 200
MASQUE_POSITION = (1 << 48) - 1
SOUS_INDEX = 4096
NOM_RD5 = re.compile(r"[EW]\d+_[NS]\d+\.rd5")
NOM_FRAGMENT = re.compile(r"\d{2}_[0-3]_[0-3]\.rd5q")


def _crc(valeur: bytes) -> int:
    return zlib.crc32(valeur) ^ 0xffffffff


def assembler(manifeste: dict, dossier: Path, destination: Path) -> None:
    """Vérifie chaque fragment et publie la RD5 reconstruite atomiquement."""
    fragments = manifeste.get("fragments")
    selection = manifeste.get("couverture")
    nom_rd5 = manifeste.get("rd5")
    if (manifeste.get("format") != 2 or not isinstance(fragments, list) or len(fragments) != 400
            or not isinstance(selection, list) or not NOM_RD5.fullmatch(str(nom_rd5))):
        raise ValueError("Manifeste de fragments RD5 invalide")
    try:
        entete_original = bytes.fromhex(manifeste["entete"])
        pied_original = bytes.fromhex(manifeste["pied"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Index RD5 invalide") from exc
    if (len(entete_original) != INDEX or len(pied_original) < 113
            or struct.unpack_from(">I", pied_original, 8)[0] != _crc(entete_original) ^ 2):
        raise ValueError("En-tête ou pied RD5 invalide")
    selectionnes = set()
    for brut in selection:
        if (not isinstance(brut, list) or len(brut) != 3
                or any(type(v) is not int for v in brut)
                or not 0 <= brut[0] < 25 or not 0 <= brut[1] < 4 or not 0 <= brut[2] < 4):
            raise ValueError("Couverture RD5 invalide")
        selectionnes.add(tuple(brut))
    if len(selectionnes) != len(selection):
        raise ValueError("Couverture RD5 répétée")
    dossier, destination = Path(dossier), Path(destination)
    provisoire = destination.with_name(destination.name + ".part")
    versions = [val & ~MASQUE_POSITION for val in struct.unpack(">25Q", entete_original)]
    positions, blocs, controles = [], [], []
    position = INDEX
    try:
        for case in range(25):
            caches = [b""] * 1024
            for y in range(4):
                for x in range(4):
                    fragment = fragments[case * 16 + y * 4 + x]
                    if (fragment["case"], fragment["x"], fragment["y"]) != (case, x, y):
                        raise ValueError("Ordre des fragments RD5 invalide")
                    if (case, x, y) not in selectionnes or fragment["nom"] is None:
                        continue
                    nom = fragment["nom"]
                    if not isinstance(nom, str) or not NOM_FRAGMENT.fullmatch(nom):
                        raise ValueError("Nom de fragment RD5 invalide")
                    brut = (dossier / nom).read_bytes()
                    if (len(brut) != fragment["octets"] or len(brut) < 256
                            or len(brut) > 64 * 1024 * 1024
                            or hashlib.sha256(brut).hexdigest() != fragment["sha256"]):
                        raise ValueError(f"Fragment RD5 altéré : {nom}")
                    longueurs = struct.unpack_from(">64I", brut)
                    if 256 + sum(longueurs) != len(brut):
                        raise ValueError("Longueurs de fragment RD5 invalides")
                    debut = 256
                    for dy in range(8):
                        for dx in range(8):
                            index = (y * 8 + dy) * 32 + x * 8 + dx
                            longueur = longueurs[dy * 8 + dx]
                            caches[index] = brut[debut:debut + longueur]
                            debut += longueur
            if any(caches):
                fin = SOUS_INDEX
                sous_positions = []
                for cache in caches:
                    fin += len(cache)
                    sous_positions.append(fin)
                sous_index = struct.pack(">1024I", *sous_positions)
                bloc = sous_index + b"".join(caches)
                controles.append(_crc(sous_index))
            else:
                bloc = b""
                controles.append(0)
            blocs.append(bloc)
            position += len(bloc)
            positions.append(position)
        entete = struct.pack(">25Q", *(v | p for v, p in zip(versions, positions)))
        pied = (pied_original[:8] + struct.pack(">I", _crc(entete) ^ 2)
                + struct.pack(">25I", *controles) + pied_original[112:])
        with provisoire.open("wb") as sortie:
            sortie.write(entete)
            for bloc in blocs:
                sortie.write(bloc)
            sortie.write(pied)
            sortie.flush()
            os.fsync(sortie.fileno())
        os.replace(provisoire, destination)
    finally:
        provisoire.unlink(missing_ok=True)
