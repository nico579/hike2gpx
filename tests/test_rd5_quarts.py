"""Reconstitution des microcaches BRouter groupés par quart de degré."""
import struct
import tempfile
import unittest
import shutil
from pathlib import Path

from deploy.linux import rd5_mosaic, rd5_quarts, rd5_shards


class Rd5QuartsTest(unittest.TestCase):
    def test_roundtrip_et_mail_incomplete(self):
        with tempfile.TemporaryDirectory() as racine:
            racine = Path(racine)
            source = racine / "E5_N40.rd5"
            caches = [b""] * 1024
            caches[0] = b"chemin ouest"
            caches[9] = b"chemin est"
            sous_positions, pos = [], 4096
            for cache in caches:
                pos += len(cache)
                sous_positions.append(pos)
            sous_index = struct.pack(">1024I", *sous_positions)
            bloc = sous_index + b"".join(caches)
            positions = [200 + len(bloc) if case >= 8 else 200 for case in range(25)]
            entete = struct.pack(">25Q", *(42 << 48 | p for p in positions))
            crc = [0] * 25
            crc[8] = rd5_shards._crc(sous_index)
            pied = (struct.pack(">QI", 123456, rd5_shards._crc(entete) ^ 2)
                    + struct.pack(">25I", *crc) + b"\x03")
            source.write_bytes(entete + bloc + pied)
            morceaux = racine / "morceaux"
            rd5_quarts.decouper(source, morceaux)

            entier = racine / "entier.rd5"
            rd5_quarts.assembler(morceaux, entier,
                                 {(case, x, y) for case in range(25) for x in range(4) for y in range(4)})
            self.assertEqual(entier.read_bytes(), source.read_bytes())

            partiel = racine / "partiel.rd5"
            rd5_quarts.assembler(morceaux, partiel, {(8, 0, 0)})
            self.assertLess(partiel.stat().st_size, entier.stat().st_size)
            sortie = partiel.read_bytes()
            fins = [v & rd5_shards.MASQUE_POSITION for v in struct.unpack(">25Q", sortie[:200])]
            sous_fins = struct.unpack_from(">1024I", sortie, fins[7])
            self.assertEqual(sous_fins[0] - 4096, len(caches[0]))
            self.assertEqual(sous_fins[9] - sous_fins[8], 0)
            self.assertEqual(struct.unpack_from(">I", sortie, fins[-1] + 8)[0],
                             rd5_shards._crc(sortie[:200]) ^ 2)

            autre = racine / "autre_fabrication"
            shutil.copytree(morceaux, autre)
            mosaique = racine / "mosaique"
            manifeste = rd5_mosaic.reunir(mosaique, [(morceaux, 8, 0, 0),
                                                      (autre, 8, 1, 0)])
            self.assertEqual(manifeste["couverture"], [[8, 0, 0], [8, 1, 0]])
            self.assertEqual((mosaique / "E5_N40.rd5").read_bytes(), source.read_bytes())


if __name__ == "__main__":
    unittest.main()
