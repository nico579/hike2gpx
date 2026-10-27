import numpy as np
from PIL import Image

from hike2gpx import relief


def terrarium(altitude: float) -> Image.Image:
    v = altitude + 32768
    r, g = divmod(int(v), 256)
    return Image.new("RGB", (512, 512), (r, g, int((v - int(v)) * 256)))


def test_noms_des_fichiers_lus_par_brouter():
    assert relief.nom_bef(40, 5) == "srtm_38_04"            # case E5_N40
    assert relief.nom_bef(45, -5) == "srtm_36_03"           # case W5_N45
    assert relief.nom_hgt(43, 6) == "N43E006.hgt"
    assert relief.nom_hgt(-1, -10) == "S01W010.hgt"


def test_hgt_decode_terrarium_sur_la_grille_d_une_seconde(tmp_path):
    # Toutes les tuiles du cache à 812,5 m, sauf une colonne de tuiles absente (la mer).
    x_mer = int(relief.pixel(43.5, 6.5)[0] // relief.TAILLE)
    x0, y1 = (int(v // relief.TAILLE) for v in relief.pixel(42.9, 5.9))
    x1, y0 = (int(v // relief.TAILLE) for v in relief.pixel(44.1, 7.1))
    presentes = set()
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            if x != x_mer:
                terrarium(812.5).save(tmp_path / f"mapterhorn_12_{x}_{y}.webp", lossless=True)
                presentes.add((x, y))
    grille = relief.hgt(tmp_path, 43, 6, presentes)
    assert grille.shape == (relief.COTE, relief.COTE) and grille.dtype == np.dtype(">i2")
    assert grille[0, 0] == 812 or grille[0, 0] == 813
    assert (grille == relief.SANS_DONNEE).any(), "la colonne de mer reste sans donnée"
    assert set(np.unique(grille)) <= {812, 813, relief.SANS_DONNEE}
