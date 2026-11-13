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

Le téléchargement suit lidar2map, qui fabrique ses fonds ainsi depuis
longtemps : FILS connexions simultanées, sans autre bride, avec le User-Agent
du projet ; une connexion gardée ouverte par fil (keep-alive) ; une file
continue, où une tuile lente n'arrête que sa connexion ; DELAI secondes au
plus par tuile. DEBIT reste réglable pour un service qui demanderait d'aller
plus doucement.
"""
from __future__ import annotations

import concurrent.futures
import http.client
import io
import math
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
# Comme lidar2map (demande de Nico du 2026-11-05) : 8 connexions, sans bride.
# À 4 connexions et 10 tuiles par seconde au plus, un carré prenait 2 h 30 ;
# lidar2map fait 55 912 tuiles de SCAN 25 en 20 minutes.
# Puis, mesuré le 2026-11-13 : 4 872 s pour les 61 508 tuiles de N43E005
# (12,6 par seconde). Les tuiles partaient par paquets de 256, chacun
# attendant sa plus lente ; or le serveur laisse parfois une requête sans
# réponse jusqu'au délai, 30 s alors, et les 8 connexions attendaient avec
# elle. Alignés sur lidar2map : file continue, connexions gardées, 15 s.
# Puis N43E006 en 1 881 s, en dents de scie quand MOBAC tient un plateau : un
# enregistrement de la base, à 830 Mo, prenait jusqu'à 12 s, et pendant ce
# temps rien ne relançait les téléchargements. D'où le mode WAL, des
# enregistrements plus rares, et une file regarnie avant d'écrire.
DEBIT = 0.0                 # tuiles par seconde au plus ; 0 : pas de bride
FILS = 8                    # connexions simultanées
DELAI = 15                  # secondes au plus pour une tuile, avant un nouvel essai
FENETRE = 32                # tuiles en vol par connexion : quelques secondes d'avance si le disque traîne
ENREGISTREMENT = 500        # tuiles reçues entre deux enregistrements (lidar2map : 2 000, sans reprise)
_NOM = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


class ErreurFond(RuntimeError):
    pass


class Abandon(Exception):
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


class _Reponse(io.BytesIO):
    """Le corps d'une réponse déjà lu, à la manière de celle d'urlopen."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _Connexions:
    """Un urlopen qui garde une connexion HTTP/1.1 ouverte par fil (keep-alive)
    et par hôte, comme lidar2map (_wmts_fetch) : urlopen refait une poignée de
    main TCP et TLS à chaque tuile. Une connexion que le serveur a fermée se
    rouvre une fois ; un délai dépassé remonte tel quel, pour le nouvel essai
    de _telecharger_tuile. Un statut d'erreur lève HTTPError, comme urlopen."""

    def __init__(self):
        self.locales = threading.local()
        self.ouvertes = []
        self.verrou = threading.Lock()

    def _connexion(self, schema: str, hote: str, timeout: float):
        cache = getattr(self.locales, "par_hote", None)
        if cache is None:
            cache = self.locales.par_hote = {}
        if hote not in cache:
            classe = http.client.HTTPSConnection if schema == "https" else http.client.HTTPConnection
            cache[hote] = classe(hote, timeout=timeout)
            with self.verrou:
                self.ouvertes.append(cache[hote])
        return cache[hote]

    def _oublier(self, hote: str) -> None:
        connexion = getattr(self.locales, "par_hote", {}).pop(hote, None)
        if connexion is not None:
            connexion.close()

    def __call__(self, requete, timeout=DELAI):
        parties = urllib.parse.urlsplit(requete.full_url)
        chemin = parties.path + (f"?{parties.query}" if parties.query else "")
        for essai in range(2):
            connexion = self._connexion(parties.scheme, parties.netloc, timeout)
            try:
                connexion.request("GET", chemin, headers=dict(requete.header_items()))
                reponse = connexion.getresponse()
                contenu = reponse.read()          # lu en entier : la connexion resservira
                break
            except (http.client.HTTPException, OSError) as exc:
                self._oublier(parties.netloc)
                if essai or isinstance(exc, TimeoutError):
                    raise
        if reponse.status >= 300:
            raise urllib.error.HTTPError(requete.full_url, reponse.status, reponse.reason, reponse.headers, None)
        return _Reponse(contenu)

    def fermer(self) -> None:
        with self.verrou:
            for connexion in self.ouvertes:
                connexion.close()
            self.ouvertes.clear()


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
            with ouvrir(urllib.request.Request(url, headers=AGENT), timeout=DELAI) as reponse:
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
    raise ErreurFond(f"Tuiles du fond injoignables ({erreur}).") from erreur


def _tuile_jpeg(url: str, ouvrir, debit: _Debit, continuer) -> bytes | None:
    """Une tuile téléchargée puis réencodée, dans le fil de sa connexion : le
    fil principal n'a plus qu'à la ranger."""
    contenu = _telecharger_tuile(url, ouvrir, debit, continuer)
    return en_jpeg(contenu) if contenu else None


def _ouvrir_base(chemin: Path, ecriture: bool = False) -> sqlite3.Connection:
    """ecriture : le .part d'un téléchargement, en mode WAL (journal en
    écriture anticipée) et synchronous=NORMAL : un enregistrement ajoute au
    journal au lieu de réécrire la base, sans risque pour la reprise si
    l'application s'arrête. lidar2map va plus loin (journal en mémoire,
    synchronous=OFF), mais jette son .part sur un échec ; hike2gpx le
    reprend."""
    base = sqlite3.connect(chemin)
    if ecriture:
        base.execute("PRAGMA journal_mode=WAL")
        base.execute("PRAGMA synchronous=NORMAL")
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
    connexions = None if ouvrir else _Connexions()
    ouvrir = ouvrir or connexions
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    partiel = chemin.with_name(chemin.name + ".part")
    base = _ouvrir_base(partiel, ecriture=True)
    try:
        deja = set(base.execute("SELECT zoom_level, tile_column, tile_row FROM tiles"))
        toutes = tuiles(zone, zooms)
        restantes = [(z, x, y) for z, x, y in toutes if (z, x, 2 ** z - 1 - y) not in deja]
        faites = len(toutes) - len(restantes)
        a_faire = iter(restantes)
        suivi(faites, len(toutes))
        limiteur = _Debit(debit)
        with concurrent.futures.ThreadPoolExecutor(max_workers=fils) as pool:
            # File continue, comme lidar2map : FENETRE tuiles en vol par
            # connexion, et chaque tuile reçue en appelle une autre. Une tuile
            # lente n'arrête que sa connexion, quand des paquets attendaient
            # chacun leur plus lente. La file se regarnit avant d'écrire : un
            # enregistrement lent n'arrête pas les connexions, qui ont de
            # l'avance.
            en_vol = {}

            def remplir():
                while len(en_vol) < FENETRE * fils and (t := next(a_faire, None)) is not None:
                    en_vol[pool.submit(_tuile_jpeg, url_tuile(source, *t, cle_ign), ouvrir,
                                       limiteur, continuer)] = t
            remplir()
            recues = 0
            try:
                while en_vol:
                    finies, _ = concurrent.futures.wait(en_vol, return_when=concurrent.futures.FIRST_COMPLETED)
                    arrivees = [(en_vol.pop(tache), tache) for tache in finies]
                    remplir()
                    for (z, x, y), tache in arrivees:
                        contenu = tache.result()
                        if contenu:
                            base.execute("INSERT OR REPLACE INTO tiles VALUES (?, ?, ?, ?)",
                                         (z, x, 2 ** z - 1 - y, contenu))
                        faites += 1
                        recues += 1
                    if recues >= ENREGISTREMENT:
                        # Dans le désordre, mais chaque tuile rangée ne se redemande plus.
                        base.commit()
                        recues = 0
                        suivi(faites, len(toutes))
            except BaseException:
                for tache in en_vol:
                    tache.cancel()
                # Arrêté ou en échec : les tuiles déjà reçues restent acquises pour la reprise.
                base.commit()
                raise
        base.commit()
        suivi(faites, len(toutes))
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
        if connexions is not None:
            connexions.fermer()
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
