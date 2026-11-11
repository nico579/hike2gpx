"""Le dépôt des lots : un catalogue (catalog.json) et ses fichiers.

Le même catalogue, quel que soit celui qui le sert : le serveur le publie sur
GitHub Releases pour le PC et le téléphone, le PC le servira au téléphone par
le Wi-Fi. Chaque fichier y figure avec sa taille, son SHA-256 et son adresse,
relative à celle du catalogue : l'application n'a besoin que de cette adresse.

  {"format": 1, "genere": "2026-10-28T…Z",
   "lots": [{"case": "E5_N40", "type": "enrichi", "fournisseurs": ["ign"],
             "zone": […], "sources": {…}, "octets": 247000000,
             "fichiers": [{"nom": "E5_N40.rd5", "octets": …, "sha256": "…", "url": "E5_N40.E5_N40.rd5"},
                          {"nom": "manifest.json", …}]}]}

Une publication GitHub est une liste plate : les fichiers y prennent le nom
de leur case en préfixe (E5_N40.calques.mbtiles) ; un dossier servi tel quel
garde ses sous-dossiers (E5_N40/calques.mbtiles).

Servi par un PC à son téléphone (partage.py), le catalogue liste aussi ses
fonds de carte, dans une clé facultative « fonds » (docs/architecture/
partage-telephone.md) ; une publication n'en a jamais.
"""
from __future__ import annotations

import calendar
import http.client
import json
import logging
import shutil
import time
import urllib.parse
import urllib.request
from pathlib import Path

from . import __version__, lot

journal = logging.getLogger(__name__)
FORMAT = 1
# Le dépôt du serveur : une publication GitHub fixe, mise à jour sur place
# chaque semaine ; son adresse ne change jamais.
DEPOT = "https://github.com/nico579/hike2gpx-bundles/releases/download/bundles/catalog.json"
AGENT = {"User-Agent": f"hike2gpx/{__version__}"}
BLOC = 1 << 20


class ErreurDepot(RuntimeError):
    pass


class Abandon(Exception):
    pass


# ------------------------------------------------------------------ catalogue (serveur)

def ecrire_catalogue(racine: Path, publication: Path | None = None) -> Path:
    """Le catalogue des lots rangés dans racine/CASE. Sans publication, il est
    écrit dans racine et ses adresses gardent les sous-dossiers ; avec, les
    fichiers y sont copiés à plat (CASE.nom), prêts pour une publication GitHub."""
    racine = Path(racine)
    cible = Path(publication) if publication else racine
    cible.mkdir(parents=True, exist_ok=True)
    lots = []
    for manifeste in sorted(racine.glob("*/manifest.json")):
        dossier = manifeste.parent
        m = json.loads(manifeste.read_text(encoding="utf-8"))
        if publication:
            entree = entree_lot(m, manifeste, lambda nom, case=m["case"]: f"{case}.{nom}")
            for f in entree["fichiers"]:
                shutil.copy2(dossier / f["nom"], cible / f["url"])
        else:
            entree = entree_lot(m, manifeste, lambda nom, sous=dossier.name: f"{sous}/{nom}")
        lots.append(entree)
    chemin = cible / "catalog.json"
    chemin.write_text(json.dumps(catalogue(lots), indent=1, ensure_ascii=False), encoding="utf-8")
    return chemin


def entree_lot(m: dict, manifeste: Path, url) -> dict:
    """L'entrée d'un lot au catalogue : ses fichiers (ceux du manifeste et le
    manifeste lui-même), chacun avec l'adresse url(nom)."""
    fichiers = [*m["fichiers"], {"nom": "manifest.json", "octets": Path(manifeste).stat().st_size,
                                 "sha256": lot.empreinte(manifeste)}]
    fichiers = [{**f, "url": url(f["nom"])} for f in fichiers]
    return {"case": m["case"], "type": m.get("type", "enrichi"), "format": m.get("format"),
            "fournisseurs": m.get("fournisseurs", []), "zone": m.get("zone"),
            "emprise_enrichie": m.get("emprise_enrichie"), "sources": m.get("sources", {}),
            "octets": sum(f["octets"] for f in fichiers), "fichiers": fichiers}


def catalogue(lots: list, fonds: list | None = None, cartes: list | None = None) -> dict:
    """Le catalogue lui-même. Les fonds de carte (partage.py) n'y figurent que
    servis par un PC à son téléphone, jamais dans une publication ; un lecteur
    qui ne les connaît pas ignore la clé « fonds ». De même pour « cartes »,
    les cartes vectorielles d'OpenStreetMap (mapsforge.py), décrites comme
    les fonds."""
    contenu = {"format": FORMAT, "genere": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "lots": lots}
    if fonds is not None:
        contenu["fonds"] = fonds
    if cartes:
        contenu["cartes"] = cartes
    return contenu


def fraicheur(contenu: dict, attendues, maintenant: float, jours_max: int) -> tuple[list, list]:
    """L'âge des lots d'un catalogue, d'après l'édition OSM de chacun, et les
    cases attendues qui n'y sont pas. Rend les lignes (case, édition, âge en
    jours ; None pour une case absente), triées, et les problèmes : une case
    absente, ou un lot plus vieux que jours_max. Une case qui échoue chaque
    semaine garde son ancien lot publié : sans ce contrôle, personne ne le voit."""
    par_case = {l["case"]: l for l in contenu.get("lots", [])}
    lignes, problemes = [], []
    for case in sorted(set(par_case) | set(attendues)):
        lot = par_case.get(case)
        edition = ((lot or {}).get("sources") or {}).get("osm")
        if lot is None:
            lignes.append((case, None, None))
            problemes.append(f"{case} : absent du catalogue")
            continue
        try:
            age = (maintenant - calendar.timegm(time.strptime(edition, "%Y-%m-%dT%H:%M:%SZ"))) / 86400
        except (TypeError, ValueError):
            age = None
        lignes.append((case, edition if age is not None else str(edition or "?"), age))
        if age is None:
            problemes.append(f"{case} : édition OSM illisible ({edition!r})")
        elif age > jours_max:
            problemes.append(f"{case} : lot de {age:.0f} jours (plus de {jours_max})")
    return lignes, problemes


def tableau_fraicheur(lignes: list, problemes: list, jours_max: int) -> str:
    """Le contrôle de fraîcheur en Markdown, pour le résumé d'un run GitHub."""
    sortie = ["## Fraîcheur des lots", "", "| Case | Édition OSM | Âge |", "|---|---|---|"]
    for case, edition, age in lignes:
        if edition is None and age is None:
            sortie.append(f"| {case} | absent | |")
        else:
            marque = " (!)" if age is None or age > jours_max else ""
            sortie.append(f"| {case} | {edition} | {'?' if age is None else f'{age:.0f} j'}{marque} |")
    sortie.append("")
    sortie += [f"- {p}" for p in problemes] or [f"Tous les lots ont moins de {jours_max} jours."]
    return "\n".join(sortie) + "\n"


# ------------------------------------------------------------------ téléchargement (application)

def lire_catalogue(url: str, ouvrir=None) -> dict:
    """Le catalogue du dépôt, vérifié dans sa forme."""
    ouvrir = ouvrir or urllib.request.urlopen         # résolu à l'appel, pas au chargement
    try:
        with ouvrir(urllib.request.Request(url, headers=AGENT), timeout=30) as reponse:
            catalogue = json.loads(reponse.read())
    except (OSError, ValueError, http.client.HTTPException) as exc:
        raise ErreurDepot(f"Catalogue des lots illisible ({exc}).") from exc
    if not isinstance(catalogue, dict) or catalogue.get("format") != FORMAT \
            or not isinstance(catalogue.get("lots"), list):
        raise ErreurDepot("Catalogue des lots d'un format inconnu.")
    return catalogue


def _telecharger(url: str, cible: Path, octets: int, sha256: str, avancer, continuer, ouvrir) -> None:
    """Le fichier, repris là où il s'est arrêté (Range) après une coupure, puis
    contrôlé par son SHA-256 ; trois essais."""
    for essai in range(3):
        deja = cible.stat().st_size if cible.exists() else 0
        if deja < octets:
            entetes = {**AGENT, **({"Range": f"bytes={deja}-"} if deja else {})}
            try:
                with ouvrir(urllib.request.Request(url, headers=entetes), timeout=60) as reponse:
                    reprise = deja and getattr(reponse, "status", 200) == 206
                    if not reprise:
                        avancer(-deja)
                    with open(cible, "ab" if reprise else "wb") as f:
                        while bloc := reponse.read(BLOC):
                            if not continuer():
                                raise Abandon()
                            f.write(bloc)
                            avancer(len(bloc))
            except (OSError, http.client.HTTPException) as exc:     # coupure : l'essai suivant reprend
                journal.info("Dépôt : %s coupé (%s), reprise", cible.name, exc)
                time.sleep(2 * (essai + 1))
                continue
        if lot.empreinte(cible) == sha256:
            return
        avancer(-cible.stat().st_size)
        cible.unlink()                  # contenu faux : on repart de zéro
    raise ErreurDepot(f"{cible.name} : téléchargement impossible ou altéré.")


def telecharger(entree: dict, url_catalogue: str, travail: Path, *, suivi=None, continuer=None,
                ouvrir=None) -> Path:
    """Les fichiers d'un lot du catalogue dans travail, sous leur nom de lot
    (manifest.json, E5_N40.rd5…), prêts pour hors_ligne.installer, qui les
    revérifie contre le manifeste. suivi(faites, total) en octets."""
    suivi = suivi or (lambda faites, total: None)
    continuer = continuer or (lambda: True)
    ouvrir = ouvrir or urllib.request.urlopen
    travail = Path(travail)
    travail.mkdir(parents=True, exist_ok=True)
    total = sum(f["octets"] for f in entree["fichiers"])
    recus = [0]

    def avancer(n):
        recus[0] += n
        suivi(recus[0], total)
    for f in entree["fichiers"]:
        nom = Path(f["nom"]).name              # jamais de chemin venu du catalogue
        if not continuer():
            raise Abandon()
        cible = travail / nom
        recus[0] += min(cible.stat().st_size, f["octets"]) if cible.exists() else 0
        _telecharger(urllib.parse.urljoin(url_catalogue, f["url"]), cible, f["octets"], f["sha256"],
                     avancer, continuer, ouvrir)
    return travail
