"""Relief d'une case BRouter depuis Mapterhorn : le .bef que lit le créateur de RD5.

Mapterhorn (https://mapterhorn.com) publie un relief mondial en tuiles
Terrarium : en France, le MNT de l'IGN tiré du LiDAR (le sol nu, pas la cime
des arbres comme Copernicus ou SRTM). Le zoom 12 en dérive déjà : ses pixels
font 0,6 seconde d'arc, plus fin que la seconde d'arc de BRouter.

1. Rapatrie une fois les tuiles du zoom 12 de la zone (cache sur disque).
2. Pour chaque case de 1° qui touche la zone, rééchantillonne sur la grille de
   1 seconde d'arc et écrit le fichier hgt que lit BRouter (N43E006.hgt :
   3 601 × 3 601 entiers 16 bits gros-boutistes, -32767 sans donnée).
3. Les convertit en srtm_x_y.bef avec ElevationRasterTileConverter de BRouter.
Attribution : https://mapterhorn.com/attribution (dont IGN pour la France).
"""
from __future__ import annotations

import http.client
import math
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from nico579_commons import enfants

from . import __version__, brouter

TUILES = "https://tiles.mapterhorn.com/{z}/{x}/{y}.webp"
ZOOM = 12
TAILLE = 512                  # pixels par tuile Mapterhorn
COTE = 3601                   # points par côté d'un hgt à 1 seconde d'arc
SANS_DONNEE = -32767
AGENT = {"User-Agent": f"hike2gpx/{__version__} (relief des cases BRouter)"}
PARALLELES = 4
ATTRIBUTION = "relief Mapterhorn (https://mapterhorn.com/attribution)"


class Abandon(Exception):
    pass


def pixel(lat, lon):
    """Coordonnées en pixels du zoom 12, sur tout le planisphère."""
    n = 2 ** ZOOM * TAILLE
    x = (np.asarray(lon) + 180) / 360 * n
    y = (1 - np.arcsinh(np.tan(np.radians(lat))) / math.pi) / 2 * n
    return x, y


def tuiles_zone(sud: float, ouest: float, nord: float, est: float) -> set:
    """Tuiles (x, y) du zoom 12 qui couvrent la zone, une de marge autour :
    l'interpolation lit le pixel voisin."""
    x0, y1 = (int(v // TAILLE) for v in pixel(sud, ouest))
    x1, y0 = (int(v // TAILLE) for v in pixel(nord, est))
    return {(x, y) for x in range(x0 - 1, x1 + 2) for y in range(y0 - 1, y1 + 2)}


def cache(dossier) -> Path:
    """Le cache des tuiles Mapterhorn, celui de gpx2elev (denivele.py) : une tuile
    rapatriée pour un lot sert aussi au dénivelé des parcours, et inversement.
    Le relief ne change pas : rien n'y expire."""
    return Path(dossier) / "gpx2elev" / "tiles"


ABSENTES = set()        # tuiles sans relief (la mer), en mémoire comme gpx2elev


def _fichier(cache_tuiles: Path, x: int, y: int) -> Path:
    return cache_tuiles / f"mapterhorn_{ZOOM}_{x}_{y}.webp"     # nommage de gpx2elev


def tuile(cache_tuiles: Path, x: int, y: int, voulues: set | None = None) -> np.ndarray | None:
    """Altitudes (float32, 512 × 512) d'une tuile, None si elle n'existe pas
    (mer) ou n'est pas voulue (hors de la zone : rien n'y est rapatrié)."""
    fichier = _fichier(cache_tuiles, x, y)
    if not fichier.exists():
        if (voulues is not None and (x, y) not in voulues) or (x, y) in ABSENTES:
            return None
        for essai in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(
                        TUILES.format(z=ZOOM, x=x, y=y), headers=AGENT), timeout=60) as r:
                    donnees = r.read()
                break
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    ABSENTES.add((x, y))
                    return None
                if essai == 2:
                    raise
            except (OSError, http.client.HTTPException):    # réponse coupée (IncompleteRead) comprise
                if essai == 2:
                    raise
            time.sleep(5 * (essai + 1))
        cache_tuiles.mkdir(parents=True, exist_ok=True)
        partiel = fichier.with_name(f"{fichier.name}.{os.getpid()}.part")
        partiel.write_bytes(donnees)
        partiel.replace(fichier)
    from PIL import Image
    with Image.open(fichier) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    # Terrarium (Mapzen) : altitude = R × 256 + G + B / 256 − 32768
    return rgb[..., 0] * 256 + rgb[..., 1] + rgb[..., 2] / 256 - 32768


def hgt(cache: Path, lat0: int, lon0: int, voulues: set | None = None) -> np.ndarray:
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
            t = tuile(cache, tx, ty, voulues)
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


def fichier_bef(dossier, boite: tuple) -> Path:
    """Le relief gardé d'une case entière, rangé par version de BRouter : le
    format .bef est celui de son convertisseur. Le serveur le publie sous le
    nom relief.<dossier>.<fichier> (relief.brouter-1.7.10.srtm_38_04.bef)."""
    return Path(dossier) / "relief-cases" / f"brouter-{brouter.VERSION}" / f"{nom_bef(int(boite[0]), int(boite[1]))}.bef"


def fabriquer(inst: brouter.Installation, boite: tuple, dossier: Path, cache_tuiles: Path, *,
              zone: tuple | None = None, suivi=None, continuer=None) -> Path:
    """Le relief de la case boite (sud, ouest, nord, est) dans dossier/bef,
    rendu pour fabriquer_tuiles(relief=...). zone : la partie utile de la case ;
    ailleurs, rien n'est rapatrié et le relief reste sans donnée. Les tuiles
    déjà dans le cache (un lot voisin, un dénivelé) ne sont pas redemandées."""
    suivi = suivi or (lambda etape, faites, total: None)
    continuer = continuer or (lambda: True)
    lat_sud, lon_ouest = int(boite[0]), int(boite[1])
    zone = zone or boite
    cache = cache_tuiles
    voulues = tuiles_zone(*zone)
    a_lire = sorted(xy for xy in voulues if not _fichier(cache, *xy).exists())
    with ThreadPoolExecutor(PARALLELES) as groupe:
        for k, _ in enumerate(groupe.map(lambda xy: tuile(cache, *xy, voulues) is not None, a_lire), 1):
            if not continuer():
                groupe.shutdown(cancel_futures=True)
                raise Abandon()
            suivi("relief", k, len(a_lire))

    dossier_hgt = dossier / "hgt"
    shutil.rmtree(dossier_hgt, ignore_errors=True)
    dossier_hgt.mkdir(parents=True)
    for lat in range(lat_sud, lat_sud + 5):
        for lon in range(lon_ouest, lon_ouest + 5):
            # Une case de 1° hors de la zone reste sans fichier : BRouter la lit
            # comme sans altitude.
            if lat + 1 > zone[0] and lat < zone[2] and lon + 1 > zone[1] and lon < zone[3]:
                if not continuer():
                    raise Abandon()
                hgt(cache, lat, lon, voulues).tofile(dossier_hgt / nom_hgt(lat, lon))

    sortie = dossier / "bef"
    shutil.rmtree(sortie, ignore_errors=True)
    sortie.mkdir(parents=True)
    librairies = sorted((inst.programme / "lib").glob("*.jar"))
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    r = enfants.lancer([brouter.java(), "-Xmx2g", "-cp", os.pathsep.join(str(p) for p in [inst.jar, *librairies]),
                        "btools.mapcreator.ElevationRasterTileConverter", nom_bef(lat_sud, lon_ouest),
                        str(dossier_hgt), str(sortie), "1"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       stdin=subprocess.DEVNULL, **options)
    shutil.rmtree(dossier_hgt, ignore_errors=True)
    if r.returncode:
        raise brouter.ErreurBRouter(f"Relief impossible : {(r.stderr or r.stdout).strip()[-300:]}")
    return sortie
