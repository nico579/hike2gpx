"""Moteur BRouter local : installation, profil hike2gpx, serveur et calcul
d'itinéraire avec les coupes des franchissements.

BRouter (Java, licence MIT) est le moteur de randonnée de référence, celui que
Locus utilise. hike2gpx ne le modifie pas : à chaque calcul, il lui passe les
franchissements à éviter sous forme de lignes interdites (paramètre
polylines). Dans son code (RoutingContext, v1.7.10), une ligne sans poids
retire du calcul tout tronçon qui la coupe (nogoCost = -1) ; une ligne avec
poids ajoute ce poids au coût du tronçon.

Le profil hike2gpx est hiking-mountain, le profil « Randonnée » de
brouter-web, à deux corrections près, écrites dans REMPLACEMENTS : un chemin
ou un nœud foot=no ne se parcourt plus à pied sous prétexte qu'un vélo y
passerait.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from nico579_commons import atomique

from . import __version__

VERSION = "1.7.10"
ARCHIVE_URL = f"https://github.com/abrensch/brouter/releases/download/v{VERSION}/brouter-{VERSION}.zip"
ARCHIVE_SHA256 = "023fec3ba997758e8cd7ab9e1bae52e962af3f00b57683e3de86b84ffad01532"
SEGMENTS_URL = "https://brouter.de/brouter/segments4/"
PROFIL = "hike2gpx"
# Coût d'un franchissement « à vérifier », à peu près en mètres de bon
# chemin : un détour plus court l'évite, un plus long le traverse.
POIDS_A_VERIFIER = 300
MEMOIRE = "-Xmx768m"
DELAI_CALCUL_S = 60

REMPLACEMENTS = (
    # Voie interdite aux piétons mais ouverte aux vélos : hiking-mountain la
    # parcourait avec une pénalité de 4 (ou 16 sur un itinéraire cyclable).
    ("assign accesspenalty switch footaccess 0 switch bikeaccess 4 switch foot=use_sidepath 10 "
     "switch any_hiking_route 12 switch any_cycleroute 16 100000",
     "assign accesspenalty switch footaccess 0 switch foot=use_sidepath 10 "
     "switch any_hiking_route 12 100000"),
    # Nœud foot=no : franchi dès qu'un vélo pouvait passer. On ne garde que la
    # tolérance de hiking-mountain sur les itinéraires de randonnée balisés.
    ("assign initialcost switch or bikeaccess footaccess 0 1000000",
     "assign initialcost switch or nodeaccessgranted=yes footaccess 0 1000000"),
)

MESSAGES = (
    ("datafile", "Données BRouter absentes pour cette zone."),
    ("not found", "Aucun chemin praticable trouvé près d'un des points."),
    ("no track found", "Aucun itinéraire ne respecte les barrières entre ces points."),
    ("target island", "Le point d'arrivée est isolé du réseau praticable."),
    ("operation killed", "Calcul trop long : rapprochez les points."),
)


class ErreurBRouter(RuntimeError):
    """Le moteur n'a pas pu calculer l'itinéraire."""


def profil_hike2gpx(source: str) -> str:
    texte = source
    for avant, apres in REMPLACEMENTS:
        if texte.count(avant) != 1:
            raise ValueError(f"Profil BRouter inattendu, ligne introuvable : {avant[:40]}…")
        texte = texte.replace(avant, apres)
    return (f"# hike2gpx : hiking-mountain de BRouter {VERSION}, foot=no respecté sur les voies\n"
            "# et les nœuds (voir hike2gpx/brouter.py, REMPLACEMENTS).\n" + texte)


def nom_segment(lat: float, lon: float) -> str:
    """Tuile de données BRouter (5° sur 5°) qui contient un point : E5_N40.rd5."""
    lon0, lat0 = math.floor(lon / 5) * 5, math.floor(lat / 5) * 5
    return f"{'E' if lon0 >= 0 else 'W'}{abs(lon0)}_{'N' if lat0 >= 0 else 'S'}{abs(lat0)}"


def segments_zone(sud: float, ouest: float, nord: float, est: float) -> list:
    return [nom_segment(lat, lon)
            for lat in range(math.floor(sud / 5) * 5, math.floor(nord / 5) * 5 + 1, 5)
            for lon in range(math.floor(ouest / 5) * 5, math.floor(est / 5) * 5 + 1, 5)]


def _telecharger(url: str, cible: Path, sha256: str | None = None) -> Path:
    cible.parent.mkdir(parents=True, exist_ok=True)
    partiel = atomique.chemin_part(cible)
    empreinte = hashlib.sha256()
    demande = urllib.request.Request(url, headers={"User-Agent": f"hike2gpx/{__version__}"})
    try:
        with urllib.request.urlopen(demande, timeout=60) as reponse, open(partiel, "wb") as sortie:
            while bloc := reponse.read(1 << 20):
                empreinte.update(bloc)
                sortie.write(bloc)
        if sha256 and empreinte.hexdigest() != sha256:
            raise ErreurBRouter(f"Empreinte inattendue pour {url} : téléchargement refusé.")
        atomique.remplacer(partiel, cible)
    except OSError as exc:
        raise ErreurBRouter(f"Téléchargement impossible : {url} ({exc}).") from exc
    finally:
        partiel.unlink(missing_ok=True)
    return cible


class Installation:
    """BRouter rangé dans <dossier>/brouter : programme, profils, données."""

    def __init__(self, dossier):
        self.racine = Path(dossier) / "brouter"
        self.programme = self.racine / f"brouter-{VERSION}"
        self.jar = self.programme / f"brouter-{VERSION}-all.jar"
        self.profils = self.programme / "profiles2"
        self.personnalises = self.racine / "customprofiles"
        self.segments = self.racine / "segments4"

    def installee(self) -> bool:
        return self.jar.is_file() and (self.profils / f"{PROFIL}.brf").is_file()

    def installer(self) -> None:
        """Télécharge l'archive épinglée, en extrait le serveur et les profils,
        puis écrit le profil hike2gpx."""
        archive = _telecharger(ARCHIVE_URL, self.racine / f"brouter-{VERSION}.zip", ARCHIVE_SHA256)
        prefixe = f"brouter-{VERSION}/"
        with zipfile.ZipFile(archive) as zf:
            for membre in zf.infolist():
                nom = membre.filename
                if membre.is_dir() or not nom.startswith(prefixe):
                    continue
                relatif = nom[len(prefixe):]
                if relatif == self.jar.name or (relatif.startswith("profiles2/") and "/" not in relatif[10:]):
                    destination = self.programme / relatif
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(membre) as source, open(destination, "wb") as sortie:
                        shutil.copyfileobj(source, sortie)
        source = (self.profils / "hiking-mountain.brf").read_text(encoding="utf-8")
        (self.profils / f"{PROFIL}.brf").write_text(profil_hike2gpx(source), encoding="utf-8")
        self.personnalises.mkdir(parents=True, exist_ok=True)
        self.segments.mkdir(parents=True, exist_ok=True)

    def segment_present(self, nom: str) -> bool:
        return (self.segments / f"{nom}.rd5").is_file()

    def telecharger_segment(self, nom: str) -> Path:
        if not (len(nom) <= 8 and nom[0] in "EW" and "_" in nom):
            raise ValueError(f"Nom de tuile BRouter invalide : {nom}")
        return _telecharger(SEGMENTS_URL + f"{nom}.rd5", self.segments / f"{nom}.rd5")


def java() -> str:
    candidats = [shutil.which("java")]
    if os.environ.get("JAVA_HOME"):
        candidats.append(str(Path(os.environ["JAVA_HOME"]) / "bin" / ("java.exe" if os.name == "nt" else "java")))
    for chemin in candidats:
        if chemin and Path(chemin).is_file():
            return chemin
    raise ErreurBRouter("Java (11 ou plus) est nécessaire pour faire tourner BRouter.")


def port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Serveur:
    """Le serveur BRouter de cette instance, arrêté par son propre PID."""

    def __init__(self, installation: Installation, port: int | None = None):
        self.installation, self.port = installation, port or port_libre()
        self.processus = None

    def demarrer(self, attente_s: float = 30.0) -> None:
        inst = self.installation
        journal = open(inst.racine / "brouter.log", "ab")
        commande = [java(), MEMOIRE, f"-DmaxRunningTime={DELAI_CALCUL_S}", "-cp", str(inst.jar),
                    "btools.server.RouteServer", str(inst.segments), str(inst.profils),
                    str(inst.personnalises), str(self.port), "4", "127.0.0.1"]
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
        try:
            self.processus = subprocess.Popen(commande, cwd=inst.racine, stdout=journal,
                                              stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **options)
        finally:
            journal.close()
        fin = time.monotonic() + attente_s
        while time.monotonic() < fin:
            if self.processus.poll() is not None:
                raise ErreurBRouter("BRouter s'est arrêté au démarrage (voir brouter.log).")
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                    return
            except OSError:
                time.sleep(0.2)
        self.arreter()
        raise ErreurBRouter("BRouter ne répond pas après son démarrage.")

    def arreter(self) -> None:
        if self.processus and self.processus.poll() is None:
            self.processus.terminate()
            try:
                self.processus.wait(5)
            except subprocess.TimeoutExpired:
                self.processus.kill()
        self.processus = None


def _coupe(coupe, poids=None) -> str:
    valeurs = [f"{v:.7f}" for point in coupe for v in point]
    if poids is not None:
        valeurs.append(str(poids))
    return ",".join(valeurs)


def requete(points, franchissements=(), *, strict: bool = False, profil: str = PROFIL,
            poids: int = POIDS_A_VERIFIER) -> str:
    """Chemin et paramètres d'une requête BRouter. points : [(lat, lon)].
    Un franchissement bloquant devient une coupe sans poids ; un
    franchissement à vérifier, une coupe pondérée, ou interdite en mode
    strict."""
    lignes = [_coupe(c, None if f["statut"] == "blocked" or strict else poids)
              for f in franchissements for c in f["coupes"]]
    parametres = {"lonlats": "|".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points),
                  "profile": profil, "alternativeidx": "0", "format": "geojson"}
    if lignes:
        parametres["polylines"] = "|".join(lignes)
    return "/brouter?" + urllib.parse.urlencode(parametres, safe=",|")


def calculer(port: int, points, franchissements=(), **options) -> dict:
    """Itinéraire GeoJSON de BRouter (une Feature LineString [lon, lat, alt])."""
    url = f"http://127.0.0.1:{port}" + requete(points, franchissements, **options)
    ouvreur = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with ouvreur.open(url, timeout=DELAI_CALCUL_S + 15) as reponse:
            donnees = json.loads(reponse.read())
    except urllib.error.HTTPError as exc:
        texte = exc.read().decode("utf-8", "replace").strip()
        message = next((m for cle, m in MESSAGES if cle in texte.lower()), None)
        raise ErreurBRouter(message or f"BRouter : {texte[:200]}") from exc
    except (OSError, ValueError) as exc:
        raise ErreurBRouter(f"BRouter ne répond pas ({exc}).") from exc
    features = donnees.get("features") if isinstance(donnees, dict) else None
    if not features or features[0].get("geometry", {}).get("type") != "LineString":
        raise ErreurBRouter("Réponse BRouter inattendue.")
    return features[0]
