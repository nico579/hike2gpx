"""Auto-test du programme figé (--self-test-version VERSION). La CI le lance
après chaque construction, et l'installateur de mise à jour du commun avant
de mettre une nouvelle version en place : moins de 30 s, sans réseau ni
données. Il éprouve ce que PyInstaller peut perdre en route sans que rien ne
casse au démarrage : un fichier de la page, l'icône, les scripts du commun,
le Java embarqué, les bibliothèques compilées (pyosmium, NumPy, rasterio et
la base de projections de PROJ). Chaque cause d'échec a son code de sortie et
sa ligne sur la sortie standard, que lit la CI."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from nico579_commons import serveweb

from . import __version__, brouter, bureau, web

PAGE = ("index.html", "app.js", "style.css", "leaflet/leaflet.js", "leaflet/leaflet.css")


def _echec(code: int, message: str) -> int:
    print(f"auto-test : {message}", flush=True)
    return code


def verifier(version_attendue: str) -> int:
    if version_attendue != __version__:
        return _echec(3, f"version {__version__}, attendue {version_attendue}")
    fichiers = [bureau.ICONE, bureau.ICONE.with_suffix(".png"), *(web.GUI / nom for nom in PAGE)]
    manquants = [str(f) for f in fichiers if not f.is_file()] + serveweb.fichiers_manquants()
    if manquants:
        return _echec(4, "fichiers absents : " + ", ".join(manquants))
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    try:
        java = subprocess.run([brouter.java(), "-version"], capture_output=True, text=True, errors="replace",
                              stdin=subprocess.DEVNULL, timeout=20, **options)
    except (brouter.ErreurBRouter, OSError, subprocess.TimeoutExpired) as exc:
        return _echec(5, f"Java inutilisable : {exc}")
    if java.returncode:
        return _echec(5, f"Java inutilisable : {java.stderr.strip()[-300:]}")
    try:
        bibliotheques()
    except Exception as exc:        # toute panne d'une bibliothèque compilée compte
        return _echec(6, f"bibliothèque inutilisable : {type(exc).__name__}: {exc}")
    print(f"auto-test : hike2gpx {__version__}, {java.stderr.strip().splitlines()[0]}", flush=True)
    return 0


def bibliotheques() -> None:
    """Chaque bibliothèque compilée par le chemin qu'emprunte hike2gpx, pas
    seulement son import : un PBF écrit comme pour les tuiles maison, la
    couverture des chemins IGN, une conversion en Lambert 93 qui lit proj.db."""
    from gpx2elev.providers import Repository  # noqa: F401  (charge rasterio et GDAL)
    from rasterio.warp import transform

    from . import fusion

    reseau = fusion.Reseau()
    reseau.ajouter_osm([{"type": "way", "id": 1, "nodes": [1, 2], "tags": {"highway": "path"},
                         "geometry": [{"lat": 43.33, "lon": 6.05}, {"lat": 43.331, "lon": 6.051}]}])
    with tempfile.TemporaryDirectory() as dossier:
        pbf = Path(dossier) / "essai.osm.pbf"
        reseau.ecrire_pbf(pbf)
        if pbf.stat().st_size == 0:
            raise OSError("PBF vide")
    part = fusion.parts_couvertes([[[43.33, 6.05], [43.331, 6.051]]], reseau.segments_osm())
    if part.tolist() != [1.0]:
        raise ValueError(f"couverture {part.tolist()}, attendue [1.0]")
    x, y = transform("EPSG:4326", "EPSG:2154", [6.05], [43.33])
    if not (900_000 < x[0] < 1_000_000 and 6_200_000 < y[0] < 6_300_000):
        raise ValueError(f"Lambert 93 inattendu : {x[0]:.0f}, {y[0]:.0f}")
