"""La BD TOPO par régions, pour fabriquer des cases entières sur le serveur.

Le WFS de l'IGN convient à une vue : une vingtaine de tuiles. Une case entière
en demande des milliers (essai GitHub Actions du 2026-10-27 : 47 min de fusion
sans finir, une réponse coupée fatale). L'IGN publie aussi la BD TOPO en
archives régionales, GeoPackage « tous thèmes », quatre fois par an :

1. les régions qui touchent une case : une requête à ADMIN EXPRESS (WFS) ;
2. leur dernière édition : le catalogue ATOM de data.geopf.fr ;
3. l'archive 7z, reprise si coupée, contrôlée par son MD5, décompressée par
   la commande 7z ; seul le GeoPackage reste, en cache, pour les cases et les
   semaines suivantes ;
4. les tronçons d'une emprise, lus par l'index RTree (case.troncons_gpkg).
"""
from __future__ import annotations

import hashlib
import http.client
import logging
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from . import __version__
from .providers.core import lire_json

journal = logging.getLogger(__name__)
WFS = "https://data.geopf.fr/wfs/ows"
CATALOGUE = "https://data.geopf.fr/telechargement/resource/BDTOPO"
TELECHARGEMENT = "https://data.geopf.fr/telechargement/download/BDTOPO/"
ATOM = "{http://www.w3.org/2005/Atom}"
GPF = "{https://data.geopf.fr/annexes/ressources/xsd/gpf_dl.xsd}"
AGENT = {"User-Agent": f"hike2gpx/{__version__} (BD TOPO par régions)"}
BLOC = 1 << 20


class ErreurArchive(RuntimeError):
    pass


def regions_de_zone(sud: float, ouest: float, nord: float, est: float) -> list:
    """Codes des régions (« R93 ») dont le contour touche l'emprise."""
    parametres = {"SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
                  "TYPENAMES": "ADMINEXPRESS-COG.LATEST:region", "OUTPUTFORMAT": "application/json",
                  "BBOX": f"{sud},{ouest},{nord},{est},urn:ogc:def:crs:EPSG::4326",
                  "PROPERTYNAME": "code_insee", "COUNT": 50}
    donnees = lire_json(WFS + "?" + urllib.parse.urlencode(parametres), "ADMIN EXPRESS")
    return sorted({f"R{f['properties']['code_insee']}" for f in donnees.get("features", [])})


def _atom(url: str) -> ET.Element:
    with urllib.request.urlopen(urllib.request.Request(url, headers=AGENT), timeout=60) as reponse:
        return ET.fromstring(reponse.read())


def derniere_edition(region: str, lire=_atom) -> dict:
    """{"nom", "date", "fichiers": [{"url", "octets", "md5"}]} de la dernière
    édition GeoPackage « tous thèmes » de la région."""
    requete = urllib.parse.urlencode({"zone": region, "format": "GPKG", "limit": 50,
                                      "sortEntriesBy": "editionDate", "sortEntriesOrder": "desc"})
    motif = rf"BDTOPO_[\d-]+_TOUSTHEMES_GPKG_LAMB93_{re.escape(region)}_(\d{{4}}-\d{{2}}-\d{{2}})"
    editions = [t for t in (e.findtext(ATOM + "title", "") for e in lire(f"{CATALOGUE}?{requete}").findall(ATOM + "entry"))
                if re.fullmatch(motif, t)]
    if not editions:
        raise ErreurArchive(f"Aucune édition BD TOPO GeoPackage pour {region}.")
    nom = max(editions, key=lambda t: t[-10:])
    fichiers = []
    for entree in lire(f"{CATALOGUE}/{nom}?limit=50").findall(ATOM + "entry"):
        for lien in entree.findall(ATOM + "link"):
            url = lien.get("href", "")
            if url.startswith(TELECHARGEMENT + nom + "/") \
                    and re.fullmatch(re.escape(nom) + r"\.7z(?:\.\d{3})?", url.rsplit("/", 1)[-1]):
                md5 = (entree.findtext(ATOM + "content") or "").strip().lower()
                fichiers.append({"url": url, "octets": int(lien.get(GPF + "length", "0")), "md5": md5})
                break
    if not fichiers:
        raise ErreurArchive(f"Aucune archive pour {nom}.")
    return {"nom": nom, "date": nom[-10:], "fichiers": sorted(fichiers, key=lambda f: f["url"])}


def _telecharger(fichier: dict, cible: Path, ouvrir=urllib.request.urlopen) -> None:
    """Le fichier, repris là où il s'est arrêté (Range), puis contrôlé par son MD5."""
    for essai in range(3):
        deja = cible.stat().st_size if cible.exists() else 0
        if deja < fichier["octets"]:
            entetes = {**AGENT, **({"Range": f"bytes={deja}-"} if deja else {})}
            try:
                with ouvrir(urllib.request.Request(fichier["url"], headers=entetes), timeout=120) as reponse:
                    mode = "ab" if deja and getattr(reponse, "status", 200) == 206 else "wb"
                    with open(cible, mode) as f:
                        shutil.copyfileobj(reponse, f, BLOC)
            except (OSError, http.client.HTTPException) as exc:     # coupure : l'essai suivant reprend
                journal.info("BD TOPO : %s coupé (%s), reprise", cible.name, exc)
                continue
        h = hashlib.md5()
        with open(cible, "rb") as f:
            while bloc := f.read(BLOC):
                h.update(bloc)
        if h.hexdigest() == fichier["md5"]:
            return
        cible.unlink()                  # contenu faux : on repart de zéro
    raise ErreurArchive(f"{cible.name} : téléchargement impossible ou altéré.")


def geopackage(dossier, region: str, edition: dict | None = None) -> Path:
    """Le GeoPackage de la région à sa dernière édition, téléchargé une fois et
    gardé dans dossier/bdtopo-regions ; les éditions plus anciennes sont effacées."""
    edition = edition or derniere_edition(region)
    racine = Path(dossier) / "bdtopo-regions"
    gpkg = racine / f"{edition['nom']}.gpkg"
    if gpkg.is_file():
        return gpkg
    commande = shutil.which("7z") or shutil.which("7za")
    if commande is None:
        raise ErreurArchive("La commande 7z est nécessaire pour la BD TOPO par régions (paquet p7zip).")
    travail = racine / f".{edition['nom']}"
    travail.mkdir(parents=True, exist_ok=True)
    parties = []
    for fichier in edition["fichiers"]:
        partie = travail / fichier["url"].rsplit("/", 1)[-1]
        journal.info("BD TOPO : téléchargement de %s (%.0f Mo)", partie.name, fichier["octets"] / 1e6)
        _telecharger(fichier, partie)
        parties.append(partie)
    extrait = travail / "extrait"
    r = subprocess.run([commande, "x", "-y", f"-o{extrait}", str(parties[0])], capture_output=True, text=True)
    if r.returncode:
        raise ErreurArchive(f"Décompression de {parties[0].name} impossible : {(r.stderr or r.stdout)[-300:]}")
    trouves = sorted(extrait.rglob("*.gpkg"), key=lambda p: p.stat().st_size)
    if not trouves:
        raise ErreurArchive(f"Pas de GeoPackage dans {parties[0].name}.")
    trouves[-1].replace(gpkg)
    shutil.rmtree(travail, ignore_errors=True)
    for ancien in racine.glob(f"BDTOPO_*_{region}_*.gpkg"):
        if ancien != gpkg:
            ancien.unlink()
    return gpkg


class Lecteur:
    """Lecture des tronçons IGN d'une emprise dans les GeoPackage régionaux,
    pour fabrication.fabriquer(troncons={"ign": ...}). Les régions d'une case
    ne sont cherchées qu'une fois, et chaque archive n'est téléchargée qu'à la
    première emprise qui en a besoin."""

    def __init__(self, dossier):
        self.dossier = dossier
        self._regions = {}          # case (sud, ouest) -> codes
        self._editions = {}         # code -> édition
        self._gpkg = {}             # code -> chemin

    def edition(self, region: str) -> dict:
        if region not in self._editions:
            self._editions[region] = derniere_edition(region)
        return self._editions[region]

    def regions(self, sud: float, ouest: float, nord: float, est: float) -> list:
        # Le centre de l'emprise : ses bords débordent un peu sur la case voisine.
        case = ((sud + nord) / 2 // 5 * 5, (ouest + est) / 2 // 5 * 5)
        if case not in self._regions:
            self._regions[case] = regions_de_zone(case[0], case[1], case[0] + 5, case[1] + 5)
        return self._regions[case]

    def date(self, sud: float, ouest: float, nord: float, est: float) -> str | None:
        """L'édition de la BD TOPO pour le manifeste : la plus récente des régions."""
        return max((self.edition(r)["date"] for r in self.regions(sud, ouest, nord, est)), default=None)

    def __call__(self, sud: float, ouest: float, nord: float, est: float) -> list:
        from .case import troncons_gpkg
        vus, resultat = set(), []
        for region in self.regions(sud, ouest, nord, est):
            if region not in self._gpkg:
                self._gpkg[region] = geopackage(self.dossier, region, self.edition(region))
            # Un tronçon qui passe la limite de deux régions est dans les deux.
            for t in troncons_gpkg(self._gpkg[region], sud, ouest, nord, est):
                if t["id"] not in vus:
                    vus.add(t["id"])
                    resultat.append(t)
        return resultat
