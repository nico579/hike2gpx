"""Calques préparés par maille de 0,25° pour le serveur de données."""
from __future__ import annotations

import gzip
import json
import math
import os
from pathlib import Path

from . import franchissements as fr
from .franchissements import ErreurDonnees, VueRemplacee

FORMAT = 1
PAS = 0.25
TAILLE_MAX = 64 * 1024 * 1024


def indices_zone(sud, ouest, nord, est):
    return [(i, j) for i in range(math.floor(sud * 4), math.ceil(nord * 4))
            for j in range(math.floor(ouest * 4), math.ceil(est * 4))]


def bornes_indices(indices):
    return [min(i for i, _ in indices) / 4, min(j for _, j in indices) / 4,
            (max(i for i, _ in indices) + 1) / 4, (max(j for _, j in indices) + 1) / 4]


def chemin(dossier, source, i, j):
    if not source.isascii() or not source.replace("_", "").isalnum():
        raise ValueError("Identifiant de source invalide")
    return Path(dossier) / "mailles" / source / f"{i}_{j}.json.gz"


def publier(dossier, source, i, j, *, osm, officiels, franchissements):
    cible = chemin(dossier, source, i, j)
    cible.parent.mkdir(parents=True, exist_ok=True)
    contenu = {"format": FORMAT, "source": source, "maille": [i, j],
               "osm": osm, "officiels": officiels,
               "franchissements": franchissements}
    provisoire = cible.with_name(cible.name + ".part")
    with provisoire.open("wb") as fichier:
        with gzip.GzipFile(fileobj=fichier, mode="wb", mtime=0) as compresseur:
            compresseur.write(json.dumps(contenu, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        fichier.flush()
        os.fsync(fichier.fileno())
    os.replace(provisoire, cible)
    return cible


def lire(dossier, source, i, j):
    fichier = chemin(dossier, source, i, j)
    try:
        with gzip.open(fichier, "rb") as entree:
            brut = entree.read(TAILLE_MAX + 1)
        if len(brut) > TAILLE_MAX:
            raise ValueError("Maille trop volumineuse")
        contenu = json.loads(brut)
    except (OSError, ValueError) as exc:
        raise ErreurDonnees(f"Maille {source} {i}_{j} absente ou illisible.") from exc
    if (not isinstance(contenu, dict) or contenu.get("format") != FORMAT
            or contenu.get("source") != source or contenu.get("maille") != [i, j]):
        raise ErreurDonnees(f"Maille {source} {i}_{j} incompatible.")
    return contenu


def calque(source, zone, dossier, genre, *, continuer=lambda: True, suivi=None):
    indices = indices_zone(*zone)
    if not indices:
        raise ErreurDonnees("Zone vide.")
    couverture = fr.bornes_zone(*zone)

    def dans_vue(element, cle):
        if cle == "franchissements":
            return (couverture[0] <= element["lat"] < couverture[2]
                    and couverture[1] <= element["lon"] < couverture[3])
        points = element.get("pts") or []
        if not points:
            return False
        latitudes, longitudes = zip(*points)
        return (min(latitudes) < couverture[2] and max(latitudes) >= couverture[0]
                and min(longitudes) < couverture[3] and max(longitudes) >= couverture[1])

    elements = {}
    clefs = ("voies", "barrieres", "franchissements") if genre == "osm" else ("troncons",)
    for cle in clefs:
        elements[cle] = {}
    if suivi:
        suivi(0, len(indices))
    for rang, (i, j) in enumerate(indices, 1):
        if not continuer():
            raise VueRemplacee()
        contenu = lire(dossier, source, i, j)
        groupe = contenu["osm"] if genre == "osm" else {"troncons": contenu["officiels"]}
        if genre == "osm":
            groupe = {**groupe, "franchissements": contenu["franchissements"]}
        for cle in clefs:
            for element in groupe[cle]:
                if not dans_vue(element, cle):
                    continue
                identifiant = element["cle"] if cle == "franchissements" else element["id"]
                elements[cle][identifiant] = element
        if suivi:
            suivi(rang, len(indices))
    return {**{cle: list(valeurs.values()) for cle, valeurs in elements.items()},
            "bornes": couverture}
