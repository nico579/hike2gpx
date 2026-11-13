"""Les calques d'un lot OSM lus par des processus fils lancés par spawn
(Windows, macOS, l'application) : le même lot qu'en série."""
import sqlite3
from contextlib import closing

import pytest

pytest.importorskip("osmium")

from hike2gpx import fabrication, lot  # noqa: E402
from test_geofabrik import installer_carte  # noqa: E402
from test_franchissements import Carte  # noqa: E402

# Quatre blocs du zoom 10 (les limites passent vers 6,33° E et 43,32° N), dans la région d'essai.
ZONE = (43.25, 6.0, 43.35, 6.4)


def tuiles(mbtiles):
    with closing(sqlite3.connect(mbtiles)) as base:
        return sorted(base.execute("SELECT zoom_level, tile_column, tile_row, tile_data FROM tiles"))


@pytest.mark.spawn_reel
def test_les_calques_en_spawn_valent_ceux_en_serie(tmp_path, monkeypatch):
    # 2026-11-13 : 330 blocs à un par un, 13 min pour Montréal sur un PC à
    # 4 cœurs. Les fils de spawn ne voient pas les doublures d'un essai : de
    # vraies données, importées par pyosmium.
    carte = Carte()
    carte.chemin((100, 2000), (900, 2000))
    carte.cloture((500, 1500), (500, 2500))
    carte.chemin((28000, 3000), (29500, 3000))             # le second bloc
    dossier = tmp_path / "donnees"
    dossier.mkdir()
    installer_carte(dossier, carte)
    monkeypatch.setattr(fabrication, "processus_paralleles", lambda: 1)   # pas de fork, même sous Linux
    sorties, etapes = {}, []
    for nom, processus in (("serie", 1), ("spawn", 2)):
        monkeypatch.setattr(fabrication, "processus_spawn", lambda p=processus: p)
        sortie = tmp_path / nom
        sortie.mkdir()
        fabrication._calques(dossier, "E5_N40", lot.boite_case("E5_N40"), ZONE, sortie, "essai",
                             lambda etape, *a: etapes.append(etape), lambda: True)
        sorties[nom] = tuiles(sortie / "calques.mbtiles")
    assert "calques en parallèle (2 processus)" in etapes
    assert len(lot.blocs(*ZONE)) > 1, "plusieurs blocs, à répartir entre les fils"
    assert sorties["serie"], "des tuiles, sinon l'essai ne compare rien"
    assert sorties["spawn"] == sorties["serie"]
