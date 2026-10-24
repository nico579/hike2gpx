"""Client du serveur personnel : API distante, repli local si inaccessible."""
from __future__ import annotations

import json
import hashlib
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
from . import providers


ROUTES_GET_ZONE = {"osm"} | {p.calque for p in providers.SOURCES.values()}
ROUTES_CLOUD = ROUTES_GET_ZONE


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
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or url.path or url.query or url.fragment or port == 0):
        raise ValueError("Indiquez une adresse HTTPS, sans chemin ni identifiants.")
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
        elif route in ROUTES_GET_ZONE:
            zone = args[0] if args else None
            if zone is not None:
                q = dict(zip(("s", "w", "n", "e"), zone))
                if len(args) > 1 and args[1] is not None:
                    q["vue"] = args[1]
                url += "?" + urllib.parse.urlencode(q)
        return url

    @staticmethod
    def _requete(config, route, methode="GET", args=(), payload=None):
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
                return json.loads(corps)
        except (OSError, ValueError) as exc:
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
        present = (isinstance(cache, dict) and cache.get("format") == 1
                   and cache.get("pret") is True
                   and all(cache.get(k) == v for k, v in
                           {"strict": bool(payload.get("strict", True)),
                            "source": payload.get("source", "ign") if payload.get("officiel", True) else "osm"}.items())
                   and all((cible / f["nom"]).is_file()
                           for f in cache.get("segments", []) + cache.get("assets", [])))
        if present and (time.time() - cache.get("telecharge_a", 0) < 7 * 86400
                        or not self.etat()["actif"]):
            return cache, cible
        if not self.etat()["actif"]:
            raise Indisponible("Paquet de cette zone absent hors connexion.")
        paquet = self.demander("paquet-zone", "GET", args=(zone, payload.get("source", "ign"),
                                                         payload.get("officiel", True),
                                                         payload.get("strict", True)))
        if not paquet.get("pret"):
            raise Indisponible(paquet.get("erreur") or "Paquet de zone en préparation.")
        config = self._config()
        racine.mkdir(parents=True, exist_ok=True)
        provisoire = racine / f"{cle}-{secrets.token_hex(6)}"
        provisoire.mkdir()
        try:
            for fichier in paquet["segments"] + paquet["assets"]:
                nom, url = fichier["nom"], fichier["url"]
                if (not url.startswith("/api/paquets/") or ".." in url
                        or "/" in nom or "\\" in nom):
                    raise Indisponible("Fichier du paquet invalide.")
                empreinte = hashlib.sha256()
                demande = urllib.request.Request(config["serveur_url"] + url)
                with urllib.request.urlopen(demande, timeout=120) as reponse, \
                        (provisoire / nom).open("wb") as sortie:
                    while bloc := reponse.read(1024 * 1024):
                        sortie.write(bloc)
                        empreinte.update(bloc)
                if ((provisoire / nom).stat().st_size != fichier["octets"]
                        or empreinte.hexdigest() != fichier["sha256"]):
                    raise Indisponible(f"Empreinte inattendue pour {nom}.")
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
            return paquet, cible
        finally:
            if provisoire.exists():
                shutil.rmtree(provisoire)
