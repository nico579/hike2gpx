"""Partage au téléphone : le PC sert ses lots et ses fonds de carte sur le Wi-Fi.

Le téléphone prend les lots publiés sur GitHub ; mais ce que seul le PC
possède, les lots OSM qu'il a préparés hors des pays routables et les fonds
de carte (le SCAN 25, fabriqué avec la clé IGN de l'utilisateur pour son seul
usage), il le reçoit de son PC. Le PC sert alors un catalogue au format du
dépôt (depot.py), adresses relatives, et un QR code qui en donne l'adresse et
le jeton. Le contrat, que l'application Android suit, est écrit dans
docs/architecture/partage-telephone.md :

  hike2gpx://depot?url=http%3A%2F%2F192.168.1.20%3A8799%2Fdepot%2Fcatalog.json&jeton=…
  GET /depot/catalog.json, puis GET /depot/<url> (Range), toutes avec
  Authorization: Bearer <jeton> ; sans jeton valide, 401.

Sécurité : le partage est fermé par défaut et ne s'ouvre qu'à la demande ; le
jeton (32 octets de secrets) change à chaque ouverture ; le serveur n'écoute
que sur l'adresse privée du PC (jamais 0.0.0.0) et ne répond qu'aux adresses
privées ; il ne sert que les fichiers du catalogue, par une table nom ->
chemin dressée à l'ouverture : aucune adresse reçue ne devient un chemin.
"""
from __future__ import annotations

import io
import ipaddress
import json
import logging
import re
import secrets
import socket
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import segno

from . import depot, lot

journal = logging.getLogger(__name__)
PORT = 8799
PLAGE = 10
PREFIXE = "/depot/"
BLOC = 1 << 16
_PLAGE_OCTETS = re.compile(r"^bytes=(\d*)-(\d*)$")


class ErreurPartage(RuntimeError):
    pass


def ip_locale() -> str:
    """L'adresse du PC sur son réseau local : celle de l'interface par laquelle
    il joindrait Internet (un connect UDP n'envoie aucun paquet). Refusée si
    elle n'est pas privée : on ne partage pas sur un réseau public."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("192.0.2.1", 9))        # adresse de documentation, jamais jointe
            adresse = s.getsockname()[0]
        except OSError as exc:
            raise ErreurPartage("Pas de réseau local : le PC n'est connecté à aucun réseau.") from exc
    ip = ipaddress.ip_address(adresse)
    if not ip.is_private or ip.is_loopback or ip.is_link_local:
        raise ErreurPartage(f"L'adresse {adresse} n'est pas celle d'un réseau local privé.")
    return adresse


def dresser(hors_ligne, empreintes: dict | None = None) -> tuple:
    """(catalogue, fichiers) des lots installés et des fonds : le catalogue au
    format du dépôt, les adresses en sous-dossiers (E5_N40/E5_N40.rd5,
    fonds/E5_N40-scan25.mbtiles), et la table adresse -> chemin, la seule que
    le serveur consulte. empreintes : un cache {(chemin, taille, date): sha256},
    pour ne pas relire un fond de plusieurs centaines de Mo à chaque ouverture."""
    empreintes = {} if empreintes is None else empreintes
    fichiers, lots = {}, []
    for m in hors_ligne.lots():
        case = m["case"]
        dossier = hors_ligne.racine / case
        segments = hors_ligne.segments_osm if m.get("type") == "osm" else hors_ligne.segments
        entree = depot.entree_lot(m, dossier / "manifest.json", lambda nom, case=case: f"{case}/{nom}")
        for f in entree["fichiers"]:
            # La RD5 d'un lot installé est rangée avec les segments ; le reste, dans le dossier de la case.
            fichiers[f["url"]] = segments / f["nom"] if f["nom"] == f"{case}.rd5" else dossier / f["nom"]
        lots.append(entree)
    fonds = []
    for f in hors_ligne.fonds():
        chemin = hors_ligne.dossier_fonds / f"{f['nom']}.mbtiles"
        etat = chemin.stat()
        cle = (str(chemin), etat.st_size, etat.st_mtime_ns)
        if cle not in empreintes:
            empreintes[cle] = lot.empreinte(chemin)
        url = f"fonds/{f['nom']}.mbtiles"
        fonds.append({"nom": f["nom"], "zone": f["zone"], "zoom": f["zoom"], "source": f["source"],
                      "octets": etat.st_size, "sha256": empreintes[cle], "url": url})
        fichiers[url] = chemin
    return depot.catalogue(lots, fonds), fichiers


def lien(url_catalogue: str, jeton: str) -> str:
    """Le texte du QR code : hike2gpx://depot?url=…&jeton=…"""
    return "hike2gpx://depot?" + urllib.parse.urlencode({"url": url_catalogue, "jeton": jeton})


def qr_svg(texte: str) -> str:
    """Le QR code en SVG, prêt à poser dans la page."""
    tampon = io.BytesIO()
    segno.make(texte, error="m").save(tampon, kind="svg", scale=4, border=4, xmldecl=False, svgns=True)
    return tampon.getvalue().decode("utf-8")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    partage = None                  # posé par Partage.ouvrir, sur une sous-classe

    def log_message(self, fmt, *args):
        pass

    def _refuser(self, code: int) -> None:
        corps = json.dumps({"erreur": {401: "jeton manquant ou invalide", 403: "hors du réseau local",
                                       404: "introuvable", 405: "méthode refusée",
                                       416: "plage invalide"}.get(code, "erreur")}).encode()
        self.send_response(code)
        if code == 401:
            self.send_header("WWW-Authenticate", 'Bearer realm="hike2gpx"')
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corps)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corps)

    def _autorise(self) -> int:
        """0 si la requête vient du réseau local avec le bon jeton, sinon le code d'erreur."""
        try:
            client = ipaddress.ip_address(self.client_address[0])
        except ValueError:
            return 403
        if not (client.is_private or client.is_loopback):
            return 403
        entete = self.headers.get("Authorization") or ""
        jeton = entete[7:].strip() if entete[:7].lower() == "bearer " else ""
        if not jeton or not secrets.compare_digest(jeton.encode(), self.partage.jeton.encode()):
            return 401
        return 0

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        code = self._autorise()
        if code:
            self._refuser(code)
            return
        chemin = urllib.parse.urlsplit(self.path).path
        if not chemin.startswith(PREFIXE):
            self._refuser(404)
            return
        adresse = urllib.parse.unquote(chemin[len(PREFIXE):])
        if adresse == "catalog.json":
            corps = self.partage.catalogue_json
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(corps)
            return
        fichier = self.partage.fichiers.get(adresse)       # la table, jamais le chemin reçu
        if fichier is None or not fichier.is_file():
            self._refuser(404)
            return
        self._envoyer_fichier(fichier)

    def _envoyer_fichier(self, fichier: Path) -> None:
        """Le fichier, ou la plage demandée (Range: bytes=debut-[fin]) pour une reprise."""
        taille = fichier.stat().st_size
        debut, fin = 0, taille - 1
        # Une seule plage d'octets ; toute autre forme (plusieurs plages) est
        # ignorée, comme le permet HTTP : le fichier entier part alors en 200.
        trouve = _PLAGE_OCTETS.match((self.headers.get("Range") or "").strip())
        plage = trouve is not None and trouve.groups() != ("", "")
        if plage:
            a, b = trouve.groups()
            if a:
                debut, fin = int(a), min(int(b), taille - 1) if b else taille - 1
            else:                                   # bytes=-n : les n derniers octets
                debut = max(taille - int(b), 0)
            if debut >= taille or debut > fin:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{taille}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        longueur = fin - debut + 1
        self.send_response(206 if plage else 200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        if plage:
            self.send_header("Content-Range", f"bytes {debut}-{fin}/{taille}")
        self.send_header("Content-Length", str(longueur))
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(fichier, "rb") as f:
            f.seek(debut)
            while longueur > 0:
                bloc = f.read(min(BLOC, longueur))
                if not bloc:
                    break
                self.wfile.write(bloc)
                longueur -= len(bloc)

    def do_POST(self):
        self._refuser(405)

    do_PUT = do_DELETE = do_PATCH = do_POST


class Serveur(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        pass                            # un téléphone qui coupe un téléchargement n'est pas une panne


class Partage:
    """Le partage du PC : fermé par défaut ; ouvrir() dresse le catalogue,
    tire un jeton neuf et écoute sur l'adresse locale ; fermer() arrête tout."""

    def __init__(self, hors_ligne, port: int = PORT, plage: int = PLAGE, adresse=ip_locale):
        self.hors_ligne = hors_ligne
        self.port_demande, self.plage, self.adresse = port, plage, adresse
        self.verrou = threading.Lock()
        self.serveur = None
        self.jeton = ""
        self.catalogue_json = b""
        self.fichiers: dict = {}
        self.url = ""
        self._empreintes: dict = {}

    def etat(self) -> dict:
        """Ce que montre la page : fermé, ou ouvert avec l'adresse, le lien du QR
        code et son dessin, et ce qui est partagé."""
        if self.serveur is None:
            return {"ouvert": False}
        catalogue = json.loads(self.catalogue_json)
        lien_qr = lien(self.url, self.jeton)
        return {"ouvert": True, "url": self.url, "lien": lien_qr, "qr": qr_svg(lien_qr),
                "lots": [l["case"] for l in catalogue["lots"]], "fonds": [f["nom"] for f in catalogue["fonds"]],
                "octets": sum(l["octets"] for l in catalogue["lots"]) + sum(f["octets"] for f in catalogue["fonds"])}

    def ouvrir(self) -> dict:
        with self.verrou:
            self._fermer()
            ip = self.adresse()
            catalogue, self.fichiers = dresser(self.hors_ligne, self._empreintes)
            self.catalogue_json = json.dumps(catalogue, ensure_ascii=False).encode("utf-8")
            self.jeton = secrets.token_urlsafe(32)        # 32 octets aléatoires, renouvelés à chaque ouverture
            handler = type("HandlerPartage", (Handler,), {"partage": self})
            for port in range(self.port_demande, self.port_demande + self.plage):
                try:
                    self.serveur = Serveur((ip, port), handler)
                    break
                except OSError:
                    continue
            else:
                raise ErreurPartage("Aucun port libre pour le partage.")
            self.url = f"http://{ip}:{self.serveur.server_address[1]}{PREFIXE}catalog.json"
            threading.Thread(target=self.serveur.serve_forever, name="partage", daemon=True).start()
            journal.info("Partage ouvert : %s (%d lots, %d fonds)", self.url, len(catalogue["lots"]),
                         len(catalogue["fonds"]))
        return self.etat()

    def _fermer(self) -> None:
        if self.serveur is not None:
            self.serveur.shutdown()
            self.serveur.server_close()
            self.serveur = None
            journal.info("Partage fermé")
        self.jeton, self.fichiers, self.catalogue_json, self.url = "", {}, b"", ""

    def fermer(self) -> dict:
        with self.verrou:
            self._fermer()
        return self.etat()
