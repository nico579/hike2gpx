"""Fonds de carte hors ligne : les tuiles raster de la page, rangées en MBTiles.

La page affiche ses fonds français depuis le service WMTS de la Géoplateforme
de l'IGN (providers/fr.js) : le SCAN 25 avec la clé IGN de l'utilisateur, le
Plan IGN sans clé. Pour marcher sans réseau, le PC télécharge ces mêmes tuiles,
sur une vue ou une case de 5°, et les range dans un MBTiles 1.3 : une base
SQLite, une rangée par tuile, numérotée à la manière TMS (rangées comptées
depuis le sud), que lisent aussi bien la page que le téléphone.

Le SCAN 25 n'est pas une donnée libre : il est téléchargé avec la clé de
l'utilisateur, pour son seul usage. Un fond reste donc sur le PC (et sur son
téléphone, par le partage local) et n'entre jamais dans une publication du
dépôt (depot.py ne publie que des lots, décrits par leur manifeste).

Conditions d'usage du service : un débit modéré (quelques connexions, DEBIT
tuiles par seconde au plus) et le User-Agent du projet.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import http.client
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import lot
from .depot import AGENT


@dataclass(frozen=True)
class Source:
    couche: str             # couche WMTS de la Géoplateforme
    mime: str
    format: str             # « jpg » ou « png », le format MBTiles
    cle: bool               # le service privé, avec la clé IGN
    titre: str


# Les mêmes couches que la page (providers/fr.js).
SOURCES = {
    "scan25": Source("GEOGRAPHICALGRIDSYSTEMS.MAPS", "image/jpeg", "jpg", True, "SCAN 25 (IGN)"),
    "plan": Source("GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2", "image/png", "png", False, "Plan IGN"),
}
ATTRIBUTION = "© IGN"
# Niveaux de zoom (mesurés le 2026-10-28, voir la PR) : une vue d'écran
# descend jusqu'au 16, le plus fin du SCAN 25, où se lisent les sentiers ;
# une case de 5° s'arrête au 13, sinon elle passerait le million de tuiles.
# La page agrandit au-delà (maxNativeZoom) ; au-dessous du 6, rien d'utile.
ZOOMS_VUE = (6, 16)
ZOOMS_CASE = (6, 13)
# Une vue très dézoomée ne se prend pas jusqu'au 16 : on retire des niveaux
# fins jusqu'à tenir sous ce nombre de tuiles (environ 100 Mo de SCAN 25).
TUILES_MAX_VUE = 5000
DEBIT = 10.0                # tuiles par seconde au plus
FILS = 4                    # connexions simultanées
_NOM = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


class ErreurFond(RuntimeError):
    pass


class Abandon(Exception):
    pass


def source_pour(cle_ign: str) -> str:
    """Le fond que montre la page : le SCAN 25 avec une clé, le Plan IGN sans."""
    return "scan25" if cle_ign else "plan"


def url_tuile(source: str, z: int, x: int, y: int, cle_ign: str = "") -> str:
    """L'adresse WMTS d'une tuile, comme tuileIgn() de providers/fr.js."""
    s = SOURCES[source]
    base = "https://data.geopf.fr/private/wmts" if s.cle else "https://data.geopf.fr/wmts"
    url = (f"{base}?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER={s.couche}&STYLE=normal"
           f"&TILEMATRIXSET=PM&FORMAT={s.mime}&TILEMATRIX={z}&TILECOL={x}&TILEROW={y}")
    return url + (f"&apikey={urllib.parse.quote(cle_ign)}" if s.cle else "")


def nom_valide(nom: str) -> bool:
    """Un nom de fond sûr comme nom de fichier et dans une adresse : jamais de
    séparateur de dossier ni de « .. »."""
    return bool(_NOM.match(nom or "")) and ".." not in nom


def nom_fond(case: str, source: str, zone: tuple | None = None) -> str:
    """E5_N40-scan25 pour la case entière ; une vue y ajoute l'empreinte courte
    de sa zone (E5_N40-scan25-vue-3fa2c1), pour en garder plusieurs."""
    if zone is None:
        return f"{case}-{source}"
    empreinte = hashlib.sha1(",".join(f"{v:.4f}" for v in zone).encode()).hexdigest()[:6]
    return f"{case}-{source}-vue-{empreinte}"


def tuiles(zone: tuple, zooms: tuple) -> list:
    """Les tuiles (z, x, y) qui couvrent la zone (sud, ouest, nord, est)."""
    return [(z, x, y) for z in range(zooms[0], zooms[1] + 1) for x, y in lot.tuiles_emprise(z, *zone)]


def zooms_vue(zone: tuple) -> tuple:
    """Les niveaux d'une vue : jusqu'au 16, moins si la vue est trop grande."""
    zmin, zmax = ZOOMS_VUE
    while zmax > zmin and len(tuiles(zone, (zmin, zmax))) > TUILES_MAX_VUE:
        zmax -= 1
    return zmin, zmax


class _Debit:
    """Au plus n requêtes par seconde, tous fils confondus."""

    def __init__(self, par_seconde: float):
        self.intervalle = 1.0 / par_seconde if par_seconde else 0.0
        self.suivante = time.monotonic()
        self.verrou = threading.Lock()

    def attendre(self) -> None:
        with self.verrou:
            maintenant = time.monotonic()
            attente = self.suivante - maintenant
            self.suivante = max(self.suivante, maintenant) + self.intervalle
        if attente > 0:
            time.sleep(attente)


def _telecharger_tuile(url: str, ouvrir, debit: _Debit, continuer) -> bytes | None:
    """Le contenu de la tuile, None hors couverture (404, ou 400 hors de la
    matrice) ; quatre essais, espacés de 2, 4 puis 8 s, sur une coupure ou un
    refus. Un refus de la clé (401, 403) n'est pas toujours définitif : mesuré
    le 2026-10-28, le service a répondu 401 une fois, après 9 000 tuiles, à
    une clé qu'il acceptait de nouveau l'instant d'après. Refusée quatre fois
    de suite, la clé est jugée fausse."""
    for essai in range(4):
        if not continuer():
            raise Abandon()
        debit.attendre()
        try:
            with ouvrir(urllib.request.Request(url, headers=AGENT), timeout=30) as reponse:
                return reponse.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (400, 404):
                return None
            erreur = exc
        except (OSError, http.client.HTTPException) as exc:
            erreur = exc
        if essai < 3:
            time.sleep(2 ** (essai + 1))
    if isinstance(erreur, urllib.error.HTTPError) and erreur.code in (401, 403):
        raise ErreurFond("Le service de l'IGN refuse la clé (réglages).") from erreur
    raise ErreurFond(f"Tuiles de l'IGN injoignables ({erreur}).") from erreur


def _ouvrir_base(chemin: Path) -> sqlite3.Connection:
    base = sqlite3.connect(chemin)
    base.executescript(
        "CREATE TABLE IF NOT EXISTS metadata (name TEXT, value TEXT);"
        "CREATE TABLE IF NOT EXISTS tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER,"
        " tile_data BLOB);"
        "CREATE UNIQUE INDEX IF NOT EXISTS tile_index ON tiles (zoom_level, tile_column, tile_row);"
        "CREATE UNIQUE INDEX IF NOT EXISTS name ON metadata (name);")
    return base


def fabriquer(chemin: Path, source: str, zone: tuple, zooms: tuple, cle_ign: str = "", *, suivi=None,
              continuer=None, ouvrir=None, debit: float = DEBIT, fils: int = FILS) -> dict:
    """Télécharge les tuiles de la zone dans le MBTiles chemin. Le travail se
    fait dans chemin.part, repris là où il s'est arrêté (tuiles déjà là), et
    ne prend le nom final qu'achevé. suivi(faites, total) en tuiles. Rend la
    description du fond (decrire)."""
    if SOURCES[source].cle and not cle_ign:
        raise ErreurFond("Le SCAN 25 demande la clé IGN des réglages.")
    suivi = suivi or (lambda faites, total: None)
    continuer = continuer or (lambda: True)
    ouvrir = ouvrir or urllib.request.urlopen
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    partiel = chemin.with_name(chemin.name + ".part")
    base = _ouvrir_base(partiel)
    try:
        deja = set(base.execute("SELECT zoom_level, tile_column, tile_row FROM tiles"))
        toutes = tuiles(zone, zooms)
        a_faire = [(z, x, y) for z, x, y in toutes if (z, x, 2 ** z - 1 - y) not in deja]
        faites = len(toutes) - len(a_faire)
        suivi(faites, len(toutes))
        limiteur = _Debit(debit)
        with concurrent.futures.ThreadPoolExecutor(max_workers=fils) as pool:
            # Par paquets : jamais plus que quelques dizaines de tuiles en mémoire.
            for debut in range(0, len(a_faire), 8 * fils):
                paquet = a_faire[debut:debut + 8 * fils]
                contenus = pool.map(lambda t: _telecharger_tuile(url_tuile(source, *t, cle_ign), ouvrir,
                                                                  limiteur, continuer), paquet)
                for (z, x, y), contenu in zip(paquet, contenus):
                    if contenu:
                        base.execute("INSERT OR REPLACE INTO tiles VALUES (?, ?, ?, ?)",
                                     (z, x, 2 ** z - 1 - y, contenu))
                base.commit()
                faites += len(paquet)
                suivi(faites, len(toutes))
        if base.execute("SELECT COUNT(*) FROM tiles").fetchone()[0] == 0:
            raise ErreurFond("Aucune tuile de l'IGN sur cette zone (hors de France ?).")
        sud, ouest, nord, est = zone
        metadata = {"name": chemin.stem, "format": SOURCES[source].format, "type": "baselayer", "version": "1",
                    "description": SOURCES[source].titre, "attribution": ATTRIBUTION,
                    "minzoom": str(zooms[0]), "maxzoom": str(zooms[1]), "bounds": f"{ouest},{sud},{est},{nord}",
                    "center": f"{(ouest + est) / 2},{(sud + nord) / 2},{zooms[1]}",
                    # Hors spécification (admis par MBTiles 1.3) : la source, lue par la page et le partage.
                    "source": source}
        base.executemany("INSERT OR REPLACE INTO metadata VALUES (?, ?)", metadata.items())
        base.commit()
    finally:
        base.close()
    partiel.replace(chemin)
    return decrire(chemin)


def decrire(chemin: Path) -> dict:
    """Le fond tel que le décrivent la page et le catalogue du partage :
    {"nom", "zone": [sud, ouest, nord, est], "zoom": [min, max], "source", "octets"}."""
    chemin = Path(chemin)
    base = sqlite3.connect(f"file:{chemin.resolve().as_posix()}?mode=ro", uri=True)
    try:
        meta = dict(base.execute("SELECT name, value FROM metadata"))
    finally:
        base.close()
    ouest, sud, est, nord = (float(v) for v in meta["bounds"].split(","))
    return {"nom": chemin.stem, "zone": [sud, ouest, nord, est],
            "zoom": [int(meta["minzoom"]), int(meta["maxzoom"])], "source": meta.get("source", ""),
            "format": meta.get("format", ""), "octets": chemin.stat().st_size}


def lire_tuile(chemin: Path, z: int, x: int, y: int) -> bytes | None:
    """La tuile XYZ (rangée comptée depuis le nord, comme Leaflet) ou None."""
    base = sqlite3.connect(f"file:{Path(chemin).resolve().as_posix()}?mode=ro", uri=True)
    try:
        ligne = base.execute("SELECT tile_data FROM tiles WHERE zoom_level = ? AND tile_column = ? AND tile_row = ?",
                             (z, x, 2 ** z - 1 - y)).fetchone()
    finally:
        base.close()
    return ligne[0] if ligne else None
