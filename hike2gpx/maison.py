"""Tuiles maison : la tuile BRouter refaite au fil des zones consultées, à
partir des tuiles Overpass et de la source officielle (BD TOPO ou ATKIS)
gardées en cache, avec les chemins qui manquent à OSM (fusion.py).

Elle n'est refaite que si une zone nouvelle s'ajoute, ou si l'une des
tuiles Overpass ou BD TOPO qui la composent a été relue depuis ; elle
contient alors les zones déjà vues (neuf tuiles, 250 km² : six secondes,
fusion comprise), tant qu'elles ne dépassent pas UNION_MAX tuiles : au-delà,
elle repart de la seule zone demandée, pour que le temps d'une zone nouvelle
reste celui de la zone et non de tout l'historique. Chaque fabrication va
dans un dossier neuf, que le serveur maison reprend ; les anciens sont
effacés quand plus rien ne les tient ouverts. Le même passage calcule les franchissements du réseau fusionné
entier : ceux d'OSM seul n'y suffisent plus, un raccord vers un chemin IGN
pouvant traverser une clôture. Ils remplacent alors ceux d'OSM seul.
"""
from __future__ import annotations

import logging
import shutil
import threading
import time
from pathlib import Path

from nico579_commons import atomique

from . import atkis, bdtopo, brouter, franchissements as fr, fusion

journal = logging.getLogger(__name__)

VERSION = 6     # format de l'état, règles de fusion ou d'analyse : l'augmenter refait la tuile


def _source(source):
    if source == "ign":
        return bdtopo
    if source == "atkis":
        return atkis
    raise ValueError("Source de chemins officiels inconnue.")


class TuilesMaison:
    UNION_MAX = 25      # tuiles de 0,05° gardées ensemble : environ 15 s de fabrication

    def __init__(self, installation: brouter.Installation, dossier):
        self.installation = installation
        self.dossier = Path(dossier)
        self.racine = installation.maison
        self.chemin_etat = self.racine / "etat.json"
        self._verrou = threading.Lock()

    def etat(self) -> dict:
        etat = atomique.lire_json(self.chemin_etat, None)
        if isinstance(etat, dict) and etat.get("version") == VERSION and isinstance(etat.get("tuiles"), dict) \
                and isinstance(etat.get("fabrication"), str):
            return etat
        return {"version": VERSION, "source": "ign", "fabrication": "", "tuiles": {}}

    def _dates(self, i, j, *, en_ligne, source="ign"):
        """Dates de lecture des tuiles Overpass et officielles (None si absentes),
        relues sur le réseau seulement si en_ligne."""
        module = _source(source)
        try:
            osm = fr.charger_tuile(i, j, self.dossier, en_ligne=en_ligne)["fetched_at"]
        except fr.ErreurDonnees:
            return None
        if en_ligne:
            module.charger_tuile(i, j, self.dossier)
        ign = module.lire_cache(i, j, self.dossier)
        return [osm, ign["fetched_at"]] if ign else None

    def preparer(self, tuiles, *, en_ligne: bool = True, suivi=None, source="ign"):
        """(dossier des tuiles .rd5, franchissements du réseau fusionné) pour
        ces tuiles de 0,05°, en refaisant la fabrication si besoin. Les
        franchissements rendus sont ceux de ces tuiles seulement. suivi(étape,
        faites, total) annonce la lecture des tuiles puis chaque étape de la
        fabrication, pour la barre de progression de la page."""
        suivi = suivi or (lambda *_: None)
        _source(source)
        with self._verrou:
            demandees = {}
            suivi("donnees", 0, len(tuiles))
            for k, (i, j) in enumerate(tuiles):
                dates = self._dates(i, j, en_ligne=en_ligne, source=source)
                if dates is None:
                    raise fr.ErreurDonnees("Données OSM ou chemins officiels de la zone indisponibles.")
                demandees[f"{i}_{j}"] = dates
                suivi("donnees", k + 1, len(tuiles))
            etat = self.etat()
            if etat.get("source", "ign") != source:
                etat = {"version": VERSION, "source": source, "fabrication": "", "tuiles": {}}
            dossier = self.racine / etat["fabrication"] if etat["fabrication"] else None
            if dossier is not None and (dossier / "segments").is_dir() \
                    and all(etat["tuiles"].get(cle) == dates for cle, dates in demandees.items()):
                segments, liste = dossier / "segments", self._franchissements(dossier)
            else:
                union = {**etat["tuiles"], **demandees}
                segments, liste = self._fabriquer(union if len(union) <= self.UNION_MAX else demandees, suivi, source)
            voulues = set(tuiles)
            return segments, [f for f in liste if fr.tuile_du_point(f["lat"], f["lon"]) in voulues]

    def _fabriquer(self, tuiles: dict, suivi=lambda *_: None, source="ign"):
        temps, debut = {}, time.monotonic()
        suivi("fusion", 0, 0)
        reseau, troncons, vus = fusion.Reseau(), [], set()
        retenues = {}
        for cle in sorted(tuiles):
            i, j = (int(v) for v in cle.split("_"))
            dates = self._dates(i, j, en_ligne=False, source=source)
            if dates is None:           # cache effacé depuis : la zone sort de la tuile
                continue
            retenues[cle] = dates
            reseau.ajouter_osm(fr.charger_tuile(i, j, self.dossier, en_ligne=False)["elements"])
            for t in _source(source).charger_tuile(i, j, self.dossier, en_ligne=False):
                if t["id"] not in vus:
                    vus.add(t["id"])
                    troncons.append(t)
        reseau.ajouter_ign(troncons, source=source)
        temps["fusion"] = time.monotonic() - debut
        suivi("tuiles", 0, 0)
        self.installation.preparer_maison()
        numero = 1 + max((int(d.name.split("-")[1]) for d in self.racine.glob("fabrication-*")
                          if d.name.split("-")[1].isdigit()), default=0)
        dossier = self.racine / f"fabrication-{numero}"
        pbf = self.racine / "zone.osm.pbf"
        self.racine.mkdir(parents=True, exist_ok=True)
        reseau.ecrire_pbf(pbf)
        segments = brouter.fabriquer_tuiles(self.installation, pbf, dossier)
        temps["tuiles"] = time.monotonic() - debut - temps["fusion"]
        suivi("analyse", 0, 0)
        # Comme pour une tuile Overpass, seuls les franchissements situés dans
        # les tuiles lues sont complets : au-delà, des barrières manquent.
        liste = [f for f in fr.analyser(reseau.elements())
                 if "{}_{}".format(*fr.tuile_du_point(f["lat"], f["lon"])) in retenues]
        atomique.ecrire_json(dossier / "franchissements.json", liste, indent=None)
        atomique.ecrire_json(self.chemin_etat, {"version": VERSION, "source": source,
                                                "fabrication": dossier.name, "tuiles": retenues,
                                                "chemins_ign": len(reseau.ign)})
        self._nettoyer(dossier.name)
        journal.info("Tuile maison %s : %d tuiles, %d chemins %s, %d franchissements ; fusion %.1f s, "
                     "PBF et BRouter %.1f s, analyse %.1f s", dossier.name, len(retenues), len(reseau.ign), source,
                     len(liste), temps["fusion"], temps["tuiles"],
                     time.monotonic() - debut - temps["fusion"] - temps["tuiles"])
        return segments, liste

    def _franchissements(self, dossier: Path) -> list:
        liste = atomique.lire_json(dossier / "franchissements.json", [])
        return liste if isinstance(liste, list) else []

    def _nettoyer(self, garder: str) -> None:
        for ancien in self.racine.glob("fabrication-*"):
            if ancien.name != garder:
                # Le serveur maison peut encore tenir l'ancienne tuile ouverte :
                # elle partira à la fabrication suivante.
                shutil.rmtree(ancien, ignore_errors=True)
