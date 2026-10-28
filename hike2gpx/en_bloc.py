"""Outils communs aux lectures en bloc des fournisseurs nationaux.

Une case entière se fabrique sur le serveur à partir d'un téléchargement
massif par pays (archives régionales de la BD TOPO, GeoPackage national de
ZABAGED…) plutôt que du service web tuile par tuile. Chaque fournisseur a son
module (bdtopo_regions, zabaged_national) ; ce qui ne dépend pas du pays vit
ici : le téléchargement repris et contrôlé, la lecture d'une emprise dans une
table GeoPackage par son index RTree.
"""
from __future__ import annotations

import hashlib
import http.client
import logging
import shutil
import sqlite3
import urllib.request
from contextlib import closing
from pathlib import Path

from . import __version__

journal = logging.getLogger(__name__)
AGENT = {"User-Agent": f"hike2gpx/{__version__} (lecture en bloc)"}
BLOC = 1 << 20
ESSAIS = 3


class ErreurArchive(RuntimeError):
    pass


def telecharger(fichier: dict, cible: Path, ouvrir=urllib.request.urlopen, essais: int = ESSAIS) -> None:
    """fichier = {"url", "octets", "md5" ou "sha256"} : téléchargé dans cible,
    repris là où il s'est arrêté (Range), puis contrôlé par son empreinte (le
    SHA-256 du catalogue STAC de swisstopo, le MD5 de l'IGN) ; sans empreinte (le flux de
    l'ČÚZK n'en donne pas), par sa taille seule, l'archive zip contrôlant
    ensuite chaque fichier par son CRC. Une coupure qui a fait avancer le
    téléchargement ne compte pas : le serveur de l'ČÚZK (6,7 Go, 1 Mo/s vu de
    GitHub Actions) coupe parfois ; seuls « essais » échecs de suite sans
    progrès arrêtent."""
    sans_progres = 0
    while sans_progres < essais:
        deja = cible.stat().st_size if cible.exists() else 0
        if deja < fichier["octets"]:
            entetes = {**AGENT, **({"Range": f"bytes={deja}-"} if deja else {})}
            try:
                with ouvrir(urllib.request.Request(fichier["url"], headers=entetes), timeout=120) as reponse:
                    mode = "ab" if deja and getattr(reponse, "status", 200) == 206 else "wb"
                    with open(cible, mode) as f:
                        shutil.copyfileobj(reponse, f, BLOC)
            except (OSError, http.client.HTTPException) as exc:     # coupure : l'essai suivant reprend
                apres = cible.stat().st_size if cible.exists() else 0
                sans_progres = 0 if apres > deja else sans_progres + 1
                journal.info("%s coupé à %.0f Mo (%s), reprise", cible.name, apres / 1e6, exc)
                continue
        algorithme = next((a for a in ("sha256", "md5") if fichier.get(a)), None)
        if algorithme:
            h = hashlib.new(algorithme)
            with open(cible, "rb") as f:
                while bloc := f.read(BLOC):
                    h.update(bloc)
            if h.hexdigest() == fichier[algorithme]:
                return
        elif cible.stat().st_size == fichier["octets"]:
            return
        cible.unlink()                  # contenu faux : on repart de zéro
        sans_progres += 1
    raise ErreurArchive(f"{cible.name} : téléchargement impossible ou altéré.")


def lignes_gpkg(gpkg, table: str, colonnes: tuple, epsg: int, sud: float, ouest: float, nord: float, est: float,
                *, geometrie: str = "geom", cle: str = "fid", filtre: str = "", valeurs: tuple = ()) -> list:
    """[(valeurs des colonnes, rang de la partie, [[lat, lon], …])] des lignes
    d'une table GeoPackage qui touchent l'emprise, entières, lues par son index
    RTree (rtree_<table>_<geometrie>, dont les id sont la clé de la table).
    filtre : une condition SQL de plus sur la table « t », avec ses valeurs.
    Le passage de la projection du fichier au GPS se fait par rasterio (GDAL
    et PROJ), déjà embarqué pour le dénivelé, en un seul appel pour tous les
    points de l'emprise."""
    import numpy as np
    from rasterio.warp import transform as reprojeter
    from shapely import from_wkb, get_coordinates, get_parts

    bord = [(ouest + (est - ouest) * k / 8, la) for la in (sud, nord) for k in range(9)]
    bord += [(lo, sud + (nord - sud) * k / 8) for lo in (ouest, est) for k in range(9)]
    xs, ys = reprojeter("EPSG:4326", f"EPSG:{epsg}", [lo for lo, _ in bord], [la for _, la in bord])
    choix = ", ".join(f't."{c}"' for c in colonnes)
    requete = (f'SELECT {choix}{", " if colonnes else ""}t."{geometrie}" FROM "rtree_{table}_{geometrie}" r '
               f'JOIN "{table}" t ON t."{cle}" = r.id '
               f"WHERE r.minx <= ? AND r.maxx >= ? AND r.miny <= ? AND r.maxy >= ?")
    if filtre:
        requete += f" AND ({filtre})"
    # En-tête GeoPackage avant le WKB : 8 octets, puis l'enveloppe, de taille
    # donnée par les bits 1 à 3 du quatrième octet.
    tailles = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}
    lues, morceaux = [], []
    with closing(sqlite3.connect(f"file:{Path(gpkg).resolve().as_posix()}?mode=ro", uri=True)) as base:
        for *attributs, blob in base.execute(requete, [max(xs), min(xs), max(ys), min(ys), *valeurs]):
            if not blob:
                continue
            for k, ligne in enumerate(get_parts(from_wkb(blob[8 + tailles[(blob[3] >> 1) & 7]:]))):
                points = get_coordinates(ligne)        # x, y dans la projection du fichier, sans l'altitude
                if len(points) >= 2:
                    lues.append((tuple(attributs), k))
                    morceaux.append(points)
    if not morceaux:
        return []
    tous = np.concatenate(morceaux)
    lons, lats = reprojeter(f"EPSG:{epsg}", "EPSG:4326", tous[:, 0].tolist(), tous[:, 1].tolist())
    resultat, debut = [], 0
    for (attributs, k), points in zip(lues, morceaux):
        fin = debut + len(points)
        resultat.append((attributs, k, [[round(la, 7), round(lo, 7)] for lo, la in zip(lons[debut:fin], lats[debut:fin])]))
        debut = fin
    return resultat
