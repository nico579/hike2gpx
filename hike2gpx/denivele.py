"""Dénivelé d'un itinéraire, calculé par le moteur de gpx2elev.

Le chiffre de BRouter vient des altitudes rangées dans ses tuiles, un modèle
de terrain mondial et grossier. gpx2elev échantillonne le tracé tous les
5 m, lit le meilleur modèle qui le couvre entièrement (IGN LiDAR HD d'abord,
puis Mapterhorn, FABDEM, Copernicus GLO-30, SRTM), lisse par une gaussienne
de 20 m et compte avec une hystérésis de 2 m : c'est son protocole publié.
Ses profils et ses tuiles d'altitude vont dans <dossier>/gpx2elev.
"""
from __future__ import annotations

import math
from pathlib import Path

from gpx2elev import core
from gpx2elev.providers import MissingCoverage, Repository

POINTS_MAX = 200_000


class ErreurDenivele(RuntimeError):
    """Aucun modèle de terrain n'a fourni le profil complet du tracé."""


def valider(coordonnees) -> list:
    """Points [lon, lat(, alt)] d'un tracé GeoJSON de BRouter."""
    if not isinstance(coordonnees, list) or not 2 <= len(coordonnees) <= POINTS_MAX:
        raise ValueError("Tracé invalide.")
    points = []
    for c in coordonnees:
        if not (isinstance(c, list) and 2 <= len(c) <= 3
                and all(isinstance(v, (int, float)) and math.isfinite(v) for v in c)
                and -180 <= c[0] <= 180 and -85 <= c[1] <= 85):
            raise ValueError("Point de tracé invalide.")
        points.append(c)
    return points


def gpx(coordonnees) -> bytes:
    """GPX 1.1 minimal du tracé, pour core.parse_gpx. L'altitude de BRouter,
    quand elle est là, suit : gpx2elev la garde pour sa comparaison."""
    points = "".join(
        f'<trkpt lat="{c[1]:.7f}" lon="{c[0]:.7f}">'
        + (f"<ele>{float(c[2]):.2f}</ele>" if len(c) > 2 else "") + "</trkpt>"
        for c in coordonnees)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<gpx version="1.1" creator="hike2gpx" xmlns="http://www.topografix.com/GPX/1/1">'
            f"<trk><trkseg>{points}</trkseg></trk></gpx>").encode("utf-8")


def calculer(coordonnees, dossier, *, en_ligne: bool = True, lecteur=None) -> dict:
    """Montée, descente et altitudes extrêmes du tracé selon gpx2elev.
    `lecteur` remplace la lecture des modèles de terrain (essais)."""
    preparee = core.prepare(core.parse_gpx(gpx(valider(coordonnees))))
    depot = Repository(Path(dossier) / "gpx2elev", reader=lecteur)
    try:
        serie = depot.obtain(preparee.coordinates, online=en_ligne)
        calcul = core.compute(preparee, serie.values)
    except MissingCoverage as exc:
        raise ErreurDenivele(str(exc).splitlines()[0] or "Aucun modèle de terrain disponible.") from exc
    finally:
        depot.close()
    return {"montee_m": round(calcul.gain.up), "descente_m": round(calcul.gain.down),
            "altitude_min_m": round(calcul.minimum), "altitude_max_m": round(calcul.maximum),
            "modele": serie.source.label, "protocole": core.PROTOCOL, "depuis_le_cache": serie.from_cache}
