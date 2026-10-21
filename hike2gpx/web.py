"""Serveur de la page de tracé, sur la boucle locale, par serveweb du commun,
avec l'icône de la zone de notification et la recherche de nouvelle version
des autres applications de nico579."""
from __future__ import annotations

import logging
import threading
import webbrowser
from pathlib import Path

from nico579_commons import maj, serveweb

from . import __version__, bureau, geofabrik, osmfr
from .application import Application, configurer_journal, lire_vue, lire_zone

journal = logging.getLogger(__name__)

HOST = "127.0.0.1"
PORT = 8795
PLAGE = 10
GUI = Path(__file__).parent / "assets" / "web"


class Handler(serveweb.Handler):
    fichiers_statiques = {**serveweb.FICHIERS_STATIQUES,
                          "/presentation.js": ("presentation.js", "text/javascript; charset=utf-8"),
                          "/presentation.css": ("presentation.css", "text/css; charset=utf-8"),
                          "/leaflet/leaflet.js": ("leaflet/leaflet.js", "text/javascript; charset=utf-8"),
                          "/leaflet/leaflet.css": ("leaflet/leaflet.css", "text/css; charset=utf-8")}
    # Les calques et l'extrait hors ligne lisent la zone de la vue :
    # ?s=&w=&n=&e= (None si invalide) ; les calques aussi sa date, &vue=.
    arguments_get = {"osm": lambda q: (lire_zone(q), lire_vue(q)), "bdtopo": lambda q: (lire_zone(q), lire_vue(q)),
                     "extrait": lambda q: (lire_zone(q),), "disponibilite": lambda q: (lire_zone(q),)}

    def do_GET(self):
        if self.path.split("?", 1)[0] == "/journal.txt":
            if not self.hote_autorise() or self.requete_inter_sites():
                self.send_error(403)
                return
            self.send_static(self.journal_path, "text/plain; charset=utf-8", cache="no-store")
            return
        super().do_GET()


def demarrer(application: Application, port: int = PORT, plage: int = PLAGE):
    get, post = application.routes()
    handler = type("Hike2gpxHandler", (Handler,), {})   # chaque serveur garde ses routes
    handler.journal_path = configurer_journal(application.dossier)
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
    serveur, port = demarrer(application, port)
    url = f"http://{HOST}:{port}/"
    print(f"hike2gpx {__version__} : {url} (données : {dossier}, journal : {chemin_journal})", flush=True)
    journal.info("hike2gpx %s démarré : %s, données %s", __version__, url, dossier)
    # Les index des extraits, prêts avant le premier usage : les départements
    # d'OSM France, les régions de Geofabrik. Chacun ne se refait, en tâche de
    # fond, que s'il manque ou a plus d'un mois.
    osmfr.regions(dossier)
    geofabrik.regions(dossier)

    arret, verrou, fini = threading.Event(), threading.Lock(), []

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

    verificateur = maj.Verificateur(bureau.DEPOT, __version__, cache=Path(dossier) / "maj.json")
    verificateur.veiller(arret)
    if ouvrir:
        webbrowser.open(url)
    zone = bureau.icone_de_notification(url, arreter, verificateur, application.lire_langue, Path(dossier), arret) \
        if icone else None
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
