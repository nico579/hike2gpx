"""Fonds de carte hors ligne : les tuiles raster de la page, rangées en MBTiles.

La page affiche des fonds nationaux (providers/<pays>.js) : en France le
SCAN 25 avec la clé IGN de l'utilisateur ou le Plan IGN, ailleurs la carte
officielle du pays quand sa licence permet de la garder (SOURCES). Pour
marcher sans réseau, le PC télécharge les tuiles du fond affiché, sur une vue
ou une case de 5°, et les range dans un MBTiles 1.3 : une base SQLite, une
rangée par tuile, numérotée à la manière TMS (rangées comptées depuis le sud),
que lisent aussi bien la page que le téléphone.

Le SCAN 25 n'est pas une donnée libre : il est téléchargé avec la clé de
l'utilisateur, pour son seul usage. Un fond reste donc sur le PC (et sur son
téléphone, par le partage local) et n'entre jamais dans une publication du
dépôt (depot.py ne publie que des lots, décrits par leur manifeste).

Le téléchargement lui-même est celui de nico579_commons.tuiles, commun avec
lidar2map : FILS connexions simultanées, sans autre bride, avec le User-Agent
du projet. DEBIT reste réglable pour un service qui demanderait d'aller plus
doucement.
"""
from __future__ import annotations

import io
import math
import re
import sqlite3
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

from nico579_commons import tuiles as reseau
from nico579_commons.tuiles import Abandon  # noqa: F401  (l'application l'attrape sous fonds.Abandon)

from . import lot
from .depot import AGENT


@dataclass(frozen=True)
class Source:
    gabarit: str            # l'adresse d'une tuile : {z}, {x}, {y}, et {cle} pour un service à clé
    cle: bool               # le service privé de l'IGN, avec la clé de l'utilisateur
    titre: str
    attribution: str


def _ign(couche: str, mime: str, cle: bool, matrice: str = "PM") -> str:
    """L'adresse WMTS de la Géoplateforme, comme tuileIgn() de providers/fr.js."""
    base = "https://data.geopf.fr/private/wmts" if cle else "https://data.geopf.fr/wmts"
    return (f"{base}?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER={couche}&STYLE=normal"
            f"&TILEMATRIXSET={matrice}&FORMAT={mime}&TILEMATRIX={{z}}&TILECOL={{x}}&TILEROW={{y}}"
            + ("&apikey={cle}" if cle else ""))


# Les fonds de la page qu'on peut emporter hors ligne, sous la clé que leur
# donne providers/<pays>.js : le PC fabrique le fond affiché. N'y entrent que
# les services dont la licence permet de garder les tuiles : le SCAN 25 pour
# l'usage de l'utilisateur, avec sa clé ; Licence Ouverte (Plan IGN, photos
# aériennes et relief LiDAR HD de l'IGN), dl-de/by-2-0 (TopPlusOpen) et
# CC BY 4.0 (IGN España, Kartverket, PDOK), l'attribution suivant le fond
# jusque dans le MBTiles. Restent en ligne les fonds dont le serveur interdit
# la recopie en masse, quelle que soit la licence des données : les tuiles
# d'OpenStreetMap et d'OpenTopoMap (serveurs de bénévoles, qui bloquent les
# téléchargements en masse) et l'imagerie d'Esri (stockage hors ligne interdit
# par ses conditions).
# Toute tuile se range en JPEG (en_jpeg) : le format d'origine n'est plus noté
# (champ jamais lu, audit M1 du 2026-11-13).
SOURCES = {
    "scan25": Source(_ign("GEOGRAPHICALGRIDSYSTEMS.MAPS", "image/jpeg", True), True, "SCAN 25 (IGN)", "© IGN"),
    "plan": Source(_ign("GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2", "image/png", False), False, "Plan IGN", "© IGN"),
    "photos": Source(_ign("ORTHOIMAGERY.ORTHOPHOTOS", "image/jpeg", False), False,
                     "Photos aériennes (IGN)", "© IGN"),
    "reliefLidar": Source(_ign("IGNF_LIDAR-HD_MNT_ELEVATION.ELEVATIONGRIDCOVERAGE.SHADOW", "image/png", False,
                               "PM_0_18"), False, "Relief LiDAR HD (IGN)", "© IGN"),
    "allemagne": Source("https://sgx.geodatenzentrum.de/wmts_topplus_open/tile/1.0.0/web/default/WEBMERCATOR/"
                        "{z}/{y}/{x}.png", False, "TopPlusOpen (BKG)", "© BKG, dl-de/by-2-0"),
    "espagne": Source("https://www.ign.es/wmts/mapa-raster?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=MTN"
                      "&STYLE=default&TILEMATRIXSET=GoogleMapsCompatible&FORMAT=image/jpeg"
                      "&TILEMATRIX={z}&TILECOL={x}&TILEROW={y}", False, "MTN (IGN España)",
                      "© IGN España, CC BY 4.0"),
    "norvege": Source("https://cache.kartverket.no/v1/wmts/1.0.0/toporaster/default/webmercator/{z}/{y}/{x}.png",
                      False, "Toporaster (Kartverket)", "© Kartverket, CC BY 4.0"),
    "paysBas": Source("https://service.pdok.nl/kadaster/brt-achtergrondkaart/wmts/v2_0/standaard/EPSG:3857/"
                      "{z}/{x}/{y}.png", False, "BRT Achtergrondkaart (PDOK)", "© Kadaster / PDOK, CC BY 4.0"),
}
# Un fond couvre un carré de 1°, nommé comme les tuiles SRTM (N43E006 : de
# 43° à 44° nord, de 6° à 7° est), et non la case de 5° du routage : une case
# entière au zoom 16 pèserait une dizaine de Go (mesure du 2026-11-05).
# Zooms 13 à 16 : le service de l'IGN ne sert le vrai SCAN 25 qu'à partir du
# 15 (au 13, c'est un document à l'échelle du SCAN 100), et le 16 est sa pleine
# résolution. Un carré en Provence : environ 60 000 tuiles, 1 Go, une demi-heure
# (19 ko et 29 tuiles par seconde, mesuré le 2026-11-05 ; lidar2map, qui garde
# ses connexions ouvertes, tire environ 46 tuiles par seconde du SCAN 25).
CARRE_DEG = 1
ZOOMS_CARRE = (13, 16)
CARRES_MAX = 4              # carrés fabriqués d'une seule demande (la vue affichée)
# Toutes les tuiles en JPEG qualité 70 (décision de Nico du 2026-11-05) : les
# PNG (Plan IGN, TopPlusOpen…) y gagnent beaucoup, le SCAN 25 un peu.
QUALITE_JPEG = 70
_CARRE = re.compile(r"^([NS])(\d{2})([EW])(\d{3})$")
# Le téléchargement lui-même (file continue, connexions gardées, essais) est dans
# nico579_commons.tuiles, commun avec lidar2map. Restent ici les réglages de
# hike2gpx, mesurés : 8 connexions et pas de bride (à 24, la Géoplateforme
# freine), 500 tuiles entre deux enregistrements (lidar2map : 2 000, car il
# jette son .part sur un échec quand hike2gpx le reprend).
DEBIT = reseau.DEBIT        # tuiles par seconde au plus ; 0 : pas de bride
FILS = reseau.FILS          # connexions simultanées
FENETRE = reseau.FENETRE    # tuiles en vol par connexion
ENREGISTREMENT = reseau.ENREGISTREMENT
_NOM = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


class ErreurFond(RuntimeError):
    pass


def source_pour(cle_ign: str) -> str:
    """Le fond français par défaut : le SCAN 25 avec une clé, le Plan IGN sans."""
    return "scan25" if cle_ign else "plan"


def url_tuile(source: str, z: int, x: int, y: int, cle_ign: str = "") -> str:
    """L'adresse d'une tuile, celle même que demande la page."""
    return SOURCES[source].gabarit.format(z=z, x=x, y=y, cle=urllib.parse.quote(cle_ign))


def nom_valide(nom: str) -> bool:
    """Un nom de fond sûr comme nom de fichier et dans une adresse : jamais de
    séparateur de dossier ni de « .. »."""
    return bool(_NOM.match(nom or "")) and ".." not in nom


def nom_fond(carre: str, source: str) -> str:
    """N43E006-scan25 : le carré, puis la source, que le téléphone lit dans le nom."""
    return f"{carre}-{source}"


def nom_carre(lat: float, lon: float) -> str:
    """Le carré de 1° du point, nommé comme une tuile SRTM : (43.3, 6.04) -> N43E006."""
    sud, ouest = math.floor(lat), math.floor(lon)
    return f"{'N' if sud >= 0 else 'S'}{abs(sud):02d}{'E' if ouest >= 0 else 'W'}{abs(ouest):03d}"


def carre_valide(nom: str) -> bool:
    trouve = _CARRE.match(nom or "")
    return bool(trouve) and int(trouve.group(2)) <= 89 and int(trouve.group(4)) <= 180


def boite_carre(nom: str) -> tuple:
    """(sud, ouest, nord, est) du carré N43E006 -> (43, 6, 44, 7)."""
    trouve = _CARRE.match(nom)
    if not trouve or not carre_valide(nom):
        raise ErreurFond(f"Carré invalide : {nom}")
    sud = int(trouve.group(2)) * (1 if trouve.group(1) == "N" else -1)
    ouest = int(trouve.group(4)) * (1 if trouve.group(3) == "E" else -1)
    return sud, ouest, sud + CARRE_DEG, ouest + CARRE_DEG


def carres_zone(zone: tuple) -> list:
    """Les carrés que touche la zone (sud, ouest, nord, est), du sud-ouest au nord-est."""
    sud, ouest, nord, est = zone
    return [nom_carre(la + 0.5, lo + 0.5)
            for la in range(math.floor(sud), math.ceil(nord))
            for lo in range(math.floor(ouest), math.ceil(est))]


def tuiles(zone: tuple, zooms: tuple) -> list:
    """Les tuiles (z, x, y) qui couvrent la zone (sud, ouest, nord, est)."""
    return [(z, x, y) for z in range(zooms[0], zooms[1] + 1) for x, y in lot.tuiles_emprise(z, *zone)]


def en_jpeg(contenu: bytes, qualite: int = QUALITE_JPEG) -> bytes:
    """La tuile en JPEG à la qualité voulue ; un PNG transparent est posé sur du blanc."""
    from PIL import Image
    image = Image.open(io.BytesIO(contenu))
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        fond = Image.new("RGB", image.size, (255, 255, 255))
        fond.paste(image, mask=image.getchannel("A"))
        image = fond
    sortie = io.BytesIO()
    image.convert("RGB").save(sortie, "JPEG", quality=qualite, optimize=True)
    return sortie.getvalue()


def _tuile_jpeg(contenu: bytes) -> bytes:
    """Le réencodage de chaque tuile, dans le fil de sa connexion."""
    return en_jpeg(contenu)


def fabriquer(chemin: Path, source: str, zone: tuple, zooms: tuple, cle_ign: str = "", *, suivi=None,
              continuer=None, ouvrir=None, debit: float = DEBIT, fils: int = FILS) -> dict:
    """Télécharge les tuiles de la zone dans le MBTiles chemin. Le travail se
    fait dans chemin.part, repris là où il s'est arrêté (tuiles déjà là), et
    ne prend le nom final qu'achevé. suivi(faites, total) en tuiles. Rend la
    description du fond (decrire)."""
    if SOURCES[source].cle and not cle_ign:
        raise ErreurFond("Le SCAN 25 demande la clé IGN des réglages.")
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    partiel = chemin.with_name(chemin.name + ".part")
    base = reseau.ouvrir_base(partiel, ecriture=True)
    try:
        deja = reseau.deja_rangees(base)
        toutes = tuiles(zone, zooms)
        restantes = [(z, x, y) for z, x, y in toutes if (z, x, 2 ** z - 1 - y) not in deja]
        if suivi:
            suivi(len(toutes) - len(restantes), len(toutes))
        try:
            reseau.telecharger(base, restantes, lambda z, x, y: url_tuile(source, z, x, y, cle_ign),
                               total=len(toutes), faites=len(toutes) - len(restantes), suivi=suivi,
                               continuer=continuer, ouvrir=ouvrir, entetes=AGENT, traiter=_tuile_jpeg,
                               debit=debit, fils=fils, fenetre=FENETRE, enregistrement=ENREGISTREMENT)
        except reseau.ErreurTuiles as exc:
            # Les tuiles reçues restent dans le .part : la demande suivante reprend là.
            if exc.code in (401, 403):
                raise ErreurFond("Le service de l'IGN refuse la clé (réglages).") from exc
            raise ErreurFond(f"Tuiles du fond injoignables ({exc}).") from exc
        if base.execute("SELECT COUNT(*) FROM tiles").fetchone()[0] == 0:
            raise ErreurFond("Aucune tuile de ce fond sur cette zone (hors de son pays ?).")
        sud, ouest, nord, est = zone
        metadata = {"name": chemin.stem, "format": "jpg", "type": "baselayer", "version": "1",
                    "description": SOURCES[source].titre, "attribution": SOURCES[source].attribution,
                    "minzoom": str(zooms[0]), "maxzoom": str(zooms[1]), "bounds": f"{ouest},{sud},{est},{nord}",
                    "center": f"{(ouest + est) / 2},{(sud + nord) / 2},{zooms[1]}",
                    # Hors spécification (admis par MBTiles 1.3) : la source, lue par la page et le partage.
                    "source": source}
        base.executemany("INSERT OR REPLACE INTO metadata VALUES (?, ?)", metadata.items())
        base.commit()
        # Le journal versé dans la base, puis le mode ordinaire : le fond
        # achevé tient en un seul fichier, à lire, partager ou archiver.
        base.execute("PRAGMA journal_mode=DELETE")
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
            "format": meta.get("format", ""), "attribution": meta.get("attribution", ""), "octets": chemin.stat().st_size}


def lire_tuile(chemin: Path, z: int, x: int, y: int) -> bytes | None:
    """La tuile XYZ (rangée comptée depuis le nord, comme Leaflet) ou None."""
    base = sqlite3.connect(f"file:{Path(chemin).resolve().as_posix()}?mode=ro", uri=True)
    try:
        ligne = base.execute("SELECT tile_data FROM tiles WHERE zoom_level = ? AND tile_column = ? AND tile_row = ?",
                             (z, x, 2 ** z - 1 - y)).fetchone()
    finally:
        base.close()
    return ligne[0] if ligne else None
