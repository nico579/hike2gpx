"""Archive zip des cases choisies : de quoi passer des cartes et des zones
d'un PC à un autre, par une clé USB ou un lien de partage.

L'archive est le partage au téléphone (partage.dresser) mis dans un zip : le
même catalog.json au format du dépôt, les mêmes fichiers aux mêmes adresses,
chacun avec sa taille et son SHA-256.

  hike2gpx-cartes.zip
    catalog.json
    E5_N40/manifest.json, E5_N40/E5_N40.rd5, …   une zone de routage
    fonds/N43E006-scan25.mbtiles                  une carte en images
    fonds/N43E006-osm.map                         une carte vectorielle

Les fichiers sont rangés sans compression (ZIP_STORED), comme Android range
les images d'un APK : des tuiles JPEG ou une RD5 n'y perdent que 7 %, et la
compression divisait le débit par neuf (E5_N40 : 8,2 s en Deflate niveau 1,
0,9 s sans). L'archive s'écrit dans un fichier, où zipfile revient noter la
taille et le CRC de chaque entrée avant ses données : le lecteur en flux
d'Android (java.util.zip.ZipInputStream) n'accepte une entrée non compressée
qu'ainsi. Une archive compressée, d'une version précédente, se lit toujours.

À l'import, aucun nom venu de l'archive ne devient un chemin : chaque fichier
est lu à l'adresse que donne le catalogue, écrit sous un nom contrôlé, puis
vérifié contre son empreinte avant de prendre sa place ; une zone passe en
plus par hors_ligne.installer, qui la revérifie contre son manifeste.
"""
from __future__ import annotations

import json
import re
import shutil
import zipfile
import zlib
from pathlib import Path

from . import depot, hors_ligne as module_hors_ligne, lot, mapsforge, partage

CATALOGUE = "catalog.json"
_NOM_FOND = re.compile(r"[A-Za-z0-9_-]{1,80}")


class ErreurArchive(RuntimeError):
    pass


def ecrire(hors_ligne, cible: Path, selection: dict | None = None, empreintes: dict | None = None) -> int:
    """Écrit dans le fichier cible l'archive de la sélection, au sens de
    partage.dresser. Un fichier, pas un flux : zipfile y revient noter chaque
    taille avant ses données (voir plus haut). Rend le nombre de fichiers
    rangés, catalogue compris."""
    catalogue, fichiers = partage.dresser(hors_ligne, empreintes, selection)
    with zipfile.ZipFile(cible, "w", zipfile.ZIP_STORED, allowZip64=True) as archive:
        archive.writestr(CATALOGUE, json.dumps(catalogue, ensure_ascii=False, indent=1))
        for adresse, chemin in fichiers.items():
            archive.write(chemin, adresse)
    return 1 + len(fichiers)


def _copier(archive: zipfile.ZipFile, adresse: str, cible: Path) -> None:
    try:
        with archive.open(adresse) as source, open(cible, "wb") as destination:
            shutil.copyfileobj(source, destination, partage.BLOC)
    except KeyError as exc:
        raise ErreurArchive(f"{adresse} manque dans l'archive.") from exc
    except (zipfile.BadZipFile, zlib.error, EOFError) as exc:
        # Un membre tronqué ou corrompu (CRC, flux) : un message, pas une erreur 500 (audit A14).
        raise ErreurArchive(f"{adresse} est altéré dans l'archive ({exc}).") from exc


def _liste_d_objets(valeur, quoi: str) -> list:
    """La liste d'objets (dict) que doit être cette partie du catalogue. Le
    catalogue vient d'un autre PC : une forme inattendue est une erreur dite
    en clair, plus une AttributeError ou une KeyError (audit A14, 2026-11-13)."""
    if valeur is None:
        return []
    if not isinstance(valeur, list) or not all(isinstance(e, dict) for e in valeur):
        raise ErreurArchive(f"Catalogue de l'archive mal formé ({quoi}).")
    return valeur


def _fichier(f: dict, quoi: str) -> tuple:
    """(adresse, nom) d'un fichier du catalogue, tous deux du texte."""
    adresse, nom = f.get("url"), f.get("nom")
    if not isinstance(adresse, str) or not isinstance(nom, str):
        raise ErreurArchive(f"Catalogue de l'archive mal formé ({quoi} sans adresse ni nom).")
    return adresse, nom


def importer(hors_ligne, chemin_zip: Path) -> dict:
    """Installe les zones et les cartes de l'archive ; rend
    {"lots": [cases], "fonds": [noms]}. Une zone ou une carte déjà là est
    remplacée, comme par un nouveau téléchargement."""
    try:
        archive = zipfile.ZipFile(chemin_zip)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ErreurArchive(f"Archive illisible ({exc}).") from exc
    with archive:
        try:
            catalogue = json.loads(archive.read(CATALOGUE))
        except KeyError as exc:
            raise ErreurArchive("Ce zip n'est pas une archive de hike2gpx (catalog.json manque).") from exc
        except ValueError as exc:
            raise ErreurArchive(f"Catalogue de l'archive illisible ({exc}).") from exc
        if not isinstance(catalogue, dict) or catalogue.get("format") != depot.FORMAT \
                or not isinstance(catalogue.get("lots"), list):
            raise ErreurArchive("Archive d'un format inconnu.")
        lots, fonds = [], []
        travail = hors_ligne.racine / ".archive.part"
        try:
            for entree in _liste_d_objets(catalogue["lots"], "zones"):
                shutil.rmtree(travail, ignore_errors=True)
                travail.mkdir(parents=True)
                for f in _liste_d_objets(entree.get("fichiers"), "fichiers d'une zone"):
                    adresse, nom = _fichier(f, "un fichier de zone")
                    _copier(archive, adresse, travail / Path(nom).name)
                try:
                    lots.append(hors_ligne.installer(travail)["case"])
                except module_hors_ligne.ErreurLot as exc:
                    raise ErreurArchive(f"Zone {entree.get('case')} : {exc}") from exc
        finally:
            shutil.rmtree(travail, ignore_errors=True)
        hors_ligne.dossier_fonds.mkdir(parents=True, exist_ok=True)
        for cle, suffixe in (("fonds", ".mbtiles"), ("cartes", mapsforge.SUFFIXE)):
            for f in _liste_d_objets(catalogue.get(cle), cle):
                nom = f.get("nom")
                if not isinstance(nom, str) or not _NOM_FOND.fullmatch(nom):
                    raise ErreurArchive("Nom de carte invalide dans l'archive.")
                adresse, _ = _fichier(f, "une carte")
                cible = hors_ligne.dossier_fonds / f"{nom}{suffixe}"
                provisoire = cible.with_name(f".{cible.name}.archive.part")
                try:
                    _copier(archive, adresse, provisoire)
                    if provisoire.stat().st_size != f.get("octets") or lot.empreinte(provisoire) != f.get("sha256"):
                        raise ErreurArchive(f"{nom} : fichier altéré dans l'archive.")
                    provisoire.replace(cible)
                finally:
                    provisoire.unlink(missing_ok=True)
                fonds.append(nom)
    return {"lots": lots, "fonds": fonds}
