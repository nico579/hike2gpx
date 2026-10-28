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
import http.client
import json
import logging
import math
import os
import shutil
import socket
import subprocess
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib
from pathlib import Path

from nico579_commons import atomique, enfants

from . import __version__, journaux
from .providers import SOURCES as SOURCES_OFFICIELLES

journal = logging.getLogger(__name__)

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
    # Voie foot=no ou foot=private : un trottoir, un vélo poussé ou un vélo
    # admis la rendaient piétonne (audit B09, vérifié par le vrai BRouter).
    # L'interdiction explicite passe avant ces permissions déduites.
    ("assign footaccess     or issidewalk",
     "assign footaccess     and not foot=private|no\n                      or issidewalk"),
)

# Tuiles maison (OSM + BD TOPO ou ATKIS, voir fusion.py et maison.py) : une clé
# dans la table de tags marque les chemins officiels, que le profil maison rend une
# fois et demie plus coûteux qu'un chemin OSM équivalent.
CLE_IGN = "hike2gpx;0000000001 " + "\nhike2gpx;0000000001 ".join(SOURCES_OFFICIELLES) + "\n\n"
PENALITE_IGN = 0.5
# Une requête peut interdire ces chemins sans changer de tuiles : profile:
# chemins_officiels=0 (calculer(officiels=False)). BRouter remplace alors la
# première affectation de la variable (BExpression.parse) ; la valeur doit être
# un nombre. Un coût de 10000 rend la voie impraticable.
REMPLACEMENT_GLOBAL = ("---context:global",
                       "---context:global\n\nassign chemins_officiels = 1   # 0 : chemins officiels interdits\n")
REMPLACEMENT_IGN = ("assign costfactor\nadd town_penalty",
                    f"assign ign_penalty switch hike2gpx={'|'.join(SOURCES_OFFICIELLES)} "
                    f"switch chemins_officiels {PENALITE_IGN} 10000 0\n\n"
                    "assign costfactor\nadd ign_penalty\nadd town_penalty")
# Profils que lit le créateur de tuiles, absents de l'archive : pris dans le
# dépôt de BRouter, au tag de la version installée, et vérifiés.
PROFILS_CREATION_URL = f"https://raw.githubusercontent.com/abrensch/brouter/v{VERSION}/misc/profiles2/"
PROFILS_CREATION = {"all.brf": "87d49d6a2850db277e2c86a81de5e2e6727e0498e47f10662ababa0a9b56f144",
                    "softaccess.brf": "0c04a5889d61bef88b62a8abd22e76555b2d3a2299e33811b2f7e15ac7587190"}

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


def lookups_ign(source: str) -> str:
    """Table de tags de BRouter, plus la clé hike2gpx=ign à la fin du contexte way."""
    if source.count("---context:node") != 1 or "\nhike2gpx;" in source:
        raise ValueError("Table de tags BRouter inattendue.")
    return source.replace("---context:node", CLE_IGN + "---context:node")


def profil_maison(source: str) -> str:
    """Profil hike2gpx des tuiles maison : les chemins IGN coûtent davantage."""
    if source.count(REMPLACEMENT_IGN[0]) != 1 or source.count(REMPLACEMENT_GLOBAL[0]) != 1:
        raise ValueError("Profil BRouter inattendu : assemblage du coût introuvable.")
    return source.replace(*REMPLACEMENT_GLOBAL).replace(*REMPLACEMENT_IGN)


def nom_segment(lat: float, lon: float) -> str:
    """Tuile de données BRouter (5° sur 5°) qui contient un point : E5_N40.rd5."""
    lon0, lat0 = math.floor(lon / 5) * 5, math.floor(lat / 5) * 5
    return f"{'E' if lon0 >= 0 else 'W'}{abs(lon0)}_{'N' if lat0 >= 0 else 'S'}{abs(lat0)}"


def segments_zone(sud: float, ouest: float, nord: float, est: float) -> list:
    return [nom_segment(lat, lon)
            for lat in range(math.floor(sud / 5) * 5, math.floor(nord / 5) * 5 + 1, 5)
            for lon in range(math.floor(ouest / 5) * 5, math.floor(est / 5) * 5 + 1, 5)]


def rd5_entier(chemin: Path) -> bool:
    """Un RD5 complet, selon la règle de BRouter lui-même (PhysicalFile,
    1.7.10) : ses 200 premiers octets indexent ses 25 sous-tuiles, et la
    dernière entrée marque la fin des données. Le fichier s'arrête là
    (ancien format), ou porte ensuite un pied d'au moins 112 octets où
    figure le CRC de cet en-tête. Un téléchargement coupé net y échoue."""
    try:
        with open(chemin, "rb") as f:
            entete = f.read(200)
            taille = os.fstat(f.fileno()).st_size
            if len(entete) < 200:
                return False
            fin = struct.unpack(">25q", entete)[24] & 0xFFFFFFFFFFFF
            if taille == fin:
                return True
            if taille - fin < 112:
                return False
            f.seek(fin + 8)
            crc = int.from_bytes(f.read(4), "big")
    except OSError:
        return False
    # Le CRC32 de BRouter (btools.util.Crc32) ne s'inverse pas à la fin comme
    # celui de zlib ; « ^ 2 » marque le nouveau format.
    attendu = zlib.crc32(entete) ^ 0xFFFFFFFF
    return crc in (attendu, attendu ^ 2)


def _telecharger(url: str, cible: Path, sha256: str | None = None, valider=None) -> Path:
    """Publie cible une fois le fichier reçu en entier. Un transfert plus
    court que la longueur annoncée est refusé : lu par blocs, urllib ne le
    signale pas de lui-même (rapport du 2026-10-20 : un RD5 de 3 octets sur
    10 publié comme installé). valider(fichier) : contrôle de son contenu."""
    cible.parent.mkdir(parents=True, exist_ok=True)
    partiel = atomique.chemin_part(cible)
    empreinte = hashlib.sha256()
    demande = urllib.request.Request(url, headers={"User-Agent": f"hike2gpx/{__version__}"})
    try:
        recu = 0
        with urllib.request.urlopen(demande, timeout=60) as reponse, open(partiel, "wb") as sortie:
            annonce = (getattr(reponse, "headers", None) or {}).get("Content-Length")
            while bloc := reponse.read(1 << 20):
                empreinte.update(bloc)
                sortie.write(bloc)
                recu += len(bloc)
        if annonce is not None and str(annonce).isdigit() and recu != int(annonce):
            raise ErreurBRouter(f"Téléchargement interrompu : {url} ({recu} octets sur {annonce}).")
        if sha256 and empreinte.hexdigest() != sha256:
            raise ErreurBRouter(f"Empreinte inattendue pour {url} : téléchargement refusé.")
        if valider is not None and not valider(partiel):
            raise ErreurBRouter(f"Fichier reçu incomplet ou illisible : {url}.")
        atomique.remplacer(partiel, cible)
    except (OSError, http.client.HTTPException) as exc:     # réponse coupée (IncompleteRead) comprise
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
        self.maison = self.racine / "maison"
        self.profils_maison = self.maison / "profils"
        self.creation = self.maison / "creation"

    def installee(self) -> bool:
        return self.jar.is_file() and (self.profils / f"{PROFIL}.brf").is_file()

    def _archive(self) -> Path:
        """L'archive épinglée, reprise telle quelle si elle est déjà là et intacte."""
        archive = self.racine / f"brouter-{VERSION}.zip"
        if archive.is_file():
            empreinte = hashlib.sha256()
            with open(archive, "rb") as f:
                while bloc := f.read(1 << 20):
                    empreinte.update(bloc)
            if empreinte.hexdigest() == ARCHIVE_SHA256:
                return archive
        return _telecharger(ARCHIVE_URL, archive, ARCHIVE_SHA256)

    def installer(self) -> None:
        """Extrait de l'archive épinglée le serveur et les profils, puis écrit
        le profil hike2gpx."""
        archive = self._archive()
        prefixe = f"brouter-{VERSION}/"
        with zipfile.ZipFile(archive) as zf:
            for membre in zf.infolist():
                nom = membre.filename
                if membre.is_dir() or not nom.startswith(prefixe):
                    continue
                relatif = nom[len(prefixe):]
                # lib/ : les deux jars dont le créateur de tuiles a besoin pour lire le PBF.
                if relatif == self.jar.name or (relatif.startswith("profiles2/") and "/" not in relatif[10:]) \
                        or (relatif.startswith("lib/") and relatif.endswith(".jar") and "/" not in relatif[4:]):
                    destination = self.programme / relatif
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(membre) as source, open(destination, "wb") as sortie:
                        shutil.copyfileobj(source, sortie)
        self.ecrire_profil()
        self.personnalises.mkdir(parents=True, exist_ok=True)
        self.segments.mkdir(parents=True, exist_ok=True)

    def ecrire_profil(self) -> None:
        """Réécrit hike2gpx.brf depuis hiking-mountain.brf : appelé aussi à
        chaque démarrage, pour qu'un changement de REMPLACEMENTS s'applique
        sans réinstaller BRouter."""
        source = (self.profils / "hiking-mountain.brf").read_text(encoding="utf-8")
        (self.profils / f"{PROFIL}.brf").write_text(profil_hike2gpx(source), encoding="utf-8")

    def preparer_maison(self) -> None:
        """Table de tags étendue et profils des tuiles maison, à côté de ceux
        de BRouter, qui restent intacts pour le moteur standard."""
        if not any((self.programme / "lib").glob("*.jar")):
            self.installer()        # installation d'avant les tuiles maison, sans lib/
        self.creation.mkdir(parents=True, exist_ok=True)
        self.profils_maison.mkdir(parents=True, exist_ok=True)
        for nom, empreinte in PROFILS_CREATION.items():
            if not (self.creation / nom).is_file():
                _telecharger(PROFILS_CREATION_URL + nom, self.creation / nom, empreinte)
        shutil.copy2(self.profils / "trekking.brf", self.creation / "trekking.brf")
        lookups = lookups_ign((self.profils / "lookups.dat").read_text(encoding="utf-8"))
        (self.creation / "lookups.dat").write_text(lookups, encoding="utf-8")
        self.ecrire_profil_maison()

    def ecrire_profil_maison(self) -> None:
        """Table de tags étendue et profil hike2gpx du serveur maison, réécrits
        à chaque démarrage comme ecrire_profil : une correction du profil
        s'applique sans attendre une nouvelle fabrication."""
        self.profils_maison.mkdir(parents=True, exist_ok=True)
        lookups = lookups_ign((self.profils / "lookups.dat").read_text(encoding="utf-8"))
        (self.profils_maison / "lookups.dat").write_text(lookups, encoding="utf-8")
        source = (self.profils / "hiking-mountain.brf").read_text(encoding="utf-8")
        (self.profils_maison / f"{PROFIL}.brf").write_text(profil_maison(profil_hike2gpx(source)), encoding="utf-8")

    def segment_present(self, nom: str) -> bool:
        """La tuile est là, et entière : un RD5 tronqué, d'avant le contrôle
        de longueur, se retélécharge au lieu de passer pour installé."""
        chemin = self.segments / f"{nom}.rd5"
        if not chemin.is_file():
            return False
        if rd5_entier(chemin):
            return True
        journal.warning("Tuile BRouter %s incomplète (%d octets) : elle se télécharge à nouveau", nom,
                        chemin.stat().st_size)
        return False

    def telecharger_segment(self, nom: str, vers: Path | None = None) -> Path:
        """vers : un autre dossier que segments4 (l'actualisation des réglages
        y prépare les tuiles avant la bascule)."""
        if not (len(nom) <= 8 and nom[0] in "EW" and "_" in nom):
            raise ValueError(f"Nom de tuile BRouter invalide : {nom}")
        return _telecharger(SEGMENTS_URL + f"{nom}.rd5", (vers or self.segments) / f"{nom}.rd5", valider=rd5_entier)


def java() -> str:
    """Le Java qui fait tourner BRouter. Le programme figé n'emploie que celui
    qu'il embarque (_internal/jre, posé par build.py), la version éprouvée
    avec lui, jamais un Java du système ; depuis les sources, c'est celui du
    système."""
    nom = "java.exe" if os.name == "nt" else "java"
    if getattr(sys, "frozen", False):
        embarque = Path(sys._MEIPASS) / "jre" / "bin" / nom
        if embarque.is_file():
            return str(embarque)
        raise ErreurBRouter("Le Java du programme est introuvable : réinstallez hike2gpx.")
    candidats = [shutil.which("java")]
    if os.environ.get("JAVA_HOME"):
        candidats.append(str(Path(os.environ["JAVA_HOME"]) / "bin" / nom))
    for chemin in candidats:
        if chemin and Path(chemin).is_file():
            return chemin
    raise ErreurBRouter("Java (11 ou plus) est nécessaire pour faire tourner BRouter.")


def port_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def fabriquer_tuiles(inst: Installation, pbf: Path, dossier: Path, *, relief: Path | None = None,
                     tas: str = "1g") -> Path:
    """Tuiles .rd5 d'un fichier OSM (PBF) par le créateur de tuiles de BRouter,
    dans dossier/segments. Options du script officiel, plus avoidMapPolling :
    sans elle, le lecteur attend 10 s par tour que le fichier grossisse.

    relief : dossier des altitudes .bef à 1 seconde d'arc (srtm_x_y.bef, voir
    relief.py) ; sans lui, les tuiles n'ont pas d'altitude.
    tas : mémoire de Java ; 1 Go suffit à une petite zone, une case de 5°
    dense en demande quatre ou cinq."""
    librairies = sorted((inst.programme / "lib").glob("*.jar"))
    if not librairies:
        raise ErreurBRouter("BRouter incomplet pour fabriquer des tuiles : réinstallez-le.")
    shutil.rmtree(dossier, ignore_errors=True)
    for d in ("nodetiles", "waytiles", "waytiles55", "nodes55", "unodes55", "segments", "srtm1", "srtm3"):
        (dossier / d).mkdir(parents=True)
    commande = [java(), f"-Xmx{tas}", "-DuseDenseMaps=true", "-DavoidMapPolling=true",
                "-cp", os.pathsep.join(str(p) for p in [inst.jar, *librairies])]
    creation = inst.creation
    etapes = [
        ["btools.mapcreator.OsmFastCutter", str(creation / "lookups.dat"), "nodetiles", "waytiles", "nodes55",
         "waytiles55", "bordernids.dat", "relations.dat", "restrictions.dat", str(creation / "all.brf"),
         str(creation / "trekking.brf"), str(creation / "softaccess.brf"), str(pbf)],
        ["btools.mapcreator.PosUnifier", "nodes55", "unodes55", "bordernids.dat", "bordernodes.dat",
         str(relief) if relief else "srtm1", "srtm3"],
        ["-DskipEncodingCheck=true", "btools.mapcreator.WayLinker", "unodes55", "waytiles55", "bordernodes.dat",
         "restrictions.dat", str(creation / "lookups.dat"), str(creation / "all.brf"), "segments", "rd5"],
    ]
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    for etape in etapes:
        r = enfants.lancer(commande + etape, cwd=dossier, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", stdin=subprocess.DEVNULL, **options)
        classe = next(e for e in etape if e.startswith("btools")).rsplit(".", 1)[-1]
        # La sortie de chaque étape reste à côté (WayLinker.log…) : une étape
        # peut finir sans erreur et sans tuile (essai GitHub Actions du
        # 2026-10-28, E5_N45), et il faut alors savoir ce qu'elle a dit.
        (dossier / f"{classe}.log").write_text(f"{r.stdout or ''}\n{r.stderr or ''}", encoding="utf-8")
        if r.returncode:
            raise ErreurBRouter(f"Fabrication des tuiles impossible ({classe}) : {(r.stderr or r.stdout).strip()[-300:]}")
    return dossier / "segments"


class Serveur:
    """Un serveur BRouter de cette instance, arrêté par son propre PID, et qui
    meurt avec hike2gpx si celui-ci meurt sans l'arrêter (console fermée,
    processus tué) : nico579_commons.enfants. Par défaut sur les tuiles et
    profils de BRouter ; les tuiles maison passent leurs propres dossiers."""

    def __init__(self, installation: Installation, port: int | None = None, *,
                 segments: Path | None = None, profils: Path | None = None):
        self.installation, self.port = installation, port or port_libre()
        self.segments, self.profils = segments, profils
        self.processus = None

    def demarrer(self, attente_s: float = 30.0) -> None:
        inst = self.installation
        if self.profils is None:
            inst.ecrire_profil()
        elif self.profils == inst.profils_maison:
            inst.ecrire_profil_maison()
        chemin_log = journaux.dossier(inst.racine.parent) / "brouter.log"
        chemin_log.parent.mkdir(parents=True, exist_ok=True)
        sortie = open(chemin_log, "ab")
        commande = [java(), MEMOIRE, f"-DmaxRunningTime={DELAI_CALCUL_S}", "-cp", str(inst.jar),
                    "btools.server.RouteServer", str(self.segments or inst.segments), str(self.profils or inst.profils),
                    str(inst.personnalises), str(self.port), "4", "127.0.0.1"]
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
        debut = time.monotonic()
        try:
            self.processus = enfants.demarrer(commande, cwd=inst.racine, stdout=sortie,
                                              stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **options)
        finally:
            sortie.close()
        if not self.processus.rattache:
            journal.warning("BRouter (PID %d) n'est pas lié à hike2gpx : il lui survivrait "
                            "si hike2gpx mourait sans l'arrêter", self.processus.pid)
        fin = debut + attente_s
        while time.monotonic() < fin:
            if self.processus.poll() is not None:
                journal.error("BRouter s'est arrêté au démarrage (port %d, voir brouter.log)", self.port)
                raise ErreurBRouter("BRouter s'est arrêté au démarrage (voir brouter.log).")
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                    journal.info("BRouter démarré en %.1f s : port %d, PID %d, tuiles %s", time.monotonic() - debut,
                                 self.port, self.processus.pid, self.segments or inst.segments)
                    return
            except OSError:
                time.sleep(0.2)
        self.arreter()
        journal.error("BRouter ne répond pas après %d s (port %d)", attente_s, self.port)
        raise ErreurBRouter("BRouter ne répond pas après son démarrage.")

    def arreter(self) -> None:
        if self.processus and self.processus.poll() is None:
            self.processus.terminate()
            try:
                self.processus.wait(5)
            except subprocess.TimeoutExpired:
                self.processus.kill()
                # Attendu aussi : un processus jamais ramassé garderait son
                # lien (le guetteur de nico579_commons.enfants) jusqu'à la fin
                # de hike2gpx.
                try:
                    self.processus.wait(5)
                except subprocess.TimeoutExpired:
                    pass
            journal.info("BRouter arrêté : port %d, PID %d", self.port, self.processus.pid)
        self.processus = None


def _coupe(coupe, poids=None) -> str:
    valeurs = [f"{v:.7f}" for point in coupe for v in point]
    if poids is not None:
        valeurs.append(str(poids))
    return ",".join(valeurs)


def requete(points, franchissements=(), *, strict: bool = False, profil: str = PROFIL,
            poids: int = POIDS_A_VERIFIER, officiels: bool = True) -> str:
    """Chemin et paramètres d'une requête BRouter. points : [(lat, lon)].
    Un franchissement bloquant devient une coupe sans poids ; un
    franchissement à vérifier, une coupe pondérée, ou interdite en mode
    strict.

    Pour un segment qui croise plusieurs coupes, BRouter garde le coût de la
    dernière de la liste (RoutingContext.calcDistance) : une coupe pondérée
    placée après une coupe interdite rendait le segment franchissable (audit
    B10, vérifié par le vrai BRouter). Les coupes interdites passent donc en
    dernier.

    officiels=False interdit les chemins officiels d'une RD5 enrichie (variable
    chemins_officiels du profil maison) : le même lot sert les deux réglages."""
    interdites = [f["statut"] == "blocked" or strict for f in franchissements]
    lignes = [_coupe(c, None if interdite else poids)
              for interdite in (False, True)
              for f, i in zip(franchissements, interdites) if i == interdite for c in f["coupes"]]
    parametres = {"lonlats": "|".join(f"{lon:.6f},{lat:.6f}" for lat, lon in points),
                  "profile": profil, "alternativeidx": "0", "format": "geojson"}
    if lignes:
        parametres["polylines"] = "|".join(lignes)
    if not officiels:
        parametres["profile:chemins_officiels"] = "0"
    return "/brouter?" + urllib.parse.urlencode(parametres, safe=",|:")


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
