"""Contrat du découpage binaire des RD5, sans téléchargement de données."""
import struct
import tempfile
import unittest
from pathlib import Path

from deploy.linux import rd5_shards


class Rd5ShardsTest(unittest.TestCase):
    def test_reconstitution_et_couverture_partielle(self):
        with tempfile.TemporaryDirectory() as racine:
            racine = Path(racine)
            source = racine / "E5_N40.rd5"
            blocs = [b"" for _ in range(25)]
            blocs[7] = b"premiere sous-case"
            blocs[13] = b"seconde sous-case"
            position, positions = 200, []
            for bloc in blocs:
                position += len(bloc)
                positions.append(position)
            entete = struct.pack(">25Q", *(42 << 48 | p for p in positions))
            pied = (struct.pack(">QI", 123456, rd5_shards._crc(entete) ^ 2)
                    + struct.pack(">25I", *([0] * 25)) + b"\x03")
            source.write_bytes(entete + b"".join(blocs) + pied)
            morceaux = racine / "morceaux"
            rd5_shards.decouper(source, morceaux)

            entier = racine / "entier.rd5"
            rd5_shards.assembler(morceaux, entier, set(range(25)))
            self.assertEqual(entier.read_bytes(), source.read_bytes())

            partiel = racine / "partiel.rd5"
            rd5_shards.assembler(morceaux, partiel, {7})
            self.assertLess(partiel.stat().st_size, entier.stat().st_size)
            donnees = partiel.read_bytes()
            index = [v & rd5_shards.MASQUE_POSITION for v in struct.unpack(">25Q", donnees[:200])]
            self.assertEqual(index[7] - index[6], len(blocs[7]))
            self.assertEqual(index[13] - index[12], 0)
            self.assertEqual(struct.unpack_from(">I", donnees, index[-1] + 8)[0],
                             rd5_shards._crc(donnees[:200]) ^ 2)

            (morceaux / "07.rd5s").write_bytes(b"altered")
            with self.assertRaisesRegex(ValueError, "altérée"):
                rd5_shards.assembler(morceaux, racine / "invalide.rd5", {7})


if __name__ == "__main__":
    unittest.main()
