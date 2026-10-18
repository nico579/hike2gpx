"""Serveur de la page de tracé, sur la boucle locale, par serveweb du commun."""
from __future__ import annotations

import time
import webbrowser
from pathlib import Path

from nico579_commons import serveweb

from . import __version__
from .application import Application

HOST = "127.0.0.1"
PORT = 8795
PLAGE = 10
GUI = Path(__file__).parent / "assets" / "web"


class Handler(serveweb.Handler):
    fichiers_statiques = {**serveweb.FICHIERS_STATIQUES,
                          "/leaflet/leaflet.js": ("leaflet/leaflet.js", "text/javascript; charset=utf-8"),
                          "/leaflet/leaflet.css": ("leaflet/leaflet.css", "text/css; charset=utf-8")}


def demarrer(application: Application, port: int = PORT, plage: int = PLAGE):
    get, post = application.routes()
    handler = type("Hike2gpxHandler", (Handler,), {})   # chaque serveur garde ses routes
    serveur, port = serveweb.premier_port_libre(HOST, port, plage, trusted_host="", gui_dir=GUI,
                                                api_routes=get, post_routes=post, handler=handler)
    if serveur is None:
        raise OSError("Aucun port disponible pour la page de hike2gpx.")
    return serveur, port


def servir(dossier: Path, port: int = PORT, ouvrir: bool = True) -> None:
    application = Application(dossier)
    serveur, port = demarrer(application, port)
    url = f"http://{HOST}:{port}/"
    print(f"hike2gpx {__version__} : {url} (données : {dossier})", flush=True)
    if ouvrir:
        webbrowser.open(url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        serveur.shutdown()
        serveur.server_close()
        application.arreter()
