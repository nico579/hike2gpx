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
PROFIL_MAX_POINTS = 500
PAS_TOBLER_M = 20.0


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


def duree_tobler(profil, *, hors_sentier: bool = False) -> float:
    """Secondes de marche sur le profil lissé complet, dans le sens du tracé.

    La pente est dh/dx, avec x horizontal en mètres. Une fenêtre de 20 m
    limite l'effet du bruit altimétrique résiduel des échantillons de 5 m.
    Le coefficient hors sentier ne vaut que pour un trajet ainsi identifié ;
    un chemin IGN absent d'OSM reste un chemin.
    """
    points = list(profil)
    if len(points) < 2:
        return 0.0
    reechantillonnes = [points[0]]
    cible = points[0][0] + PAS_TOBLER_M
    precedent = points[0]
    for courant in points[1:]:
        distance, altitude = courant
        if distance <= precedent[0]:
            continue
        while cible <= distance:
            fraction = (cible - precedent[0]) / (distance - precedent[0])
            reechantillonnes.append((cible, precedent[1] + fraction * (altitude - precedent[1])))
            cible += PAS_TOBLER_M
        precedent = courant
    if reechantillonnes[-1][0] < precedent[0]:
        reechantillonnes.append(precedent)
    secondes = 0.0
    for (debut, altitude_debut), (fin, altitude_fin) in zip(reechantillonnes, reechantillonnes[1:]):
        pente = (altitude_fin - altitude_debut) / (fin - debut)
        vitesse_kmh = 6 * math.exp(-3.5 * abs(pente + 0.05))
        if hors_sentier:
            vitesse_kmh *= 0.6
        secondes += (fin - debut) * 3.6 / vitesse_kmh
    return secondes


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
    # Courbe issue des altitudes lissées par gpx2elev, réduite pour la page.
    points = [(float(distance), float(altitude))
              for profil in calcul.profiles
              for distance, altitude in zip(profil.distance, profil.elevations)]
    duree_marche_s = round(duree_tobler(points))
    pas = max(1, math.ceil((len(points) - 1) / (PROFIL_MAX_POINTS - 1)))
    profil = [(round(distance, 1), round(altitude, 1)) for distance, altitude in points[::pas]]
    derniere = (round(points[-1][0], 1), round(points[-1][1], 1))
    if profil[-1] != derniere:
        profil.append(derniere)
    return {"montee_m": round(calcul.gain.up), "descente_m": round(calcul.gain.down),
            "altitude_min_m": round(calcul.minimum), "altitude_max_m": round(calcul.maximum),
            "modele": serie.source.label, "protocole": core.PROTOCOL, "depuis_le_cache": serie.from_cache,
            "profil": profil, "duree_marche_s": duree_marche_s}
