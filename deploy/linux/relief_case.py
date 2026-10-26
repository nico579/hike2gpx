#!/usr/bin/env python3
"""Relief d'une case BRouter depuis Mapterhorn : le .bef que lit le créateur de RD5.

  relief_case.py CASE DOSSIER INSTALLATION_BROUTER [--cache DOSSIER]

Mapterhorn (https://mapterhorn.com) publie un relief mondial en tuiles
Terrarium : en France, le MNT de l'IGN tiré du LiDAR (le sol nu, pas la cime
des arbres comme Copernicus ou SRTM). Le zoom 12 en dérive déjà : ses pixels
font 0,6 seconde d'arc, plus fin que la seconde d'arc de BRouter.

1. Rapatrie une fois les tuiles du zoom 12 de la case (cache sur disque).
2. Pour chaque case de 1°, rééchantillonne sur la grille de 1 seconde d'arc et
   écrit le fichier hgt que lit BRouter (N43E006.hgt : 3 601 × 3 601 entiers
   16 bits gros-boutistes, -32767 sans donnée).
3. Les convertit en srtm_x_y.bef avec ElevationRasterTileConverter de BRouter.
Attribution : https://mapterhorn.com/attribution (dont IGN pour la France).
"""
from __future__ import annotations

import argparse
import io
import math
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

from hike2gpx import __version__, brouter

TUILES = "https://tiles.mapterhorn.com/{z}/{x}/{y}.webp"
ZOOM = 12
TAILLE = 512                  # pixels par tuile Mapterhorn
COTE = 3601                   # points par côté d'un hgt à 1 seconde d'arc
SANS_DONNEE = -32767
AGENT = {"User-Agent": f"hike2gpx/{__version__} (relief des cases BRouter)"}
PARALLELES = 4


def pixel(lat, lon):
    """Coordonnées en pixels du zoom 12, sur tout le planisphère."""
    n = 2 ** ZOOM * TAILLE
    x = (np.asarray(lon) + 180) / 360 * n
    y = (1 - np.arcsinh(np.tan(np.radians(lat))) / math.pi) / 2 * n
    return x, y


def tuile(cache: Path, x: int, y: int) -> np.ndarray | None:
    """Altitudes (float32, 512 × 512) d'une tuile, None si elle n'existe pas (mer)."""
    fichier = cache / f"{ZOOM}-{x}-{y}.webp"
    if not fichier.exists():
        for essai in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(
                        TUILES.format(z=ZOOM, x=x, y=y), headers=AGENT), timeout=60) as r:
                    donnees = r.read()
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    fichier.write_bytes(b"")
                    return None
                if essai == 2:
                    raise
            except OSError:
                if essai == 2:
                    raise
            time.sleep(5 * (essai + 1))
        fichier.with_suffix(".part").write_bytes(donnees)
        fichier.with_suffix(".part").replace(fichier)
    if fichier.stat().st_size == 0:
        return None
    rgb = np.asarray(Image.open(fichier).convert("RGB"), dtype=np.float32)
    # Terrarium (Mapzen) : altitude = R × 256 + G + B / 256 − 32768
    return rgb[..., 0] * 256 + rgb[..., 1] + rgb[..., 2] / 256 - 32768


def hgt(cache: Path, lat0: int, lon0: int) -> np.ndarray:
    """Grille de 1 seconde d'arc de la case de 1° [lat0, lon0], rangée du nord au sud."""
    lats = lat0 + 1 - np.arange(COTE) / 3600
    lons = lon0 + np.arange(COTE) / 3600
    px, _ = pixel(lat0, lons)
    _, py = pixel(lats, lon0)
    # Un pixel de marge de chaque côté : l'interpolation lit le voisin.
    tx0, tx1 = int((px.min() - 1) // TAILLE), int((px.max() + 1) // TAILLE)
    ty0, ty1 = int((py.min() - 1) // TAILLE), int((py.max() + 1) // TAILLE)
    mosaique = np.full(((ty1 - ty0 + 1) * TAILLE, (tx1 - tx0 + 1) * TAILLE), np.nan, dtype=np.float32)
    for ty in range(ty0, ty1 + 1):
        for tx in range(tx0, tx1 + 1):
            t = tuile(cache, tx, ty)
            if t is not None:
                mosaique[(ty - ty0) * TAILLE:(ty - ty0 + 1) * TAILLE, (tx - tx0) * TAILLE:(tx - tx0 + 1) * TAILLE] = t
    # Interpolation bilinéaire, séparable : la grille est régulière en longitude
    # comme en latitude, et la projection de Mercator ne mélange pas les deux.
    gx, gy = px - tx0 * TAILLE - 0.5, py - ty0 * TAILLE - 0.5
    x0, y0 = np.floor(gx).astype(int), np.floor(gy).astype(int)
    fx, fy = (gx - x0).astype(np.float32), (gy - y0).astype(np.float32)
    lignes = mosaique[:, x0] * (1 - fx) + mosaique[:, x0 + 1] * fx
    grille = lignes[y0] * (1 - fy)[:, None] + lignes[y0 + 1] * fy[:, None]
    return np.where(np.isnan(grille), SANS_DONNEE, np.round(grille)).astype(">i2")


def nom_hgt(lat: int, lon: int) -> str:
    return f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}{'E' if lon >= 0 else 'W'}{abs(lon):03d}.hgt"


def nom_bef(lat_sud: int, lon_ouest: int) -> str:
    """Nom CGIAR que donne ElevationRasterTileConverter à une case de 5°."""
    return f"srtm_{(lon_ouest + 180) // 5 + 1:02d}_{(60 - lat_sud) // 5:02d}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("case", help="nom BRouter de la case, par exemple E5_N40")
    parser.add_argument("dossier", type=Path, help="où écrire le .bef")
    parser.add_argument("installation", type=Path, help="dossier de données contenant brouter/")
    parser.add_argument("--cache", type=Path, help="tuiles Mapterhorn déjà rapatriées")
    args = parser.parse_args()
    lon_ouest = int(args.case[1:args.case.index("_")]) * (-1 if args.case[0] == "W" else 1)
    lat_sud = int(args.case[args.case.index("_") + 2:]) * (-1 if args.case[args.case.index("_") + 1] == "S" else 1)
    cache = args.cache or args.dossier / "tuiles"
    cache.mkdir(parents=True, exist_ok=True)
    dossier_hgt = args.dossier / "hgt"
    dossier_hgt.mkdir(parents=True, exist_ok=True)

    debut = time.monotonic()
    x0, y1 = (int(v // TAILLE) for v in pixel(lat_sud, lon_ouest))
    x1, y0 = (int(v // TAILLE) for v in pixel(lat_sud + 5, lon_ouest + 5))
    a_lire = [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)
              if not (cache / f"{ZOOM}-{x}-{y}.webp").exists()]
    print(f"{(x1 - x0 + 1) * (y1 - y0 + 1)} tuiles du zoom {ZOOM}, {len(a_lire)} à rapatrier", flush=True)
    with ThreadPoolExecutor(PARALLELES) as groupe:
        for k, _ in enumerate(groupe.map(lambda xy: tuile(cache, *xy) is not None, a_lire), 1):
            if k % 500 == 0:
                print(f"  {k}/{len(a_lire)} tuiles", flush=True)
    octets = sum(f.stat().st_size for f in cache.glob("*.webp"))
    print(f"Tuiles : {octets / 1e6:.0f} Mo en {time.monotonic() - debut:.0f} s", flush=True)

    debut = time.monotonic()
    for lat in range(lat_sud, lat_sud + 5):
        for lon in range(lon_ouest, lon_ouest + 5):
            hgt(cache, lat, lon).tofile(dossier_hgt / nom_hgt(lat, lon))
    print(f"25 fichiers hgt en {time.monotonic() - debut:.0f} s", flush=True)

    inst = brouter.Installation(args.installation)
    nom = nom_bef(lat_sud, lon_ouest)
    sortie = args.dossier / "bef"
    sortie.mkdir(exist_ok=True)
    librairies = sorted((inst.programme / "lib").glob("*.jar"))
    subprocess.run([brouter.java(), "-Xmx2g", "-cp", os.pathsep.join(str(p) for p in [inst.jar, *librairies]),
                    "btools.mapcreator.ElevationRasterTileConverter", nom, str(dossier_hgt), str(sortie), "1"],
                   check=True)
    shutil.rmtree(dossier_hgt)
    bef = sortie / f"{nom}.bef"
    print(f"Relief : {bef} ({bef.stat().st_size / 1e6:.1f} Mo)", flush=True)


if __name__ == "__main__":
    main()
