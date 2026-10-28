"""Serveur de la page de tracé, sur la boucle locale, par serveweb du commun,
avec l'icône de la zone de notification et la recherche de nouvelle version
des autres applications de nico579."""
from __future__ import annotations

import logging
import sqlite3
import subprocess
import threading
import webbrowser
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

from nico579_commons import maj, serveweb

from . import __version__, bureau, fonds, geofabrik, osmfr, providers
from .application import Application, configurer_journal, lire_vue, lire_zone

journal = logging.getLogger(__name__)

HOST = "127.0.0.1"
PORT = 8795
PLAGE = 10
GUI = Path(__file__).parent / "assets" / "web"
PROVIDERS = GUI / "providers"
RAPPORT_GITHUB = "https://github.com/nico579/hike2gpx/blob/{ref}/{document}"


def url_couverture_pays(langue: str = "fr") -> str:
    """Pointe vers la branche de travail en source, vers main en version publiée."""
    ref = "main"
    racine = Path(__file__).resolve().parent.parent
    if (racine / ".git").exists():
        try:
            resultat = subprocess.run(["git", "branch", "--show-current"], cwd=racine,
                                      capture_output=True, text=True, timeout=2, check=False)
            if resultat.returncode == 0 and resultat.stdout.strip():
                ref = resultat.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    document = ("COUNTRY_COVERAGE.md#supported-countries" if langue == "en"
                else "RAPPORT_SOURCES_CHEMINS_BROUTER.md#pays-pris-en-charge")
    return RAPPORT_GITHUB.format(ref=quote(ref, safe="/"), document=document)


class Handler(serveweb.Handler):
    fichiers_statiques = {**serveweb.FICHIERS_STATIQUES,
                          "/presentation.js": ("presentation.js", "text/javascript; charset=utf-8"),
                          "/presentation.css": ("presentation.css", "text/css; charset=utf-8"),
                          "/leaflet/leaflet.js": ("leaflet/leaflet.js", "text/javascript; charset=utf-8"),
                           "/leaflet/leaflet.css": ("leaflet/leaflet.css", "text/css; charset=utf-8"),
                           "/leaflet/Leaflet.VectorGrid.bundled.js":
                           ("leaflet/Leaflet.VectorGrid.bundled.js", "text/javascript; charset=utf-8")}
    # Les calques et l'extrait hors ligne lisent la zone de la vue :
    # ?s=&w=&n=&e= (None si invalide) ; les calques aussi sa date, &vue=.
    arguments_get = {"osm": lambda q: (lire_zone(q), lire_vue(q)),
                     **{p.calque: (lambda q: (lire_zone(q), lire_vue(q))) for p in providers.SOURCES.values()},
                     "extrait": lambda q: (lire_zone(q),), "disponibilite": lambda q: (lire_zone(q),)}

    def do_GET(self):
        chemin = self.path.split("?", 1)[0]
        if chemin == "/documentation/pays":
            if not self.hote_autorise() or self.requete_inter_sites():
                self.send_error(403)
                return
            self.send_response(302)
            langue = parse_qs(urlsplit(self.path).query).get("lang", ["fr"])[0]
            self.send_header("Location", url_couverture_pays(langue))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if chemin == "/map-providers.js":
            if not self.hote_autorise() or self.requete_inter_sites():
                self.send_error(403)
                return
            # Les providers sont des modules autonomes. Leur dossier est la
            # source unique du registre et de la liste de couverture de la page.
            morceaux = ["window.HIKE2GPX_MAP_PROVIDERS = {};\n"]
            morceaux.extend(p.read_text(encoding="utf-8") + "\n" for p in sorted(PROVIDERS.glob("[a-z][a-z].js")))
            morceaux.append('window.HIKE2GPX_MAP_PROVIDERS.autre = '
                            '{ defaultBase: "osm", overlays: [], bases: () => ({}) };\n')
            corps = "".join(morceaux).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/javascript; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)
            return
        if chemin.startswith("/fonds/"):
            if not self.hote_autorise() or self.requete_inter_sites():
                self.send_error(403)
                return
            self.envoyer_tuile(chemin)
            return
        if self.path.split("?", 1)[0] == "/journal.txt":
            if not self.hote_autorise() or self.requete_inter_sites():
                self.send_error(403)
                return
            self.send_static(self.journal_path, "text/plain; charset=utf-8", cache="no-store")
            return
        super().do_GET()

    hors_ligne = None       # posé par demarrer : les fonds de carte installés

    def envoyer_tuile(self, chemin: str) -> None:
        """/fonds/<nom>/<z>/<x>/<y> : une tuile d'un fond de carte installé
        (fonds.py), que la page affiche sans réseau. 404 hors du fond."""
        morceaux = chemin.split("/")[2:]
        if len(morceaux) != 4 or not all(m.isascii() and m.isdigit() for m in morceaux[1:]) or self.hors_ligne is None:
            self.send_error(404)
            return
        fichier = self.hors_ligne.chemin_fond(morceaux[0])
        z, x, y = (int(m) for m in morceaux[1:])
        try:
            tuile = fonds.lire_tuile(fichier, z, x, y) if fichier and z <= 24 else None
        except sqlite3.Error:
            tuile = None
        if tuile is None:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/png" if tuile[:4] == b"\x89PNG" else "image/jpeg")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(tuile)))
        self.end_headers()
        self.wfile.write(tuile)


def demarrer(application: Application, port: int = PORT, plage: int = PLAGE, installateur=None):
    """installateur : celui de bureau.installateur(), dont les routes du
    commun (/api/maj, /api/maj-installer, /api/maj-verifier) font vivre le
    bandeau de mise à jour de la page."""
    get, post = application.routes()
    if installateur is not None:
        from nico579_commons import maj_install
        get_maj, post_maj = maj_install.routes(installateur, lambda: application.lire_langue() or "fr")
        get, post = {**get, **get_maj}, {**post, **post_maj}
    handler = type("Hike2gpxHandler", (Handler,), {})   # chaque serveur garde ses routes
    handler.journal_path = configurer_journal(application.dossier)
    handler.hors_ligne = application.hors_ligne
    serveur, port = serveweb.premier_port_libre(HOST, port, plage, trusted_host="", gui_dir=GUI,
                                                api_routes=get, post_routes=post, handler=handler,
                                                favicon=bureau.ICONE)
    if serveur is None:
        raise OSError("Aucun port disponible pour la page de hike2gpx.")
    return serveur, port


def instance_en_place(port: int = PORT, plage: int = PLAGE):
    """Port d'un hike2gpx qui répond déjà dans la plage (sa route /api/init
    l'annonce), ou None."""
    return next((p for p in range(port, port + plage)
                 if serveweb.instance_existante("hike2gpx", HOST, p, timeout=0.5)), None)


def servir(dossier: Path, port: int = PORT, ouvrir: bool = True, icone: bool = True) -> None:
    # Une seule instance : relancé, hike2gpx rouvre la page du serveur déjà là.
    existant = instance_en_place(port)
    if existant is not None:
        url = f"http://{HOST}:{existant}/"
        print(f"hike2gpx tourne déjà : {url}", flush=True)
        if ouvrir:
            webbrowser.open(url)
        return
    chemin_journal = configurer_journal(dossier)
    application = Application(dossier)
    arret, verrou, fini = threading.Event(), threading.Lock(), []
    verificateur = maj.Verificateur(bureau.DEPOT, __version__, cache=Path(dossier) / "maj.json")
    # La nouvelle version prête, l'assistant du commun attend notre fin :
    # lever arret referme l'icône, puis finally arrête serveur et BRouter.
    installateur = bureau.installateur(verificateur, quitter=arret.set)
    # Restes d'une mise à jour interrompue (assistant tué, coupure), à côté de
    # l'installation : effacés en tâche de fond, sans retarder le démarrage.
    threading.Thread(target=installateur.nettoyer_restes, name="menage-maj", daemon=True).start()
    serveur, port = demarrer(application, port, installateur=installateur)
    url = f"http://{HOST}:{port}/"
    print(f"hike2gpx {__version__} : {url} (données : {dossier}, journal : {chemin_journal})", flush=True)
    journal.info("hike2gpx %s démarré : %s, données %s", __version__, url, dossier)
    # Les index des extraits, prêts avant le premier usage : les départements
    # d'OSM France, les régions de Geofabrik. Chacun ne se refait, en tâche de
    # fond, que s'il manque ou a plus d'un mois.
    osmfr.regions(dossier)
    geofabrik.regions(dossier)
    # Bundle publié, premier lancement : l'icône sur le Bureau, une fois.
    bureau.raccourci_au_premier_lancement(application.lire_langue, Path(dossier))

    def arreter():
        """Arrête le serveur et BRouter, une seule fois, depuis l'icône (sur
        un fil à part) ou à la fin de servir."""
        with verrou:
            if fini:
                return
            fini.append(True)
        serveur.shutdown()
        serveur.server_close()
        application.arreter()
        arret.set()
        journal.info("hike2gpx arrêté")

    verificateur.veiller(arret)
    if ouvrir:
        webbrowser.open(url)
    zone = bureau.icone_de_notification(url, arreter, verificateur, application.lire_langue, Path(dossier), arret,
                                        installateur) if icone else None
    try:
        if zone is not None:
            zone.executer()     # rend la main quand Arrêter ou Redémarrer referment l'icône
        else:
            while not arret.wait(1):
                pass
    except KeyboardInterrupt:
        pass
    finally:
        arreter()
