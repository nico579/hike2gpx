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
import time
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


class _SansPlages(ErreurArchive):
    """Le serveur répond 200 à une demande de plage : il ne les sert pas."""


# Débit plancher, à la manière de curl --speed-limit / --speed-time : une
# connexion qui reste sous DEBIT_MIN octets par seconde pendant FENETRE_S
# secondes est abandonnée, et l'essai suivant reprend là où elle s'est arrêtée.
# Le serveur du GUGiK répartit ses connexions : le 2026-11-09 au soir, trois
# tiraient 0,3 à 0,95 Mo/s, une quatrième 18 ko/s, qui aurait tenu tout un
# powiat une demi-heure sans jamais déclencher le délai de 120 s, puisqu'elle
# avançait.
DEBIT_MIN = 50_000
FENETRE_S = 30
_LECTURE = 1 << 16


class _TropLent(OSError):
    pass


def _copier(reponse, f, horloge=time.monotonic) -> None:
    """Copie reponse dans f, et lève _TropLent (une coupure, donc reprise) si
    le débit reste sous DEBIT_MIN pendant toute une fenêtre de FENETRE_S."""
    debut, recus = horloge(), 0
    while bloc := reponse.read(_LECTURE):
        f.write(bloc)
        recus += len(bloc)
        ecoule = horloge() - debut
        if ecoule >= FENETRE_S:
            if recus / ecoule < DEBIT_MIN:
                raise _TropLent(f"moins de {DEBIT_MIN // 1000} ko/s pendant {ecoule:.0f} s")
            debut, recus = horloge(), 0


def _morceau(url: str, partie: Path, debut: int, longueur: int, ouvrir, essais: int, pause) -> None:
    """Les octets [debut, debut + longueur) de url dans partie, repris là où
    ils se sont arrêtés ; même règle que telecharger : seuls « essais » échecs
    de suite sans progrès arrêtent."""
    sans_progres = 0
    while True:
        deja = partie.stat().st_size if partie.exists() else 0
        if deja >= longueur:
            return
        if sans_progres >= essais:
            raise ErreurArchive(f"{partie.name} : plage impossible à télécharger.")
        entetes = {**AGENT, "Range": f"bytes={debut + deja}-{debut + longueur - 1}"}
        try:
            with ouvrir(urllib.request.Request(url, headers=entetes), timeout=120) as reponse:
                if getattr(reponse, "status", 200) != 206:
                    raise _SansPlages(url)
                with open(partie, "ab") as f:
                    _copier(reponse, f)
        except (OSError, http.client.HTTPException) as exc:     # coupure : l'essai suivant reprend
            journal.info("%s coupé (%s), reprise", partie.name, exc)
        apres = partie.stat().st_size if partie.exists() else 0
        sans_progres = 0 if apres > deja else sans_progres + 1
        if apres < longueur:
            pause(min(60, 5 * (sans_progres + 1)))


def _par_plages(fichier: dict, cible: Path, plages: int, ouvrir, essais: int, pause) -> None:
    """Le fichier en plages téléchargées en parallèle (cible.0, cible.1…),
    puis recollées dans cible : la méthode d'aria2c ou d'axel. Le serveur de
    l'ČÚZK bride chaque connexion (mesure du 2026-11-09 : 1,1 Mo/s sur une,
    2,5 Mo/s sur quatre ; vu de GitHub Actions, moins de 0,47 Mo/s sur une,
    et 6,7 Go non finis en 4 h). Une plage coupée reprend seule ; les plages
    restent sur disque si tout échoue, pour l'essai suivant."""
    from concurrent.futures import ThreadPoolExecutor
    taille = fichier["octets"]
    pas = -(-taille // plages)
    morceaux = [(cible.with_name(f"{cible.name}.{k}"), k * pas, min(pas, taille - k * pas))
                for k in range(plages) if k * pas < taille]
    journal.info("%s : %d plages en parallèle", cible.name, len(morceaux))
    try:
        with ThreadPoolExecutor(len(morceaux)) as groupe:
            list(groupe.map(lambda m: _morceau(fichier["url"], *m, ouvrir, essais, pause), morceaux))
    except _SansPlages:
        for partie, _, _ in morceaux:
            partie.unlink(missing_ok=True)
        raise
    with open(cible, "wb") as f:
        for partie, _, _ in morceaux:
            with open(partie, "rb") as source:
                shutil.copyfileobj(source, f, BLOC)
            partie.unlink()


def telecharger(fichier: dict, cible: Path, ouvrir=urllib.request.urlopen, essais: int = ESSAIS,
                pause=time.sleep, plages: int = 1) -> None:
    """fichier = {"url", "octets", "md5"} : téléchargé dans cible, repris là où
    il s'est arrêté (Range), puis contrôlé par son MD5 ; sans MD5 (le flux de
    l'ČÚZK n'en donne pas), par sa taille seule, l'archive zip contrôlant
    ensuite chaque fichier par son CRC. Une coupure qui a fait avancer le
    téléchargement ne compte pas : le serveur de l'ČÚZK (6,7 Go, 1 Mo/s vu de
    GitHub Actions) coupe parfois, et celui de l'IGN ferme parfois proprement
    avant la fin, sans erreur (BD TOPO, essai du 2026-10-28, R93 et R44
    abandonnées après trois coupures) : un fichier encore incomplet reprend au
    lieu de repartir de zéro. Seuls « essais » échecs de suite sans progrès
    arrêtent.

    plages > 1 : en autant de plages parallèles (_par_plages), pour un serveur
    qui bride chaque connexion ; d'un seul tenant s'il ne sert pas les plages."""
    if plages > 1 and fichier["octets"] > plages * BLOC \
            and not (cible.exists() and cible.stat().st_size == fichier["octets"]):
        try:
            _par_plages(fichier, cible, plages, ouvrir, essais, pause)
        except _SansPlages:
            journal.info("%s : pas de plages sur ce serveur, d'un seul tenant", cible.name)
    sans_progres = 0
    while sans_progres < essais:
        deja = cible.stat().st_size if cible.exists() else 0
        if deja < fichier["octets"]:
            entetes = {**AGENT, **({"Range": f"bytes={deja}-"} if deja else {})}
            try:
                with ouvrir(urllib.request.Request(fichier["url"], headers=entetes), timeout=120) as reponse:
                    mode = "ab" if deja and getattr(reponse, "status", 200) == 206 else "wb"
                    with open(cible, mode) as f:
                        _copier(reponse, f)
            except (OSError, http.client.HTTPException) as exc:     # coupure : l'essai suivant reprend
                journal.info("%s coupé (%s), reprise", cible.name, exc)
            apres = cible.stat().st_size if cible.exists() else 0
            if apres < fichier["octets"]:
                sans_progres = 0 if apres > deja else sans_progres + 1
                pause(min(60, 5 * (sans_progres + 1)))
                continue
        if fichier.get("md5"):
            h = hashlib.md5()
            with open(cible, "rb") as f:
                while bloc := f.read(BLOC):
                    h.update(bloc)
            if h.hexdigest() == fichier["md5"]:
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
