"""Carte OpenStreetMap hors ligne : un fichier Mapsforge par carré de 1°.

Les tuiles d'openstreetmap.org ne se recopient pas : leur serveur interdit le
téléchargement en masse et l'usage hors ligne. Les données d'OSM, elles, sont
libres (ODbL). Le PC fait donc comme Locus Map ou OpenAndroMaps : il part de
l'extrait Geofabrik de la région et en tire une carte vectorielle au format
Mapsforge, que le téléphone dessine lui-même. Un carré de 1° pèse quelques
dizaines de Mo, là où ses tuiles en image en pèseraient un millier.

L'outillage est celui de tout le monde, épinglé par son empreinte comme
BRouter : Osmosis, le couteau suisse des fichiers OSM, et son greffon
mapsforge-map-writer (le même couple que lidar2map). Le greffon s'annonce de
lui-même à Osmosis par son fichier osmosis-plugins.conf : il suffit de le
mettre sur le chemin de classes de Java, sans rien poser dans le dossier
personnel de l'utilisateur.

Rangement, sous le dossier de données :
  mapsforge/osmosis-0.49.2/lib/*.jar, mapsforge-map-writer-…jar   l'outillage
  mapsforge/extraits/provence-alpes-cote-d-azur.osm.pbf           l'extrait brut
  hors-ligne/fonds/N43E006-osm.map                                la carte, avec les autres fonds

L'extrait brut est gardé le temps du délai de renouvellement : les carrés
voisins d'une même région le relisent sans le retélécharger. (geofabrik.py,
lui, n'en garde que les chemins, dans une base : il ne suffit pas à une carte.)
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path

from nico579_commons import atomique, enfants

from . import brouter, fonds, geofabrik

journal = logging.getLogger(__name__)

OSMOSIS_VERSION = "0.49.2"
OSMOSIS_URL = (f"https://github.com/openstreetmap/osmosis/releases/download/{OSMOSIS_VERSION}/"
               f"osmosis-{OSMOSIS_VERSION}.zip")
OSMOSIS_SHA256 = "6950f1dfdbe4337ad193b0501309351426c403fab770061c9ddca9a28aefc26d"
GREFFON_VERSION = "0.25.0"
GREFFON = f"mapsforge-map-writer-{GREFFON_VERSION}-jar-with-dependencies.jar"
GREFFON_URL = f"https://repo1.maven.org/maven2/org/mapsforge/mapsforge-map-writer/{GREFFON_VERSION}/{GREFFON}"
GREFFON_SHA256 = "c132d97d492707b30f2bf0c594ce9009eac9a8bde4e6be8ad97a005a506f4b68"

# La clé du fond dans la page (providers : « osm ») et ce que la carte annonce.
SOURCE = "osm"
TITRE = "OpenStreetMap"
ATTRIBUTION = "© les contributeurs d'OpenStreetMap"
SUFFIXE = ".map"
# Les voies sont coupées au bord du carré par le greffon ; la boîte lue dans
# l'extrait déborde un peu, pour qu'une voie qui sort du carré garde ses nœuds.
MARGE_DEG = 0.05
# Le greffon range ses données sur le disque (type=hd) : le tas de Java reste
# modeste, un quart de la mémoire de la machine entre 1 et 2 Go. Un essai à
# 4 Go, le 2026-11-10, a mis un PC de 8 Go à court de mémoire.
TAS_MIN, TAS_MAX = 1 << 30, 2 << 30


class ErreurCarte(RuntimeError):
    """La carte ne peut pas être fabriquée ; le message va à la page."""


class Abandon(Exception):
    """L'utilisateur a arrêté la fabrication."""


class Outils:
    """Osmosis et le greffon Mapsforge, rangés dans <dossier>/mapsforge."""

    def __init__(self, dossier):
        self.racine = Path(dossier) / "mapsforge"
        self.osmosis = self.racine / f"osmosis-{OSMOSIS_VERSION}"
        self.greffon = self.racine / GREFFON
        self.extraits = self.racine / "extraits"
        # Les fichiers de travail d'Osmosis (index et tas du greffon, plusieurs
        # centaines de Mo), dans un dossier à eux, vidé avant et après chaque carte.
        self.travail = self.racine / "travail"

    def installes(self) -> bool:
        return (self.osmosis / "lib" / f"osmosis-core-{OSMOSIS_VERSION}.jar").is_file() and self.greffon.is_file()

    def installer(self) -> None:
        """Télécharge les deux outils, chacun vérifié par son empreinte, et
        n'extrait de l'archive d'Osmosis que ses bibliothèques."""
        archive = brouter._telecharger(OSMOSIS_URL, self.racine / f"osmosis-{OSMOSIS_VERSION}.zip", OSMOSIS_SHA256)
        prefixe = f"osmosis-{OSMOSIS_VERSION}/lib/"
        with zipfile.ZipFile(archive) as zf:
            for membre in zf.infolist():
                nom = membre.filename
                if membre.is_dir() or not nom.startswith(prefixe) or "/" in nom[len(prefixe):]:
                    continue
                cible = self.osmosis / "lib" / nom[len(prefixe):]
                cible.parent.mkdir(parents=True, exist_ok=True)
                cible.write_bytes(zf.read(membre))
        archive.unlink(missing_ok=True)
        brouter._telecharger(GREFFON_URL, self.greffon, GREFFON_SHA256)

    def chemin_de_classes(self) -> str:
        return os.pathsep.join([str(self.osmosis / "lib" / "*"), str(self.greffon)])


def nom_carte(carre: str) -> str:
    return fonds.nom_fond(carre, SOURCE)


def decrire(chemin: Path) -> dict:
    """La carte telle que la décrivent la page et le catalogue du partage, à
    la manière de fonds.decrire ; « format » la distingue d'un fond en images."""
    chemin = Path(chemin)
    carre = chemin.stem.rsplit("-", 1)[0]
    if not fonds.carre_valide(carre):
        raise ValueError(f"Nom de carte inattendu : {chemin.name}")
    return {"nom": chemin.stem, "zone": list(fonds.boite_carre(carre)), "zoom": [0, 21], "source": SOURCE,
            "format": "map", "attribution": ATTRIBUTION, "octets": chemin.stat().st_size}


def regions_du_carre(regions: list, zone: tuple) -> list:
    """Les extraits Geofabrik à lire pour le carré : le plus petit qui le
    contient, sauf si de plus petits le couvrent ensemble (un carré à cheval
    sur une frontière), comme geofabrik.regions_de_tuile pour une tuile. Les
    points du carré qu'aucun extrait ne couvre sont en mer : ils ne comptent
    pas. Liste vide : le carré est tout en mer."""
    sud, ouest, nord, est = zone
    points = {(sud + (nord - sud) * a / 4, ouest + (est - ouest) * b / 4) for a in range(5) for b in range(5)}
    proches = [r for r in regions if not (r["bornes"][0] > nord or r["bornes"][2] < sud
                                         or r["bornes"][1] > est or r["bornes"][3] < ouest)]
    couverts = {p for p in points if any(geofabrik.contient_point(r, *p) for r in proches)}
    if not couverts:
        return []
    entieres = [r for r in proches if all(geofabrik.contient_point(r, *p) for p in couverts)]
    seule = min(entieres, key=geofabrik._surface) if entieres else None
    reste, choisies = set(couverts), []
    for r in sorted(proches, key=geofabrik._surface):
        if seule is not None and geofabrik._surface(r) >= geofabrik._surface(seule):
            break
        dedans = {p for p in reste if geofabrik.contient_point(r, *p)}
        if dedans:
            choisies.append(r)
            reste -= dedans
            if not reste:
                return choisies
    return [seule] if seule else choisies


def extrait(outils: Outils, region: dict, jours: int, *, suivi=None, continuer=None) -> Path:
    """L'extrait brut de la région, repris s'il est plus jeune que le délai de
    renouvellement, sinon téléchargé et vérifié par son MD5 (geofabrik)."""
    pbf = outils.extraits / f"{region['id'].replace('/', '__')}.osm.pbf"
    if pbf.is_file() and time.time() - pbf.stat().st_mtime < jours * 86400:
        return pbf
    pbf.parent.mkdir(parents=True, exist_ok=True)
    try:
        geofabrik._telecharger(region["pbf"], pbf, suivi=suivi, continuer=continuer)
    except geofabrik.Abandon as exc:
        raise Abandon() from exc
    except geofabrik.ErreurExtrait as exc:
        raise ErreurCarte(str(exc)) from exc
    return pbf


def _tas() -> str:
    memoire = brouter.memoire_physique()
    octets = TAS_MIN if memoire is None else max(TAS_MIN, min(TAS_MAX, memoire // 4))
    return f"{octets >> 20}m"


def commande(outils: Outils, pbfs: list, cible: Path, zone: tuple) -> list:
    """Osmosis : chaque extrait réduit à la boîte du carré, le tout fusionné,
    puis écrit en carte Mapsforge coupée au carré exact."""
    sud, ouest, nord, est = zone
    ligne = [brouter.java(), f"-Xmx{_tas()}", f"-Djava.io.tmpdir={outils.travail}", f"-Duser.home={outils.racine}",
             "-cp", outils.chemin_de_classes(),
             "org.openstreetmap.osmosis.core.Osmosis", "-q"]
    for pbf in pbfs:
        ligne += ["--read-pbf", f"file={pbf}", "--bounding-box", f"left={ouest - MARGE_DEG}",
                  f"right={est + MARGE_DEG}", f"top={nord + MARGE_DEG}", f"bottom={sud - MARGE_DEG}"]
    ligne += ["--merge"] * (len(pbfs) - 1)
    return ligne + ["--mapfile-writer", f"file={cible}", f"bbox={sud},{ouest},{nord},{est}", "type=hd"]


def isolement(outils: Outils) -> dict:
    """Le dossier courant et l'environnement du lancement. Osmosis cherche
    aussi des greffons dans ./plugins, dans le dossier personnel et, sous
    Windows, dans %APPDATA% : la copie du greffon qu'un autre logiciel y a
    posée (lidar2map le fait) se déclarerait une seconde fois, et Osmosis
    refuserait de partir (« Task type "mapfile-writer" already exists »).
    Avec -Duser.home (commande), il ne voit donc que nos outils."""
    return {"cwd": outils.racine, "env": {**os.environ, "APPDATA": str(outils.racine)}}


# Ce que le greffon laisse quand Osmosis est interrompu : ses index et ses tas.
# Les versions 0.9.8 et 0.9.9 les écrivaient dans le dossier des cartes.
RESTES = ("idx*.tmp", "heap*.tmp")


def nettoyer(outils: Outils, dossier_cartes: Path | None = None) -> int:
    """Vide le dossier de travail d'Osmosis, et efface les restes qu'une
    fabrication interrompue a pu laisser dans le dossier des cartes. Rend les
    octets libérés."""
    fichiers = [p for p in outils.travail.rglob("*") if p.is_file()] if outils.travail.is_dir() else []
    if dossier_cartes is not None and Path(dossier_cartes).is_dir():
        fichiers += [p for motif in RESTES for p in Path(dossier_cartes).glob(motif) if p.is_file()]
    octets = 0
    for p in fichiers:
        try:
            taille = p.stat().st_size
            p.unlink()
            octets += taille
        except OSError as exc:           # encore pris par un Osmosis qui finit
            journal.warning("Reste d'Osmosis laissé : %s (%s)", p, exc)
    shutil.rmtree(outils.travail, ignore_errors=True)
    if octets:
        journal.info("Restes d'Osmosis effacés : %d Mo", octets // 10 ** 6)
    return octets


def _surveiller(processus, continuer) -> None:
    while processus.poll() is None:
        if not continuer():
            processus.terminate()
            return
        time.sleep(0.5)


def fabriquer(dossier, chemin: Path, zone: tuple, *, suivi=None, continuer=None) -> dict:
    """Fabrique la carte du carré dans chemin et la décrit. suivi(etape,
    faites, total) : « outils », « extraits » (en centièmes) puis « carte »
    (sans mesure : Osmosis ne dit rien de son avancée). continuer() faux arrête
    tout (Abandon) ; rien de partiel ne reste à la place de la carte."""
    suivi = suivi or (lambda *_: None)
    continuer = continuer or (lambda: True)
    outils = Outils(dossier)
    if not outils.installes():
        suivi("outils", 0, 0)
        try:
            outils.installer()
        except brouter.ErreurBRouter as exc:
            raise ErreurCarte(str(exc)) from exc
    regions = regions_du_carre(geofabrik.regions_attendues(dossier), zone)
    if not regions:
        raise ErreurCarte("Aucune donnée OpenStreetMap pour ce carré (en mer ?).")
    jours = geofabrik.jours_renouvellement(dossier)
    pbfs = []
    for rang, region in enumerate(regions):
        def avance(fraction, rang=rang):
            suivi("extraits", round(100 * (rang + (fraction or 0)) / len(regions)), 100)
        pbfs.append(extrait(outils, region, jours, suivi=avance, continuer=continuer))
    if not continuer():
        raise Abandon()
    suivi("carte", 0, 0)
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    nettoyer(outils, chemin.parent)
    outils.travail.mkdir(parents=True, exist_ok=True)
    partiel = atomique.chemin_part(chemin)
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    debut, fin = time.monotonic(), []
    try:
        with enfants.demarrer(commande(outils, pbfs, partiel, zone), stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                              errors="replace", **isolement(outils), **options) as processus:
            threading.Thread(target=_surveiller, args=(processus, continuer), daemon=True,
                             name="mapsforge-surveillance").start()
            for ligne in processus.stdout:
                fin = (fin + [ligne.rstrip()])[-20:]
        if not continuer():
            raise Abandon()
        if processus.returncode or not partiel.is_file() or not partiel.stat().st_size:
            journal.error("Osmosis en échec (code %s) : %s", processus.returncode, " | ".join(fin))
            raise ErreurCarte("Fabrication de la carte OpenStreetMap impossible : " + " | ".join(fin)[-300:])
        atomique.remplacer(partiel, chemin)
    finally:
        partiel.unlink(missing_ok=True)
        nettoyer(outils)
    journal.info("Carte %s : %d Mo depuis %s, en %.0f s", chemin.name, chemin.stat().st_size // 10 ** 6,
                 ", ".join(r["id"] for r in regions), time.monotonic() - debut)
    return decrire(chemin)
