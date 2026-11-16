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
import threading
import time
import sqlite3
import urllib.error
import urllib.request
import zipfile
import zlib
from contextlib import closing
from pathlib import Path

from . import __version__

journal = logging.getLogger(__name__)
AGENT = {"User-Agent": f"hike2gpx/{__version__} (lecture en bloc)"}
BLOC = 1 << 20
ESSAIS = 3


class ErreurArchive(RuntimeError):
    pass


def lire(url: str, analyser, *, entetes=None, ouvrir=None, pause=None, essais: int = ESSAIS,
         pause_s: float = 5.0, delai_s: float = 60, nom: str = "") :
    """analyser(corps) d'une petite réponse : un flux ATOM (ET.fromstring), un
    catalogue JSON (json.loads). Une erreur 5xx ou 429, un délai, une coupure
    ou un document tronqué se retentent, essais fois, après pause_s, 2 × pause_s… ;
    une autre erreur 4xx ne guérit pas et remonte tout de suite. La dernière
    erreur remonte telle quelle. ouvrir et pause : urlopen et time.sleep, lus
    à l'appel (les essais les remplacent)."""
    ouvrir = ouvrir or urllib.request.urlopen
    pause = pause or time.sleep
    derniere = None
    for essai in range(essais):
        try:
            with ouvrir(urllib.request.Request(url, headers=entetes or AGENT), timeout=delai_s) as reponse:
                return analyser(reponse.read())
        except urllib.error.HTTPError as exc:
            if exc.code < 500 and exc.code != 429:
                raise
            derniere = exc
        except (OSError, ValueError, SyntaxError, http.client.HTTPException) as exc:
            # délai, coupure, JSON tronqué (ValueError), XML tronqué (ET.ParseError, un SyntaxError)
            derniere = exc
        if essai < essais - 1:
            journal.info("%s : essai %d en échec (%s), nouvel essai", nom or url, essai + 1, derniere)
            pause(pause_s * (essai + 1))
    raise derniere


_verrous_global = threading.Lock()
_verrous = {}


def verrou(cle) -> threading.Lock:
    """Le verrou de cette clé, le même à chaque appel : deux fils qui
    téléchargent la même chose (un powiat, une tuile) le font l'un après
    l'autre, le second trouvant le travail du premier."""
    with _verrous_global:
        return _verrous.setdefault(cle, threading.Lock())


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


def taille(url: str, ouvrir=urllib.request.urlopen) -> int:
    """La taille d'un fichier distant (HEAD, Content-Length). Sans en-tête,
    une erreur : 0 passait pour un fichier vide, et le téléchargement levait
    ensuite FileNotFoundError (audit A03/A04, 2026-11-13). La seule copie,
    pour les quatre fournisseurs nationaux."""
    with ouvrir(urllib.request.Request(url, headers=AGENT, method="HEAD"), timeout=60) as reponse:
        longueur = (getattr(reponse, "headers", None) or {}).get("Content-Length")
    try:
        octets = int(longueur)
    except (TypeError, ValueError):
        octets = 0
    if octets <= 0:
        raise ErreurArchive(f"{url} : taille inconnue (pas de Content-Length).")
    return octets


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
    if not isinstance(fichier.get("octets"), int) or fichier["octets"] <= 0:
        # Une archive nationale n'est jamais vide : sans taille, rien ne se
        # télécharge ni ne se contrôle (audit A03).
        raise ErreurArchive(f"{cible.name} : taille inconnue, téléchargement refusé.")
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
            # Les indicateurs 5 à 7 sont réservés : un message, plutôt qu'un
            # KeyError au milieu de la lecture (audit A11).
            enveloppe = tailles.get((blob[3] >> 1) & 7) if len(blob) >= 8 else None
            if enveloppe is None:
                raise ErreurArchive(f"{Path(gpkg).name} : géométrie GeoPackage illisible dans {table}.")
            for k, ligne in enumerate(get_parts(from_wkb(blob[8 + enveloppe:]))):
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


# --- Fabrique commune des lecteurs nationaux (audit D2, D3, D10, D12, D13) ---
# BD TOPO par régions, BDOT10k par powiats, Basis-DLM par Länder, swissTLM3D
# et ZABAGED suivent la même séquence : téléchargement, extraction, base
# allégée aux seuls chemins, purge des éditions plus anciennes.

def base_reduite(base: Path, anciens: str, fabriquer) -> Path:
    """La base allégée base, fabriquée une fois : fabriquer(travail, cible)
    télécharge et réduit dans un dossier de travail, effacé ensuite quoi qu'il
    arrive, et cible ne prend le nom de base qu'achevée. Les bases plus
    anciennes de la même source (anciens, un motif glob à côté de base) sont
    effacées ensuite."""
    base = Path(base)
    if base.is_file():
        return base
    travail = base.parent / f".{base.name}"
    try:
        travail.mkdir(parents=True, exist_ok=True)
        cible = travail / base.name
        fabriquer(travail, cible)
        cible.replace(base)
    finally:
        shutil.rmtree(travail, ignore_errors=True)
    for ancien in base.parent.glob(anciens):
        if ancien != base and ancien.is_file():
            ancien.unlink()
    return base


def extraire(archive: Path, dossier: Path, choisir) -> list:
    """Les membres de l'archive que retient choisir({nom: ZipInfo}) -> [ZipInfo],
    décompressés à plat dans dossier ; zipfile contrôle le CRC en lisant. Les
    noms sont comparés en « / » : une archive faite sous Windows garde des
    « \\ » que zipfile ne convertit qu'en lisant sous Windows (swissTLM3D,
    essai 42644919578). Une archive altérée lève ErreurArchive."""
    sortie = []
    try:
        with zipfile.ZipFile(archive) as z:
            for membre in choisir({m.filename.replace("\\", "/"): m for m in z.infolist()}):
                dossier.mkdir(parents=True, exist_ok=True)
                cible = dossier / Path(membre.filename.replace("\\", "/")).name
                with z.open(membre) as source, open(cible, "wb") as f:
                    shutil.copyfileobj(source, f, BLOC)
                sortie.append(cible)
    except (zipfile.BadZipFile, zlib.error, EOFError) as exc:
        raise ErreurArchive(f"{archive.name} : archive altérée ({exc}).") from exc
    return sortie


def garder_couches(gpkg: Path, cible: Path, couches, *, geometrie: str, cle: str) -> int:
    """Les tables gardées d'un GeoPackage complet, copiées dans la base cible
    avec leur index RTree, pour lignes_gpkg. couches : [(source, table,
    colonnes, condition, parametres)] ; colonnes déclare les colonnes gardées
    hors clé et géométrie (« cleabs TEXT, nature TEXT ») ; condition filtre les
    lignes (la clause WHERE, sans le mot, « » pour toutes), et l'index ne garde
    alors que les lignes copiées. La clé reste la clé primaire : l'index RTree
    renvoie des clés, et un CREATE TABLE … AS SELECT l'aurait réduite à une
    colonne ordinaire, que chaque lecture d'emprise aurait parcourue en
    entier. Rend le nombre de lignes gardées."""
    gardes = 0
    with closing(sqlite3.connect(str(cible), uri=True)) as base:     # uri : ATTACH en lecture seule
        base.execute("ATTACH DATABASE ? AS complet", (f"file:{Path(gpkg).resolve().as_posix()}?mode=ro",))
        for source, table, colonnes, condition, parametres in couches:
            noms = ", ".join(c.split()[0] for c in colonnes.split(","))
            rtree, rtree_source = f"rtree_{table}_{geometrie}", f"rtree_{source}_{geometrie}"
            try:
                base.execute(f'CREATE TABLE "{table}" ({cle} INTEGER PRIMARY KEY, {colonnes}, {geometrie} BLOB)')
                base.execute(f'INSERT INTO "{table}" SELECT {cle}, {noms}, {geometrie} FROM complet."{source}"'
                             + (f" WHERE {condition}" if condition else ""), parametres)
                base.execute(f'CREATE VIRTUAL TABLE "{rtree}" USING rtree(id, minx, maxx, miny, maxy)')
                if condition:
                    base.execute(f'INSERT INTO "{rtree}" SELECT r.id, r.minx, r.maxx, r.miny, r.maxy '
                                 f'FROM complet."{rtree_source}" r JOIN "{table}" t ON t.{cle} = r.id')
                else:
                    base.execute(f'INSERT INTO "{rtree}" SELECT id, minx, maxx, miny, maxy '
                                 f'FROM complet."{rtree_source}"')
            except sqlite3.OperationalError as exc:
                raise ErreurArchive(f"{Path(gpkg).name} : pas de {source} lisible ({exc}).") from exc
            gardes += base.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        base.commit()
        base.execute("DETACH DATABASE complet")
    return gardes


class LecteurEdition:
    """Le lecteur d'une source nationale publiée d'une seule édition
    (swissTLM3D, ZABAGED), pour fabrication.fabriquer(troncons=…) : l'édition
    n'est cherchée qu'une fois, et l'archive n'est téléchargée qu'à la
    première emprise qui en a besoin. derniere_edition() et
    geopackage(dossier, edition) sont les fonctions du fournisseur ; la
    sous-classe lit les chemins d'une emprise (__call__)."""

    def __init__(self, dossier, derniere_edition, geopackage):
        self.dossier = dossier
        self._derniere_edition, self._geopackage = derniere_edition, geopackage
        self._edition = None
        self._base = None

    def edition(self) -> dict:
        if self._edition is None:
            self._edition = self._derniere_edition()
        return self._edition

    def date(self, sud: float, ouest: float, nord: float, est: float) -> str:  # noqa: ARG002 (interface des lecteurs)
        """L'édition pour le manifeste."""
        return self.edition()["date"]

    def preparer(self, sud: float, ouest: float, nord: float, est: float) -> None:  # noqa: ARG002
        """Télécharge d'avance l'édition, sans rien lire, comme
        bdtopo_regions.Lecteur.preparer : l'étape « données » du serveur la
        range ainsi dans son artefact, et la fusion en damier
        (fabrication._lecteur) ne s'active que si chaque lecteur sait le faire.
        Sans elle, le calcul puis chaque part des calques retéléchargeaient
        l'archive (6,7 Go pour ZABAGED), et la fusion restait maille par maille."""
        if self._base is None:
            self._base = self._geopackage(self.dossier, self.edition())
