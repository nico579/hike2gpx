"""Client du serveur personnel : API distante, repli local si inaccessible."""
from __future__ import annotations

import json
import gzip
import hashlib
import logging
import os
import secrets
import shutil
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from nico579_commons import atomique
from . import providers, rd5_fragments

journal = logging.getLogger(__name__)


ROUTES_GET_ZONE = {"osm"} | {p.calque for p in providers.SOURCES.values()}
ROUTES_CLOUD = ROUTES_GET_ZONE
ROUTES_AVEC_ZONE = ROUTES_GET_ZONE | {"disponibilite"}
CACHE_CALQUES_S = 24 * 3600
FORMAT_CALQUES_CACHE = 1


class Indisponible(Exception):
    """Connexion au serveur de données indisponible."""


def valider_adresse(adresse: str) -> str:
    adresse = adresse.strip().rstrip("/")
    if not adresse:
        return ""
    try:
        url = urllib.parse.urlsplit(adresse)
        port = url.port
    except ValueError as exc:
        raise ValueError("Adresse du serveur invalide.") from exc
    local_http = url.scheme == "http" and url.hostname in {"127.0.0.1", "localhost"}
    if (not (url.scheme == "https" or local_http) or not url.hostname or url.username or url.password
            or url.path or url.query or url.fragment or port == 0):
        raise ValueError("Indiquez une adresse HTTPS (HTTP accepté sur localhost), sans chemin ni identifiants.")
    return adresse


class Client:
    def __init__(self, preferences):
        self.preferences = preferences
        self._verrou = threading.Lock()
        self._expiration = 0.0
        self._etat = {"actif": False, "raison": "non_configure"}

    def invalider(self):
        with self._verrou:
            self._expiration = 0.0

    def _config(self):
        prefs = atomique.lire_json(self.preferences, {})
        return prefs if isinstance(prefs, dict) else {}

    @staticmethod
    def _url(config, route, args=()):
        url = config["serveur_url"] + "/api/" + route
        if route == "paquet-zone":
            zone, source, officiel, strict = args
            q = dict(zip(("s", "w", "n", "e"), zone))
            q.update(source=source, officiel=int(bool(officiel)), strict=int(bool(strict)))
            url += "?" + urllib.parse.urlencode(q)
        elif route in ROUTES_AVEC_ZONE:
            zone = args[0] if args else None
            if zone is not None:
                q = dict(zip(("s", "w", "n", "e"), zone))
                if len(args) > 1 and args[1] is not None:
                    q["vue"] = args[1]
                url += "?" + urllib.parse.urlencode(q)
        return url

    @staticmethod
    def _requete(config, route, methode="GET", args=(), payload=None):
        debut = time.monotonic()
        donnees = json.dumps(payload).encode("utf-8") if methode == "POST" else None
        entetes = {"Accept": "application/json"}
        if donnees is not None:
            entetes["Content-Type"] = "application/json"
        demande = urllib.request.Request(Client._url(config, route, args), data=donnees,
                                         headers=entetes, method=methode)
        try:
            with urllib.request.urlopen(demande, timeout=5) as reponse:
                corps = reponse.read(32 * 1024 * 1024 + 1)
                if len(corps) > 32 * 1024 * 1024:
                    raise Indisponible("Réponse du serveur trop volumineuse.")
                journal.info("Cloud HTTP %s %s : %d octets reçus en %.2f s",
                             methode, route, len(corps), time.monotonic() - debut)
                return json.loads(corps)
        except (OSError, ValueError) as exc:
            journal.warning("Cloud HTTP %s %s : échec après %.2f s : %s",
                            methode, route, time.monotonic() - debut, exc)
            raise Indisponible(str(exc)) from exc

    def etat(self, *, force=False):
        config = self._config()
        adresse = config.get("serveur_url", "")
        if not adresse:
            return {"actif": False, "raison": "non_configure", "adresse": ""}
        with self._verrou:
            if not force and time.monotonic() < self._expiration:
                return {**self._etat, "adresse": adresse}
        try:
            infos = self._requete(config, "etat")
            if infos.get("app") != "hike2gpx" or infos.get("mode_serveur") is not True:
                raise Indisponible("L'adresse ne répond pas comme serveur hike2gpx.")
            etat = {"actif": True, "raison": "", "adresse": adresse}
        except Indisponible as exc:
            etat = {"actif": False, "raison": str(exc), "adresse": adresse}
        with self._verrou:
            self._etat = etat
            self._expiration = time.monotonic() + (15 if etat["actif"] else 5)
        return etat

    def demander(self, route, methode, args=(), payload=None):
        config = self._config()
        try:
            return self._requete(config, route, methode, args, payload)
        except Indisponible:
            self.invalider()
            raise

    def calque(self, route, args=()):
        """Conserve les calques distants dans cloud-paquets, par serveur et zone."""
        if route not in ROUTES_GET_ZONE:
            raise ValueError("Route de calque inconnue")
        config = self._config()
        adresse = config.get("serveur_url", "")
        if not adresse:
            raise Indisponible("Aucun serveur configuré.")
        zone = args[0] if args else None
        debut = time.monotonic()
        racine = (self.preferences.parent / "cloud-paquets" / "calques"
                  / hashlib.sha256(adresse.encode()).hexdigest()[:16] / route)
        cache = None
        cache_fichier = None
        cache_octets = 0
        if zone is not None and racine.is_dir():
            for fichier in racine.glob("*.json.gz"):
                try:
                    if fichier.stat().st_size > 16 * 1024 * 1024:
                        continue
                    with gzip.open(fichier, "rb") as entree:
                        brut = entree.read(32 * 1024 * 1024 + 1)
                    if len(brut) > 32 * 1024 * 1024:
                        continue
                    candidat = json.loads(brut)
                    if candidat.get("format") != FORMAT_CALQUES_CACHE:
                        continue
                    bornes = candidat["bornes"]
                    if (not isinstance(candidat.get("fetched_at"), (int, float))
                            or not isinstance(candidat.get("donnees"), dict)):
                        continue
                    if (len(bornes) != 4 or not (bornes[0] <= zone[0] and bornes[1] <= zone[1]
                            and zone[2] <= bornes[2] and zone[3] <= bornes[3])):
                        continue
                    if cache is None or candidat["fetched_at"] > cache["fetched_at"]:
                        cache = candidat
                        cache_fichier = fichier
                        cache_octets = fichier.stat().st_size
                except (OSError, ValueError, KeyError, TypeError, IndexError):
                    continue
        if cache and time.time() - cache["fetched_at"] < CACHE_CALQUES_S:
            journal.info("Calque %s : cache cloud %s lu en %.2f s (%d octets compressés), zone %s",
                         route, cache_fichier, time.monotonic() - debut,
                         cache_octets, zone)
            return {**cache["donnees"], "origine_calque": "cloud"}
        if not self.etat()["actif"]:
            if cache:
                journal.info("Calque %s : cache cloud hors connexion lu en %.2f s (%d octets), zone %s",
                             route, time.monotonic() - debut, cache_octets, zone)
                return {**cache["donnees"], "origine_calque": "cloud"}
            journal.warning("Calque %s : serveur indisponible et cache cloud absent, zone %s",
                            route, zone)
            raise Indisponible("Calque absent du cache et serveur indisponible.")
        try:
            journal.info("Calque %s : téléchargement depuis le serveur cloud, zone %s", route, zone)
            resultat = self.demander(route, "GET", args)
        except Indisponible:
            if cache:
                journal.info("Calque %s : téléchargement échoué, cache cloud utilisé (%d octets), zone %s",
                             route, cache_octets, zone)
                return {**cache["donnees"], "origine_calque": "cloud"}
            raise
        bornes = resultat.get("bornes")
        if not resultat.get("erreur") and isinstance(bornes, (list, tuple)) and len(bornes) == 4:
            racine.mkdir(parents=True, exist_ok=True)
            cle = hashlib.sha256(json.dumps(bornes).encode()).hexdigest()[:20]
            cible = racine / f"{cle}.json.gz"
            provisoire = cible.with_name(cible.name + ".part")
            contenu = {"format": FORMAT_CALQUES_CACHE, "fetched_at": time.time(),
                       "bornes": bornes, "donnees": resultat}
            try:
                with provisoire.open("wb") as sortie:
                    with gzip.GzipFile(fileobj=sortie, mode="wb", mtime=0) as zippe:
                        zippe.write(json.dumps(contenu, ensure_ascii=False,
                                               separators=(",", ":")).encode("utf-8"))
                    sortie.flush()
                    os.fsync(sortie.fileno())
                os.replace(provisoire, cible)
            except OSError as exc:
                raise Indisponible(f"Enregistrement du cache cloud impossible : {exc}") from exc
            finally:
                provisoire.unlink(missing_ok=True)
            try:
                with gzip.open(cible, "rt", encoding="utf-8") as entree:
                    confirme = json.load(entree)
                journal.info("Calque %s : serveur cloud reçu en %.2f s, cache %s (%d octets), zone %s",
                             route, time.monotonic() - debut, cible, cible.stat().st_size, zone)
                return {**confirme["donnees"], "origine_calque": "cloud"}
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise Indisponible(f"Lecture du cache cloud impossible : {exc}") from exc
        journal.warning("Calque %s : réponse du serveur cloud sans données publiables, zone %s : %s",
                        route, zone, resultat.get("erreur", "bornes absentes"))
        return {**resultat, "origine_calque": "cloud"}

    def paquet(self, payload: dict, dossier: Path, zone) -> tuple[dict, Path]:
        """Télécharge un paquet vérifié une seule fois par zone et source.

        Un paquet déjà présent permet ensuite le même calcul hors connexion.
        """
        from . import franchissements

        cle = hashlib.sha256(json.dumps([zone, payload.get("source"), payload.get("officiel"),
                                         payload.get("strict")], sort_keys=True).encode()).hexdigest()[:24]
        racine = Path(dossier) / "cloud-paquets"
        cible = racine / cle
        cache = atomique.lire_json(cible / "manifest.json", None)
        present = (isinstance(cache, dict) and cache.get("format") in (1, 2)
                   and cache.get("pret") is True
                   and all(cache.get(k) == v for k, v in
                           {"strict": bool(payload.get("strict", True)),
                            "source": payload.get("source", "ign") if payload.get("officiel", True) else "osm"}.items())
                   and all((cible / f["nom"]).is_file()
                           for f in cache.get("segments", []) + cache.get("assets", []))
                   and (cache.get("format") != 2
                        or (isinstance(cache.get("assemblage"), dict)
                            and (cible / cache["assemblage"].get("rd5", "")).is_file())))
        actif = self.etat()["actif"]
        if present and not actif:
            journal.info("Paquet d'itinéraire : cache cloud hors connexion, %d octets, zone %s",
                         sum(f["octets"] for f in cache["segments"] + cache["assets"]), zone)
            return cache, cible
        if not actif:
            raise Indisponible("Paquet de cette zone absent hors connexion.")
        paquet = self.demander("paquet-zone", "GET", args=(zone, payload.get("source", "ign"),
                                                         payload.get("officiel", True),
                                                         payload.get("strict", True)))
        if not paquet.get("pret"):
            if present:
                journal.info("Paquet d'itinéraire : aucun paquet serveur plus récent, cache cloud conservé, zone %s", zone)
                return cache, cible
            raise Indisponible(paquet.get("erreur") or "Paquet de zone en préparation.")
        if paquet.get("format") not in (1, 2):
            raise Indisponible("Format de paquet inconnu.")
        if (present and cache.get("format") == paquet["format"]
                and cache.get("segments") == paquet.get("segments")
                and cache.get("assets") == paquet.get("assets")
                and cache.get("assemblage") == paquet.get("assemblage")):
            journal.info("Paquet d'itinéraire : cache cloud à jour, format %s, %d octets, zone %s",
                         paquet["format"], sum(f["octets"] for f in cache["segments"] + cache["assets"]), zone)
            return cache, cible
        journal.info("Paquet d'itinéraire : téléchargement cloud, format %s, %d segments, %d assets, zone %s",
                     paquet["format"], len(paquet["segments"]), len(paquet["assets"]), zone)
        config = self._config()
        racine.mkdir(parents=True, exist_ok=True)
        provisoire = racine / f"{cle}-{secrets.token_hex(6)}"
        provisoire.mkdir()
        debut_paquet = time.monotonic()
        try:
            for fichier in paquet["segments"] + paquet["assets"]:
                nom, url = fichier["nom"], fichier["url"]
                if (not url.startswith("/api/paquets/") or ".." in url
                        or "/" in nom or "\\" in nom):
                    raise Indisponible("Fichier du paquet invalide.")
                empreinte = hashlib.sha256()
                demande = urllib.request.Request(config["serveur_url"] + url)
                debut_fichier = time.monotonic()
                with urllib.request.urlopen(demande, timeout=120) as reponse, \
                        (provisoire / nom).open("wb") as sortie:
                    while bloc := reponse.read(1024 * 1024):
                        sortie.write(bloc)
                        empreinte.update(bloc)
                if ((provisoire / nom).stat().st_size != fichier["octets"]
                        or empreinte.hexdigest() != fichier["sha256"]):
                    raise Indisponible(f"Empreinte inattendue pour {nom}.")
                journal.info("Paquet d'itinéraire : %s reçu et vérifié, %d octets en %.2f s",
                             nom, fichier["octets"], time.monotonic() - debut_fichier)
            if paquet["format"] == 2:
                try:
                    assemblage = paquet["assemblage"]
                    rd5_fragments.assembler(assemblage, provisoire,
                                           provisoire / assemblage["rd5"])
                    journal.info("Paquet d'itinéraire : RD5 assemblée localement %s (%d octets)",
                                 assemblage["rd5"], (provisoire / assemblage["rd5"]).stat().st_size)
                except (KeyError, OSError, ValueError, TypeError) as exc:
                    raise Indisponible(f"Assemblage RD5 invalide : {exc}") from exc
            paquet["telecharge_a"] = time.time()
            atomique.ecrire_json(provisoire / "manifest.json", paquet)
            ancien = racine / f"{cle}-ancien"
            if ancien.exists():
                shutil.rmtree(ancien)
            if cible.exists():
                os.replace(cible, ancien)
            os.replace(provisoire, cible)
            if ancien.exists():
                shutil.rmtree(ancien)
            journal.info("Paquet d'itinéraire : %d fichiers, %d octets en %.2f s, zone %s",
                         len(paquet["segments"] + paquet["assets"]),
                         sum(f["octets"] for f in paquet["segments"] + paquet["assets"]),
                         time.monotonic() - debut_paquet, zone)
            return paquet, cible
        finally:
            if provisoire.exists():
                shutil.rmtree(provisoire)
