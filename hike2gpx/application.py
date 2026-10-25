"""Une instance de hike2gpx : réglages, moteur BRouter, et les routes /api/*
de la page.

Un itinéraire se calcule en quatre temps : la zone des points, élargie ;
les franchissements de cette zone ; BRouter avec leurs coupes ; puis, si le
tracé sort de la zone examinée, la zone s'agrandit et le calcul recommence,
pour qu'aucun détour ne passe par une barrière jamais vérifiée.
"""
from __future__ import annotations

import logging
import json
import hashlib
import math
import os
import re
import secrets
import shutil
import threading
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from nico579_commons import atomique
from nico579_commons import langue as langue_commune

from . import __version__, brouter, cloud, communes, franchissements, geofabrik, journaux, mailles, maison, osmfr, providers

journal = logging.getLogger(__name__)

# Journal des calculs dans le dossier de données : 1 Mo, gardé trois fois.
FICHIER_JOURNAL = "hike2gpx.log"  # repli pour une Application hors serveur
_JOURNAUX: dict[Path, Path] = {}
LIGNES_JOURNAL = 300        # montrées par la page
SESSIONS_GARDEES = 10       # journaux horodatés gardés, celui de la session en cours compris
LENT_S = 60.0               # au-delà, l'itinéraire est signalé lent dans le journal
# Étapes d'un calcul, telles que le journal en détaille les temps.
NOMS_ETAPES = {"debut": "préparation", "donnees": "lecture des données", "fusion": "fusion des chemins officiels",
               "tuiles": "tuile BRouter", "analyse": "franchissements", "itineraire": "calcul BRouter",
               "comparaison": "tracé standard"}
ZONE_CALQUE_MAX_DEG2 = 0.03  # un grand écran au zoom 14 ; au-delà, trop de tuiles à lire
# Un fournisseur cartographique peut être ajouté côté page sans modifier le
# choix du pays : seul son identifiant dans l'index Geofabrik est déclaré ici.
PAYS_CARTES = providers.PAYS_CARTES
MARGE_DEG = 0.01            # environ 1 km autour des points
MARGE_RELATIVE = 0.25
POINTS_MAX = 50
ELARGISSEMENTS = 3
# Tuiles de 0,05° lues (OSM et source officielle) et fusionnées pour un calcul :
# environ 55 × 40 km. Au-delà, la première lecture prendrait des dizaines de
# minutes ; mieux vaut découper le parcours en étapes.
TUILES_MAX = 100
_CLE_IGN = re.compile(r"^[A-Za-z0-9_\-]{0,100}$")


def configurer_journal(dossier) -> Path:
    """Un fichier horodaté neuf par démarrage du serveur ; seules les
    SESSIONS_GARDEES dernières sessions restent, rotations comprises, sans
    quoi un fichier de plus s'ajouterait à chaque démarrage, à jamais."""
    racine_donnees = Path(dossier).resolve()
    dossier_logs = journaux.dossier(racine_donnees)
    chemin = _JOURNAUX.get(racine_donnees)
    racine = logging.getLogger("hike2gpx")
    if chemin is not None and any(isinstance(h, RotatingFileHandler) and Path(h.baseFilename) == chemin
                                  for h in racine.handlers):
        return chemin
    # Le nom horodaté se trie dans l'ordre chronologique.
    dossier_logs.mkdir(parents=True, exist_ok=True)
    for ancienne in sorted(dossier_logs.glob("hike2gpx-*.log"))[:-(SESSIONS_GARDEES - 1)]:
        for fichier in dossier_logs.glob(ancienne.name + "*"):
            fichier.unlink(missing_ok=True)
    chemin = dossier_logs / f"hike2gpx-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.log"
    fichier = RotatingFileHandler(chemin, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    fichier.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    racine.addHandler(fichier)
    racine.setLevel(logging.INFO)
    _JOURNAUX[racine_donnees] = chemin
    return chemin


def zone_autour(points, marge_relative=MARGE_RELATIVE):
    lats, lons = [p[0] for p in points], [p[1] for p in points]
    marge_lat = max(MARGE_DEG, (max(lats) - min(lats)) * marge_relative)
    marge_lon = max(MARGE_DEG / max(.2, math.cos(math.radians(sum(lats) / len(lats)))),
                    (max(lons) - min(lons)) * marge_relative)
    return (round(min(lats) - marge_lat, 6), round(min(lons) - marge_lon, 6),
            round(max(lats) + marge_lat, 6), round(max(lons) + marge_lon, 6))


def contient(zone, autre, marge_deg=0.002) -> bool:
    return (zone[0] + marge_deg <= autre[0] and zone[1] + marge_deg <= autre[1]
            and autre[2] <= zone[2] - marge_deg and autre[3] <= zone[3] - marge_deg)


def union(a, b):
    return min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])


def lire_zone(requete: dict):
    """(sud, ouest, nord, est) des paramètres s, w, n, e d'une requête, ou
    None s'ils manquent ou ne décrivent pas un rectangle valide."""
    try:
        sud, ouest, nord, est = (float(requete[c][0]) for c in ("s", "w", "n", "e"))
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    if all(math.isfinite(v) for v in (sud, ouest, nord, est)) and -85 <= sud < nord <= 85 \
            and -180 <= ouest < est <= 180:
        return sud, ouest, nord, est
    return None


def lire_vue(requete: dict):
    """L'instant (en ms, croissant même d'un rechargement de la page à
    l'autre) où la page a demandé cette vue d'un calque : paramètre vue, ou
    None sans lui."""
    try:
        vue = float(requete["vue"][0])
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return vue if math.isfinite(vue) else None


def valider_points(brut) -> list:
    if not isinstance(brut, list) or not 2 <= len(brut) <= POINTS_MAX:
        raise ValueError(f"Il faut entre 2 et {POINTS_MAX} points.")
    points = []
    for p in brut:
        if not (isinstance(p, list) and len(p) == 2 and all(isinstance(v, (int, float)) for v in p)
                and -85 <= p[0] <= 85 and -180 <= p[1] <= 180):
            raise ValueError("Point invalide.")
        points.append((float(p[0]), float(p[1])))
    return points


def sur_le_trace(coordonnees, liste) -> list:
    """Franchissements que le tracé passe vraiment : il coupe l'une de leurs
    coupes. La proximité ne suffit pas : deux voies croisent parfois la même
    clôture à un mètre l'une de l'autre, l'une bloquée, l'autre non (constaté
    à Garéoult, way 1558904264). Distance comptée depuis le départ."""
    if len(coordonnees) < 2 or not liste:
        return []
    proj = franchissements.Projection(coordonnees[0][1], coordonnees[0][0])
    pts = [proj.xy(c[1], c[0]) for c in coordonnees]
    cumul = [0.0]
    grille = franchissements._Grille()
    for k, (a, b) in enumerate(zip(pts, pts[1:])):
        cumul.append(cumul[-1] + math.dist(a, b))
        grille.ajouter(k, a, b)
    resultat = []
    for f in liste:
        distances = []
        for (lon1, lat1), (lon2, lat2) in f["coupes"]:
            c, d = proj.xy(lat1, lon1), proj.xy(lat2, lon2)
            for k in grille.candidats(c, d):
                inter = franchissements._intersection(pts[k], pts[k + 1], c, d)
                if inter is not None:
                    distances.append(cumul[k] + inter[0] * (cumul[k + 1] - cumul[k]))
        if distances:
            resultat.append({**{k: f[k] for k in ("cle", "statut", "raison", "nature", "lat", "lon", "osm")},
                             "distance_m": round(min(distances))})
    return sorted(resultat, key=lambda f: f["distance_m"])


def portions_ign(trace) -> list:
    """Portions du tracé sur des chemins officiels, lues dans les messages de
    BRouter : chaque ligne y résume un morceau de mêmes étiquettes, avec sa
    longueur et la position, en millionièmes de degré, de son dernier point
    (constaté le 19 octobre : c'est exactement un point du tracé)."""
    messages = (trace.get("properties") or {}).get("messages") or []
    if len(messages) < 2 or "WayTags" not in messages[0]:
        return []
    entete = messages[0]
    i_lon, i_lat, i_dist, i_tags = (entete.index(c) for c in ("Longitude", "Latitude", "Distance", "WayTags"))
    coords = trace["geometry"]["coordinates"]
    micro = [(round(c[0] * 1e6), round(c[1] * 1e6)) for c in coords]

    def rang(position, depuis):
        for k in range(depuis, len(micro)):
            if micro[k] == position:
                return k
        return min(range(depuis, len(micro)),       # arrondi inattendu : le plus proche
                   key=lambda k: abs(micro[k][0] - position[0]) + abs(micro[k][1] - position[1]))

    portions, cumul, debut_rang = [], 0.0, 0
    for ligne in messages[1:]:
        longueur = float(ligne[i_dist])
        fin_rang = rang((int(ligne[i_lon]), int(ligne[i_lat])), debut_rang)
        source = next((nom for nom in providers.SOURCES if f"hike2gpx={nom}" in ligne[i_tags]), None)
        if source:
            if portions and portions[-1]["fin_rang"] == debut_rang and portions[-1]["source"] == source:
                portions[-1].update(fin_rang=fin_rang, longueur_m=portions[-1]["longueur_m"] + longueur)
            else:
                portions.append({"debut_m": round(cumul), "longueur_m": longueur, "debut_rang": debut_rang,
                                 "fin_rang": fin_rang, "source": source})
        cumul += longueur
        debut_rang = fin_rang
    return [{"debut_m": p["debut_m"], "longueur_m": round(p["longueur_m"]),
             "coords": [[c[1], c[0]] for c in coords[p["debut_rang"]:p["fin_rang"] + 1]],
             **({"source": p["source"]} if p["source"] != "ign" else {})} for p in portions]


def entrees_ign(portions) -> list:
    """Les portions officielles comme points à vérifier sur le tracé."""
    return [{"cle": f"{p.get('source', 'ign')}-{k}", "statut": "uncertain",
             "raison": f"Chemin {providers.source(p.get('source', 'ign')).nom} absent d'OpenStreetMap : existence et accès à vérifier",
             "nature": f"Chemin {providers.source(p.get('source', 'ign')).nom} de {p['longueur_m']} m",
             "longueur_m": p["longueur_m"],
             "lat": p["coords"][0][0], "lon": p["coords"][0][1],
             "osm": None, "distance_m": p["debut_m"]} for k, p in enumerate(portions) if p["coords"]]


def _nombre(proprietes, cle):
    try:
        return float(proprietes.get(cle))
    except (TypeError, ValueError):
        return None


def km_texte(metres) -> str:
    """Distance comme l'écrit la page : « 1,25 km »."""
    return f"{metres / 1000:.2f}".replace(".", ",") + " km"


class Application:
    def __init__(self, dossier: Path, *, mode_serveur: bool = False):
        self.dossier = Path(dossier)
        self.mode_serveur = mode_serveur
        self.installation = brouter.Installation(self.dossier)
        self.maison = maison.TuilesMaison(self.installation, self.dossier)
        self.preferences = self.dossier / "preferences.json"
        self.cloud = None if mode_serveur else cloud.Client(self.preferences)
        self.serveur = None
        self.serveur_maison = None
        self._verrou_moteur = threading.Lock()
        self._verrou_calcul = threading.Lock()
        self._verrou_denivele = threading.Lock()
        # Numéro de la vue en cours de chaque calque : une vue plus récente
        # arrête la lecture des tuiles de la précédente.
        self._vues = {"osm": 0, **{p.calque: 0 for p in providers.SOURCES.values()}}
        self._verrou_vues = threading.Lock()
        # Avancement de la vue en cours de chaque calque, pour la barre de la
        # page : {"faites", "total", "debut"} (tuiles), absent hors lecture.
        self._lectures = {}
        # Moteur et tuiles BRouter téléchargés en tâche de fond (_brouter_automatique).
        self._verrou_brouter = threading.Lock()
        self._fil_brouter = None
        self._brouter_en_cours = {}
        self._echecs_brouter = {}       # "moteur" ou nom de tuile -> instant (monotonic) du dernier échec
        self._progression = {"actif": False}
        self._debut_calcul = time.monotonic()
        self._temps_etapes, self._etape_courante = {}, None

    # ---------------------------------------------------------- réglages

    def reglages(self) -> dict:
        prefs = atomique.lire_json(self.preferences, {})
        cle = prefs.get("cle_ign") if isinstance(prefs, dict) else None
        return {"cle_ign": cle if isinstance(cle, str) and _CLE_IGN.match(cle) else "",
                "renouvellement_jours": geofabrik.jours_renouvellement(self.dossier)}

    def etat_serveur(self) -> dict:
        return self.cloud.etat(force=True) if self.cloud else {"actif": False, "raison": "mode_serveur"}

    def enregistrer_serveur(self, payload) -> dict:
        if self.cloud is None:
            return {"erreur": "Le serveur ne peut pas se connecter à lui-même."}
        try:
            adresse = cloud.valider_adresse((payload or {}).get("adresse", ""))
        except (ValueError, AttributeError) as exc:
            return {"erreur": str(exc)}
        prefs = atomique.lire_json(self.preferences, {})
        prefs = prefs if isinstance(prefs, dict) else {}
        prefs["serveur_url"] = adresse
        atomique.ecrire_json(self.preferences, prefs)
        self.cloud.invalider()
        return self.etat_serveur()

    def enregistrer_reglages(self, payload) -> dict:
        payload = payload or {}
        cle = payload.get("cle_ign", "")
        if not isinstance(cle, str) or not _CLE_IGN.match(cle.strip()):
            return {"erreur": "Clé IGN invalide : lettres, chiffres, _ et - seulement."}
        jours = payload.get("renouvellement_jours", self.reglages()["renouvellement_jours"])
        if type(jours) is not int or not 1 <= jours <= 365:
            return {"erreur": "Le délai de renouvellement doit être compris entre 1 et 365 jours."}
        prefs = atomique.lire_json(self.preferences, {})
        prefs = prefs if isinstance(prefs, dict) else {}
        prefs["cle_ign"] = cle.strip()
        prefs["renouvellement_jours"] = jours
        atomique.ecrire_json(self.preferences, prefs)
        return self.reglages()

    def lire_langue(self):
        """Langue choisie dans la page (« fr », « en »), ou None : le choix FR / EN
        du commun prend alors celle du navigateur."""
        prefs = atomique.lire_json(self.preferences, {})
        return prefs.get("langue") if isinstance(prefs, dict) else None

    def ecrire_langue(self, code: str) -> None:
        prefs = atomique.lire_json(self.preferences, {})
        prefs = prefs if isinstance(prefs, dict) else {}
        prefs["langue"] = code
        atomique.ecrire_json(self.preferences, prefs)

    def etat(self) -> dict:
        segments = sorted(p.stem for p in self.installation.segments.glob("*.rd5")) \
            if self.installation.segments.is_dir() else []
        return {"app": "hike2gpx", "version": __version__, "mode_serveur": self.mode_serveur,
                **({} if self.mode_serveur else {"dossier": str(self.dossier)}),
                "moteur_installe": self.installation.installee(), "segments": segments,
                "brouter": brouter.VERSION, "poids_a_verifier": brouter.POIDS_A_VERIFIER}

    # ---------------------------------------------------------- moteur

    def moteur(self) -> int:
        with self._verrou_moteur:
            if self.serveur is None or self.serveur.processus is None or self.serveur.processus.poll() is not None:
                serveur = brouter.Serveur(self.installation)
                serveur.demarrer()
                self.serveur = serveur
            return self.serveur.port

    def moteur_maison(self, segments) -> int:
        """Serveur BRouter sur les tuiles maison, relancé quand elles changent
        de dossier (une nouvelle fabrication)."""
        with self._verrou_moteur:
            s = self.serveur_maison
            if s is None or s.segments != segments or s.processus is None or s.processus.poll() is not None:
                if s is not None:
                    s.arreter()
                s = brouter.Serveur(self.installation, segments=segments, profils=self.installation.profils_maison)
                s.demarrer()
                self.serveur_maison = s
            return s.port

    def arreter(self) -> None:
        with self._verrou_moteur:
            for serveur in (self.serveur, self.serveur_maison):
                if serveur is not None:
                    serveur.arreter()
            self.serveur = self.serveur_maison = None

    def installer_moteur(self, _payload=None) -> dict:
        """Installe le moteur absent ou renouvelle les tuiles périmées en fond."""
        en_cours = self._brouter_automatique([])
        if en_cours is None:
            en_cours = self._renouveler_brouter_si_perime()
        return {"brouter_en_cours": en_cours}

    # Après un échec, pas de nouvel essai pour le même élément avant une heure.
    REESSAI_BROUTER_S = 3600.0

    def _brouter_automatique(self, segments: list) -> dict | None:
        """Le moteur BRouter et les tuiles de routage qui manquent se
        téléchargent d'eux-mêmes en tâche de fond, sans bouton (décision de
        Nico du 2026-10-19, comme les extraits OSM). Rend ce qui se télécharge,
        {"moteur": bool, "segments": [...]}, ou None."""
        with self._verrou_brouter:
            if self._fil_brouter and self._fil_brouter.is_alive():
                return {**self._brouter_en_cours, "segments": list(self._brouter_en_cours["segments"])}
            maintenant = time.monotonic()
            recent = lambda cle: maintenant - self._echecs_brouter.get(cle, -self.REESSAI_BROUTER_S) \
                < self.REESSAI_BROUTER_S
            moteur = not self.installation.installee() and not recent("moteur")
            a_faire = [n for n in segments if not self.installation.segment_present(n) and not recent(n)]
            if not moteur and not a_faire:
                return None
            # La réponse est copiée avant le départ du fil, qui retire chaque
            # tuile de la liste en cours dès qu'il en a fini.
            reponse = {"moteur": moteur, "segments": list(a_faire)}
            self._brouter_en_cours = {"moteur": moteur, "segments": a_faire}
            self._fil_brouter = threading.Thread(target=self._telecharger_brouter, args=(moteur, list(a_faire)),
                                                 daemon=True, name="brouter-donnees")
            self._fil_brouter.start()
            return reponse

    def _telecharger_brouter(self, moteur: bool, segments: list) -> None:
        try:
            if moteur:
                debut = time.monotonic()
                try:
                    self.installation.installer()
                except (brouter.ErreurBRouter, OSError, ValueError) as exc:
                    self._echecs_brouter["moteur"] = time.monotonic()
                    journal.warning("Moteur BRouter non installé : %s", exc)
                    return
                journal.info("Moteur BRouter installé automatiquement en %.0f s", time.monotonic() - debut)
                self._brouter_en_cours["moteur"] = False
            for nom in segments:
                debut = time.monotonic()
                try:
                    self.installation.telecharger_segment(nom)
                except (brouter.ErreurBRouter, ValueError) as exc:
                    self._echecs_brouter[nom] = time.monotonic()
                    journal.warning("Tuile BRouter %s non téléchargée : %s", nom, exc)
                else:
                    journal.info("Tuile BRouter %s téléchargée automatiquement en %.0f s", nom,
                                 time.monotonic() - debut)
                finally:
                    self._brouter_en_cours["segments"].remove(nom)
        finally:
            self._brouter_en_cours = {}

    # ---------------------------------------------------------- avancement

    def _avancer(self, etape: str, fraction: float, faites: int = 0, total: int = 0, passe: int = 1) -> None:
        """Étape du calcul en cours, lue par la page pour sa barre de
        progression. Le temps écoulé depuis l'annonce précédente revient à
        l'étape qu'elle annonçait : le journal en fait le détail en fin de
        calcul."""
        maintenant = time.monotonic()
        if self._etape_courante is not None:
            nom, depuis = self._etape_courante
            self._temps_etapes[nom] = self._temps_etapes.get(nom, 0.0) + maintenant - depuis
        self._etape_courante = (etape, maintenant)
        self._progression = {"actif": True, "etape": etape, "fraction": round(fraction, 3), "faites": faites,
                             "total": total, "passe": passe, "duree_s": round(maintenant - self._debut_calcul, 1)}

    def _detail_des_etapes(self) -> str:
        """« données 1,2 s ; calcul BRouter 0,9 s… » pour le journal, en
        fermant l'étape en cours."""
        if self._etape_courante is not None:
            nom, depuis = self._etape_courante
            self._temps_etapes[nom] = self._temps_etapes.get(nom, 0.0) + time.monotonic() - depuis
            self._etape_courante = None
        return " ; ".join(f"{NOMS_ETAPES.get(nom, nom)} {duree:.1f} s" for nom, duree in self._temps_etapes.items())

    def progression(self) -> dict:
        """L'étape du calcul en cours, et l'avancement des calques en lecture :
        tuiles lues sur tant, depuis tant de secondes."""
        maintenant = time.monotonic()
        calques = {}
        for identifiant, lecture in list(self._lectures.items()):
            cle = identifiant.split(":", 1)[0] if self.mode_serveur else identifiant
            if cle not in calques or lecture["debut"] > calques[cle]["debut"]:
                calques[cle] = lecture
        calques = {cle: {"faites": l["faites"], "total": l["total"],
                         "duree_s": round(maintenant - l["debut"], 1)} for cle, l in calques.items()}
        return {**self._progression, "calques": calques}

    def lire_journal(self) -> dict:
        """Les dernières lignes du journal des calculs, pour la page."""
        chemin = _JOURNAUX.get(self.dossier.resolve(), journaux.dossier(self.dossier) / FICHIER_JOURNAL)
        try:
            lignes = chemin.read_text(encoding="utf-8", errors="replace").splitlines()[-LIGNES_JOURNAL:]
        except OSError:
            lignes = []
        return {"chemin": str(chemin), "lignes": lignes}

    # ---------------------------------------------------------- itinéraire

    def itineraire(self, payload) -> dict:
        """Le calcul, avec son avancement pour la page et sa trace dans le
        journal : début, fin, erreurs, lenteurs."""
        payload = payload or {}
        with self._verrou_calcul:
            self._debut_calcul = time.monotonic()
            self._temps_etapes, self._etape_courante = {}, None
            self._avancer("debut", 0.02)
            try:
                reponse = self._itineraire(payload)
            except Exception:
                journal.exception("Itinéraire : erreur inattendue après %.1f s (%s)",
                                  time.monotonic() - self._debut_calcul, self._detail_des_etapes())
                raise
            finally:
                self._progression = {"actif": False}
            duree = time.monotonic() - self._debut_calcul
            etapes = self._detail_des_etapes()
            if "erreur" in reponse:
                journal.warning("Itinéraire en erreur après %.1f s : %s (étapes : %s)", duree, reponse["erreur"],
                                etapes)
            else:
                journal.info("Itinéraire calculé en %.1f s : %.0f m, moteur %s, %d point(s) à vérifier, "
                             "%d portion(s) officielles%s", duree, reponse["longueur_m"] or 0, reponse["moteur"],
                             len(reponse["sur_le_trace"]), len(reponse["portions_ign"]),
                             f" ; {reponse['avertissement']}" if reponse["avertissement"] else "")
                journal.info("Étapes : %s", etapes)
                if duree > LENT_S:
                    journal.warning("Itinéraire lent : %.1f s, voir les étapes ci-dessus", duree)
            return reponse

    def _itineraire(self, payload) -> dict:
        try:
            points = valider_points(payload.get("points"))
        except ValueError as exc:
            return {"erreur": str(exc)}
        strict, comparer = bool(payload.get("strict")), bool(payload.get("comparer", True))
        ign = bool(payload.get("ign", True))
        source = payload.get("source", "ign")
        if source not in providers.SOURCES:
            return {"erreur": "Source de chemins officiels inconnue."}
        debut = time.monotonic()
        zone = zone_autour(points)
        if ign and not providers.source(source).disponible(zone):
            return {"erreur": f"Chemins {providers.source(source).nom} indisponibles dans cette zone.",
                    "code": "source_hors_zone"}
        if self.mode_serveur:
            # Le calcul distant est un secours sur données déjà publiées. Une
            # requête cliente ne déclenche ni fusion, ni Overpass, ni création
            # de RD5 : seule la commande SSH prépare ces données.
            paquet = self.lire_paquet(zone, source, str(int(strict)), str(int(ign)))
            if not paquet.get("pret"):
                return {"erreur": "Paquet de zone non préparé sur le serveur.",
                        "code": "zone_non_preparee"}
            if not self.installation.installee():
                return {"erreur": "Le moteur BRouter n'est pas installé.", "moteur_absent": True}
            try:
                fichier = paquet["segments"][0]["url"]
                jeton = fichier.split("/")[3]
                if not re.fullmatch(r"[0-9a-f]{32}", jeton):
                    raise ValueError("Identifiant de paquet invalide.")
                reponse = self._itineraire_paquet(points, zone, paquet,
                                                   self.dossier / "paquets" / jeton, debut)
                if "erreur" not in reponse:
                    reponse["moteur"] = "serveur-secours"
                return reponse
            except (brouter.ErreurBRouter, OSError, ValueError, KeyError, IndexError) as exc:
                return {"erreur": str(exc)}
        # Un paquet vérifié reste utilisable lorsque le serveur ne répond plus.
        if self.cloud and self.cloud.etat()["adresse"]:
            try:
                paquet, dossier = self.cloud.paquet({"source": source, "officiel": ign,
                                                      "strict": strict}, self.dossier, zone)
                if self.installation.installee():
                    resultat = self._itineraire_paquet(points, zone, paquet, dossier, debut)
                    if "erreur" not in resultat:
                        return resultat
            except (cloud.Indisponible, brouter.ErreurBRouter, OSError, ValueError) as exc:
                journal.warning("Calcul sur paquet cloud indisponible : %s", exc)
        # Un calcul est un usage réel de la région : son extrait OSM part en
        # tâche de fond s'il manque, Overpass servant en attendant ; de même le
        # moteur et les tuiles BRouter, sans lesquels il n'y a pas de calcul.
        extrait = self._extrait_automatique(zone, "calcul d'itinéraire")
        if not self.installation.installee():
            return {"erreur": "Le moteur BRouter n'est pas installé.", "moteur_absent": True,
                    "brouter_en_cours": self._brouter_automatique(brouter.segments_zone(*zone))}
        avertissement = detail_avertissement = None
        journal.info("Itinéraire : %d points, %d tuiles, chemins %s %s, mode strict %s", len(points),
                     len(franchissements.tuiles_zone(*zone)), source.upper(),
                     "oui" if ign else "non", "oui" if strict else "non")
        try:
            for essai in range(ELARGISSEMENTS):
                passe = essai + 1
                nombre = len(franchissements.tuiles_zone(*zone))
                if nombre > TUILES_MAX:
                    return {"erreur": f"Zone trop étendue : {nombre} tuiles de 0,05° à examiner, au plus "
                                      f"{TUILES_MAX}. Découpez le parcours en étapes plus courtes.",
                            "code": "zone_trop_etendue", "valeurs": {"nombre": nombre, "max": TUILES_MAX}}
                manquants = [n for n in brouter.segments_zone(*zone)
                             if not self.installation.segment_present(n)]
                if manquants:
                    return {"erreur": "Données BRouter absentes pour cette zone.",
                            "segments_manquants": manquants, "brouter_en_cours": self._brouter_automatique(manquants)}
                trace, moteur_utilise = None, "standard"
                if ign:
                    # Tuiles maison : OSM plus les chemins officiels qui y manquent, avec
                    # les franchissements du réseau fusionné. Si elles ne peuvent se
                    # faire, le moteur standard calcule sur OSM seul ; un itinéraire
                    # introuvable sur elles reste une erreur.
                    def suivi_maison(etape, faites, total, passe=passe):
                        fraction = {"donnees": 0.05 + 0.45 * faites / max(total, 1), "fusion": 0.5,
                                    "tuiles": 0.6, "analyse": 0.78}[etape]
                        self._avancer(etape, fraction, faites, total, passe)
                    try:
                        segments, liste = self.maison.preparer(franchissements.tuiles_zone(*zone),
                                                               suivi=suivi_maison, source=source)
                        port = self.moteur_maison(segments)
                    except (franchissements.ErreurDonnees, brouter.ErreurBRouter, OSError, ImportError,
                            ValueError) as exc:
                        nom_source = providers.source(source).nom
                        avertissement = f"Chemins {nom_source} indisponibles, calcul sur OSM seul : {exc}"
                        detail_avertissement = str(exc)
                        journal.warning("Chemins %s indisponibles : %s", nom_source, exc)
                        ign = False     # pas de nouvel essai si la zone s'élargit
                    else:
                        self._avancer("itineraire", 0.82, passe=passe)
                        trace = brouter.calculer(port, points, liste, strict=strict)
                        moteur_utilise = "maison"
                if trace is None:
                    liste = franchissements.franchissements_zone(
                        *zone, self.dossier, suivi=lambda faites, total, passe=passe: self._avancer(
                            "donnees", 0.05 + 0.6 * faites / max(total, 1), faites, total, passe))
                    self._avancer("itineraire", 0.7, passe=passe)
                    trace = brouter.calculer(self.moteur(), points, liste, strict=strict)
                coords = trace["geometry"]["coordinates"]
                etendue = (min(c[1] for c in coords), min(c[0] for c in coords),
                           max(c[1] for c in coords), max(c[0] for c in coords))
                if contient(zone, etendue):
                    break
                journal.info("Le tracé sort de la zone examinée : zone élargie (passe %d)", passe + 1)
                zone = union(zone, zone_autour([etendue[:2], etendue[2:]], 0.1))
            else:
                return {"erreur": "Le tracé sort sans cesse de la zone examinée : rapprochez les points."}
        except (franchissements.ErreurDonnees, brouter.ErreurBRouter) as exc:
            reponse = {"erreur": str(exc)}
            if isinstance(exc, franchissements.ErreurDonnees) and extrait:
                # Overpass en panne, mais l'extrait de la région se télécharge :
                # la page relancera le calcul une fois l'extrait installé.
                reponse["extrait_en_cours"] = extrait
            return reponse
        # Dernier contrôle, indépendant de BRouter : un tracé qui passe encore
        # une coupe interdite n'est jamais rendu (audit B10, amélioration 2).
        passages = sur_le_trace(coords, liste)
        traverses = [f for f in passages if f["statut"] == "blocked" or strict]
        if traverses:
            f = traverses[0]
            mot = "bloquant" if f["statut"] == "blocked" else "à vérifier, en mode strict"
            return {"erreur": f"Itinéraire refusé : le tracé passe un franchissement {mot} "
                              f"({f['nature']}, à {km_texte(f['distance_m'])} du départ).",
                    "code": "itineraire_refuse",
                    "valeurs": {"nature": f["nature"], "statut": f["statut"], "distance_m": f["distance_m"]},
                    "traverses": traverses}
        portions = portions_ign(trace) if moteur_utilise == "maison" else []
        reponse = {"itineraire": trace, "zone": zone, "franchissements": liste,
                   "longueur_m": _nombre(trace["properties"], "track-length"),
                   "denivele_m": _nombre(trace["properties"], "filtered ascend"),
                   "sur_le_trace": sorted(passages + entrees_ign(portions), key=lambda f: f["distance_m"]),
                   "portions_ign": portions, "moteur": moteur_utilise, "avertissement": avertissement,
                   "avertissement_detail": detail_avertissement, "strict": strict,
                   "source_officielle": source}
        if comparer:
            self._avancer("comparaison", 0.92)
            try:
                naif = brouter.calculer(self.moteur(), points, profil="hiking-mountain")
                traverses = [f for f in sur_le_trace(naif["geometry"]["coordinates"], liste)
                             if f["statut"] == "blocked"]
                reponse.update(naif=naif, naif_longueur_m=_nombre(naif["properties"], "track-length"),
                               naif_traverse=traverses)
            except brouter.ErreurBRouter:
                reponse["naif"] = None
        reponse["duree_s"] = round(time.monotonic() - debut, 2)
        return reponse

    def _itineraire_paquet(self, points, zone, paquet, dossier, debut) -> dict:
        """Calcule sur l'appareil avec les RD5 et les coupes finales du serveur."""
        moteur = brouter.Serveur(self.installation, segments=dossier, profils=dossier)
        try:
            moteur.demarrer()
            liste = paquet["franchissements"]
            trace = brouter.calculer(moteur.port, points, liste, strict=paquet["strict"])
        finally:
            moteur.arreter()
        coords = trace["geometry"]["coordinates"]
        etendue = (min(c[1] for c in coords), min(c[0] for c in coords),
                   max(c[1] for c in coords), max(c[0] for c in coords))
        if not contient(paquet["couverture"], etendue):
            return {"erreur": "Le tracé sort du paquet de zone."}
        passages = sur_le_trace(coords, liste)
        traverses = [f for f in passages if f["statut"] == "blocked" or paquet["strict"]]
        if traverses:
            return {"erreur": "Itinéraire refusé : franchissement interdit sur le tracé.",
                    "code": "itineraire_refuse", "traverses": traverses}
        portions = portions_ign(trace) if paquet["source"] != "osm" else []
        return {"itineraire": trace, "zone": zone, "franchissements": liste,
                "longueur_m": _nombre(trace["properties"], "track-length"),
                "denivele_m": _nombre(trace["properties"], "filtered ascend"),
                "sur_le_trace": sorted(passages + entrees_ign(portions), key=lambda f: f["distance_m"]),
                "portions_ign": portions, "moteur": "cloud-local", "avertissement": None,
                "avertissement_detail": None, "strict": paquet["strict"],
                "source_officielle": paquet["source"],
                "duree_s": round(time.monotonic() - debut, 2)}

    # ---------------------------------------------------------- dénivelé

    def denivele(self, payload) -> dict:
        """Dénivelé du tracé par gpx2elev, demandé par la page une fois
        l'itinéraire affiché : le calcul de l'itinéraire n'attend pas le
        modèle de terrain."""
        from . import denivele      # numpy et rasterio ne se chargent qu'au premier calcul
        with self._verrou_denivele:
            debut = time.monotonic()
            try:
                resultat = denivele.calculer((payload or {}).get("coordonnees"), self.dossier)
            except (ValueError, denivele.ErreurDenivele) as exc:
                journal.warning("Dénivelé en erreur après %.1f s : %s", time.monotonic() - debut, exc)
                return {"erreur": str(exc)}
            journal.info("Dénivelé calculé en %.1f s : +%s m, %s", time.monotonic() - debut,
                         resultat.get("montee_m"), resultat.get("modele"))
            return resultat

    # ---------------------------------------------------------- calques

    def _prendre_vue(self, cle, vue=None):
        """Le numéro de cette vue du calque, désormais la seule qui se lit, ou
        None si une vue plus récente de la page l'a déjà remplacée. La page
        date ses vues (vue=, en ms) : deux requêtes arrivées dans le désordre
        ne peuvent plus faire passer la plus ancienne pour la vue en cours,
        ce qui laissait la page sans réponse (calque figé, 2026-10-20). Sans
        date (essais), la vue suit la précédente."""
        with self._verrou_vues:
            if self.mode_serveur:
                # Identifiant unique seulement ; aucun client n'interrompt
                # la lecture d'un autre dans _calque().
                self._vues[cle] += 1
                return self._vues[cle]
            if vue is None:
                vue = self._vues[cle] + 1
            elif vue <= self._vues[cle]:
                return None
            self._vues[cle] = vue
            return vue

    def _calque(self, cle, zone, lire, numero):
        """Un calque pour la vue de la page, une vue à la fois : la demande
        d'une nouvelle vue arrête la lecture des tuiles de la précédente, que
        plus personne ne regarde. Le résultat donne les bornes des tuiles
        lues, que la page n'a pas à redemander tant que la vue y reste. Tuile
        après tuile, l'avancement de la vue en cours va dans progression()."""
        if numero is None:
            return {"erreur": "Vue remplacée par une autre.", "code": "vue_remplacee"}
        if zone is None:
            return {"erreur": "Zone invalide."}
        if (zone[2] - zone[0]) * (zone[3] - zone[1]) > ZONE_CALQUE_MAX_DEG2:
            return {"erreur": "Zone trop grande : zoomez davantage."}
        debut = time.monotonic()

        cle_lecture = f"{cle}:{numero}" if self.mode_serveur else cle

        def suivre(faites, total):
            if self.mode_serveur or self._vues[cle] == numero:
                self._lectures[cle_lecture] = {"numero": numero, "faites": faites,
                                               "total": total, "debut": debut}

        try:
            continuer = (lambda: True) if self.mode_serveur else lambda: self._vues[cle] == numero
            resultat = lire(*zone, self.dossier, continuer=continuer, suivi=suivre)
        except franchissements.VueRemplacee:
            return {"erreur": "Vue remplacée par une autre.", "code": "vue_remplacee"}
        except franchissements.ErreurDonnees as exc:
            journal.warning("Calque %s (%s) : échec après %.2f s, zone %s : %s",
                            cle, "serveur" if self.mode_serveur else "local",
                            time.monotonic() - debut, zone, exc)
            return {"erreur": str(exc)}
        finally:
            # Seulement la sienne : une vue plus récente a peut-être déjà la place.
            if self._lectures.get(cle_lecture, {}).get("numero") == numero:
                self._lectures.pop(cle_lecture, None)
        reponse = {"bornes": franchissements.bornes_zone(*zone), **resultat}
        journal.info("Calque %s (%s) : %d octets JSON en %.2f s, zone %s, %d chemins, %d barrières, %d franchissements",
                     cle, "serveur" if self.mode_serveur else "local",
                     len(json.dumps(reponse, ensure_ascii=False).encode("utf-8")),
                     time.monotonic() - debut, zone,
                     len(reponse.get("voies", reponse.get("troncons", []))),
                     len(reponse.get("barrieres", [])), len(reponse.get("franchissements", [])))
        return reponse

    def calque_osm(self, zone, vue=None) -> dict:
        # La vue d'abord : une vue déjà remplacée ne lance rien, pas même un
        # extrait. Le calque des chemins OSM (zoom 14 au moins) est un usage
        # réel de la région : son extrait se télécharge s'il manque.
        numero = self._prendre_vue("osm", vue)
        if numero is None:
            return self._calque("osm", zone, None, None)
        if self.mode_serveur:
            def lire(s, w, n, e, dossier, **options):
                return mailles.calque("osm", (s, w, n, e), dossier, "osm", **options)
            return self._calque("osm", zone, lire, numero)
        extrait = self._extrait_automatique(zone, "calque des chemins OSM") if zone else None
        resultat = self._calque("osm", zone, franchissements.voies_affichables, numero)
        return {**resultat, "extrait_en_cours": extrait} if extrait else resultat

    def calque_officiel(self, source, zone, vue=None) -> dict:
        fournisseur = providers.source(source)
        def lire(*bornes, **options):
            if not fournisseur.disponible(bornes[:4]):
                return {"troncons": []}
            if self.mode_serveur:
                return mailles.calque(source, bornes[:4], bornes[4], "officiel", **options)
            return {"troncons": fournisseur.chemins_pour_calque(
                fournisseur.module.troncons_zone(*bornes, **options))}
        return self._calque(fournisseur.calque, zone, lire,
                           self._prendre_vue(fournisseur.calque, vue))

    def arreter_calques(self, corps=None) -> dict:
        """La page n'affiche plus ces calques (zoom trop faible, calque masqué) :
        leurs lectures en cours s'arrêtent avant la tuile suivante. vue : la
        date de cette demande, qui remplace toute vue plus ancienne."""
        corps = corps or {}
        if self.mode_serveur:
            return {"arretes": []}
        demandes, vue = corps.get("calques"), corps.get("vue")
        cles = [c for c in self._vues if not isinstance(demandes, list) or c in demandes]
        with self._verrou_vues:
            for cle in cles:
                if isinstance(vue, (int, float)) and math.isfinite(vue):
                    self._vues[cle] = max(self._vues[cle], vue)
                else:
                    self._vues[cle] += 1
        return {"arretes": cles}

    # ---------------------------------------------------------- paquet Android

    def preparer_paquet(self, payload) -> dict:
        """Rend un paquet de zone prêt pour BRouter : RD5, profil et coupes.

        Les franchissements sont analysés ici, sur le réseau effectivement
        contenu dans la tuile, et convertis au format final `polylines`.
        Le téléphone n'a pas à relire les tags OSM ni à refaire la fusion.
        """
        if not self.mode_serveur:
            return {"erreur": "Paquets de zone réservés au mode serveur."}
        payload = payload if isinstance(payload, dict) else {}
        if "zone" in payload:
            zone = payload["zone"]
            if (not isinstance(zone, (list, tuple)) or len(zone) != 4
                    or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in zone)
                    or not -90 <= zone[0] < zone[2] <= 90
                    or not -180 <= zone[1] < zone[3] <= 180):
                return {"erreur": "Zone invalide."}
        else:
            try:
                points = valider_points(payload.get("points"))
            except ValueError as exc:
                return {"erreur": str(exc)}
            zone = zone_autour(points)
        source = payload.get("source", "ign")
        if source not in providers.SOURCES:
            return {"erreur": "Source de chemins officiels inconnue."}
        officiel, strict = bool(payload.get("officiel", True)), bool(payload.get("strict", True))
        tuiles = franchissements.tuiles_zone(*zone)
        if len(tuiles) > TUILES_MAX:
            return {"erreur": "Zone trop étendue : découpez le parcours en étapes plus courtes."}
        if officiel and not providers.source(source).disponible(zone):
            return {"erreur": f"Chemins {providers.source(source).nom} indisponibles dans cette zone."}
        segments_attendus = brouter.segments_zone(*zone)
        if not self.installation.installee():
            return {"pret": False, "brouter_en_cours": self._brouter_automatique(
                [] if officiel else segments_attendus)}
        if not officiel:
            manquants = [nom for nom in segments_attendus if not self.installation.segment_present(nom)]
            if manquants:
                return {"pret": False, "brouter_en_cours": self._brouter_automatique(manquants)}
        self._extrait_automatique(zone, "paquet Android")
        try:
            with self._verrou_calcul:
                if officiel:
                    dossier_segments, liste = self.maison.preparer(tuiles, source=source)
                    profil = self.installation.profils_maison / f"{brouter.PROFIL}.brf"
                else:
                    dossier_segments = self.installation.segments
                    liste = franchissements.franchissements_zone(*zone, self.dossier)
                    profil = self.installation.profils / f"{brouter.PROFIL}.brf"
                racine = self.dossier / "paquets"
                racine.mkdir(parents=True, exist_ok=True)
                jeton = secrets.token_hex(16)
                dossier_paquet = racine / jeton
                dossier_paquet.mkdir()
                fichiers, assets = [], []
                sources = [(dossier_segments / f"{nom}.rd5", fichiers) for nom in segments_attendus]
                sources += [(profil, assets), (profil.parent / "lookups.dat", assets)]
                if officiel:
                    chemins = providers.source(source).module.troncons_zone(*zone, self.dossier)
                    chemin_officiel = dossier_paquet / "chemins-officiels.json"
                    atomique.ecrire_json(chemin_officiel, {"troncons": chemins}, indent=None)
                    sources.append((chemin_officiel, assets))
                for source_fichier, destination in sources:
                    if not source_fichier.is_file():
                        raise brouter.ErreurBRouter(f"Fichier BRouter {source_fichier.name} absent du paquet.")
                    cible = dossier_paquet / source_fichier.name
                    if source_fichier != cible:
                        try:
                            os.link(source_fichier, cible)
                        except OSError:
                            shutil.copy2(source_fichier, cible)
                    empreinte = hashlib.sha256()
                    with cible.open("rb") as entree:
                        while bloc := entree.read(1024 * 1024):
                            empreinte.update(bloc)
                    destination.append({"nom": cible.name, "octets": cible.stat().st_size,
                                     "sha256": empreinte.hexdigest(),
                                     "url": f"/api/paquets/{jeton}/{cible.name}"})
                atomique.ecrire_json(dossier_paquet / "manifest.json",
                                    {"fichiers": [f["nom"] for f in fichiers + assets]})
                profil_texte = profil.read_text(encoding="utf-8")
        except (franchissements.ErreurDonnees, brouter.ErreurBRouter, OSError, ValueError) as exc:
            return {"erreur": str(exc)}
        reponse = {"pret": True, "format": 1, "source": source if officiel else "osm",
                "zone": zone, "couverture": franchissements.bornes_zone(*zone),
                "strict": strict, "profil": profil_texte,
                "polylines": brouter.coupes_parametre(liste, strict=strict),
                "franchissements": [{k: f.get(k) for k in
                                      ("cle", "statut", "raison", "nature", "lat", "lon", "osm", "coupes")}
                                     for f in liste if f["statut"] in ("blocked", "uncertain")],
                "segments": fichiers, "assets": assets}
        atomique.ecrire_json(dossier_paquet / "public.json", reponse)
        return reponse

    def lire_paquet(self, zone, source="ign", strict="1", officiel="1") -> dict:
        """Lit le dernier paquet préparé par SSH couvrant toute la zone."""
        if zone is None:
            return {"pret": False, "raison": "zone_invalide"}
        cle = source if officiel not in ("0", "false") else "osm"
        if cle != "osm" and cle not in providers.SOURCES:
            return {"pret": False, "raison": "source_inconnue"}
        est_strict = strict not in ("0", "false")
        racine = self.dossier / "paquets"
        if not racine.is_dir():
            return {"pret": False, "raison": "zone_non_preparee"}
        disponibles = []
        for dossier in racine.iterdir():
            if not dossier.is_dir() or not re.fullmatch(r"[0-9a-f]{32}", dossier.name):
                continue
            paquet = atomique.lire_json(dossier / "public.json", None)
            if (isinstance(paquet, dict) and paquet.get("format") in (1, 2)
                    and paquet.get("source") == cle and paquet.get("strict") is est_strict
                    and isinstance(paquet.get("couverture"), list)
                    and contient(paquet["couverture"], zone, marge_deg=0)):
                disponibles.append((dossier.stat().st_mtime, paquet))
        return max(disponibles, key=lambda item: item[0])[1] if disponibles else {
            "pret": False, "raison": "zone_non_preparee"}

    def mailles_disponibles(self) -> dict:
        """Inventaire public des quarts de degré effectivement publiés."""
        if not self.mode_serveur:
            if self.cloud is None or not self.cloud.etat()["actif"]:
                return {"mailles": [], "erreur": "Serveur de données indisponible."}
            try:
                return self.cloud.demander("mailles-disponibles", "GET")
            except cloud.Indisponible as exc:
                return {"mailles": [], "erreur": str(exc)}
        index = {}
        for source in ("osm", *providers.SOURCES):
            racine = self.dossier / "mailles" / source
            for fichier in racine.glob("*.json.gz") if racine.is_dir() else []:
                match = re.fullmatch(r"(-?\d+)_(-?\d+)\.json\.gz", fichier.name)
                if not match:
                    continue
                cellule = (int(match[1]), int(match[2]))
                info = index.setdefault(cellule, {"maille": list(cellule), "osm": False,
                                                 "sources": [], "itineraires": []})
                if source == "osm":
                    info["osm"] = True
                else:
                    info["sources"].append(source)
        racine = self.dossier / "paquets"
        for dossier in racine.iterdir() if racine.is_dir() else []:
            if not dossier.is_dir() or not re.fullmatch(r"[0-9a-f]{32}", dossier.name):
                continue
            paquet = atomique.lire_json(dossier / "public.json", None)
            if (not isinstance(paquet, dict) or paquet.get("format") != 2
                    or paquet.get("pret") is not True or paquet.get("source") not in providers.SOURCES):
                continue
            for brut in paquet.get("mailles", []):
                if (not isinstance(brut, list) or len(brut) != 2
                        or any(type(v) is not int for v in brut)):
                    continue
                cellule = tuple(brut)
                info = index.setdefault(cellule, {"maille": list(cellule), "osm": False,
                                                 "sources": [], "itineraires": []})
                entree = {"source": paquet["source"], "strict": paquet.get("strict") is True}
                if entree not in info["itineraires"]:
                    info["itineraires"].append(entree)
        return {"pas": 0.25, "mailles": [index[cle] for cle in sorted(index)]}

    def fichier_paquet(self, jeton: str, nom: str) -> Path | None:
        if not re.fullmatch(r"[0-9a-f]{32}", jeton) or not re.fullmatch(
                r"(?:[EW]\d+_[NS]\d+\.rd5|\d{2}_[0-3]_[0-3]\.rd5q|lookups\.dat|hike2gpx\.brf|chemins-officiels\.json)", nom):
            return None
        dossier = self.dossier / "paquets" / jeton
        manifest = atomique.lire_json(dossier / "manifest.json", {})
        if not isinstance(manifest, dict) or nom not in manifest.get("fichiers", []):
            return None
        chemin = dossier / nom
        return chemin if chemin.is_file() else None

    # ---------------------------------------------------------- données OSM hors ligne

    def _extrait_automatique(self, zone, raison: str) -> dict | None:
        """L'extrait OSM du centre de la zone se télécharge de lui-même, en
        tâche de fond, dès que la région sert vraiment (un calcul, le calque
        des chemins OSM) : pas de bouton, décision de Nico du 2026-10-19.
        Survoler la carte ne suffit pas, sans quoi chaque région traversée
        partirait. Rien après un échec récent. Taille et place disque se
        vérifient en tâche de fond (geofabrik._telecharger), et les index ne
        se téléchargent jamais ici (geofabrik.Index) : le calque ou le calcul
        n'attendent aucun serveur, Geofabrik tardant parfois une minute.

        En France, une cascade (Nico, 2026-10-20) : le département d'OSM
        France d'abord, prêt en une quarantaine de secondes, puis sa région de
        Geofabrik, qui prend le relais dès qu'elle est là, ses voies entières
        à la frontière. Rend {"id", "nom"} de l'extrait que la zone attend, ou
        None quand un extrait installé la couvre déjà, relais en préparation
        compris."""
        # Les paquets serveur sont calculés par zone. Leur préparation ne doit
        # pas télécharger et importer toute une région Geofabrik en arrière-plan
        # pour quelques tuiles. Les franchissements utilisent le cache OSM de
        # la zone ou Overpass ; un extrait préinstallé reste utilisable.
        if self.mode_serveur:
            return None
        i, j = franchissements.tuile_du_point((zone[0] + zone[2]) / 2, (zone[1] + zone[3]) / 2)
        installe = geofabrik.extrait_de_tuile(self.dossier, i, j)
        if installe is not None and not installe.get("voies_coupees"):
            return None
        taches = geofabrik.telechargements(self.dossier)

        def plus_petit(regions):
            # Le plus petit extrait qui contient toute la tuile : une région
            # écartée ou en échec récent cède à celle qui la contient.
            return geofabrik.region_de_tuile([r for r in regions if taches.disponible(r["id"])], i, j)

        en_cours = taches.etat()
        occupee = bool(en_cours) and en_cours["etape"] in ("telechargement", "import")
        complete = plus_petit(geofabrik.regions(self.dossier))
        if installe is not None:
            # Un département d'OSM France sert déjà : sa région de Geofabrik se
            # prépare pour prendre le relais, sans faire attendre la page ni
            # prendre la place d'un téléchargement en cours.
            if complete is not None and not occupee and taches.lancer(complete, relais=True):
                journal.info("Extrait OSM %s : téléchargement lancé pour prendre le relais de %s (%s)",
                             complete["id"], installe["id"], raison)
            return None
        # Rien sur le disque : le plus rapide d'abord, le département d'OSM
        # France (sa région en repli, Nico, 2026-10-20 : « départements en
        # priorité, et région en fall back »), puis Geofabrik hors de France
        # ou quand OSM France échoue.
        region = plus_petit(osmfr.regions(self.dossier)) or complete
        if region is None:
            return None
        # La même région déjà en cours : rien à relancer. Une autre : elle cède
        # la place à celle-ci (Telechargements.lancer, le dernier usage l'emporte).
        if occupee and en_cours["id"] == region["id"]:
            return {"id": en_cours["id"], "nom": en_cours["nom"]}
        ensuite = complete if region.get("voies_coupees") else None
        if not taches.lancer(region, ensuite=ensuite):
            return None         # région écartée, ou échec de moins d'une heure
        journal.info("Extrait OSM %s : téléchargement lancé (%s)", region["id"], raison)
        return {"id": region["id"], "nom": region["nom"]}

    def extrait(self, zone) -> dict:
        """Données de la vue : extrait installé et pays. Un téléchargement devenu
        étranger à la vue est abandonné ; cette lecture n'en lance aucun."""
        en_cours_brouter = self._brouter_en_cours
        taches = geofabrik.telechargements(self.dossier)
        if zone is not None:
            i, j = franchissements.tuile_du_point((zone[0] + zone[2]) / 2, (zone[1] + zone[3]) / 2)
            taches.abandonner_hors_tuile(i, j)
        reponse = {"en_cours": taches.etat(),
                   "brouter": {**en_cours_brouter, "segments": list(en_cours_brouter["segments"])}
                   if en_cours_brouter else None}
        if zone is None:
            return reponse
        lat, lon = (zone[0] + zone[2]) / 2, (zone[1] + zone[3]) / 2
        # Le pays de la carte suit son centre, y compris après un déplacement
        # manuel. Les contours de Geofabrik sont déjà lus pour les extraits OSM.
        pays = next((r["id"] for r in geofabrik.regions(self.dossier)
                     if r["id"] in PAYS_CARTES
                     and geofabrik.contient_point(r, lat, lon)), None)
        if pays:
            reponse["pays"] = PAYS_CARTES[pays]
        regions_france = osmfr.regions(self.dossier)
        if regions_france:
            reponse["hors_france"] = not any(geofabrik.contient_point(r, lat, lon) for r in regions_france)
            if not reponse["hors_france"]:
                reponse["pays"] = "fr"
        installe = geofabrik.extrait_de_tuile(self.dossier, i, j)
        if installe:
            return {**reponse, "installe": {"id": installe["id"], "nom": installe["nom"], "date": installe["date"]}}
        return reponse

    def _detail_sources_osm(self, zone, overpass) -> dict:
        """État des deux extraits de la tuile centrale et d'Overpass."""
        detail = {"overpass": "oui" if overpass is True else "non" if overpass is False else "verification"}
        if zone is None:
            return detail
        i, j = franchissements.tuile_du_point((zone[0] + zone[2]) / 2, (zone[1] + zone[3]) / 2)
        locaux = [r for r in osmfr.regions(self.dossier) if r.get("genre") == "departement"]
        local = geofabrik.region_de_tuile(locaux, i, j)
        regional = geofabrik.region_de_tuile(geofabrik.regions(self.dossier), i, j)
        installes = {r["id"] for r in geofabrik.installes(self.dossier)}
        en_cours = geofabrik.telechargements(self.dossier).etat()

        def etat(region):
            if region is None:
                return {"etat": "non_applicable"}
            statut = "disponible" if region["id"] in installes else "absent"
            if statut == "absent" and en_cours and en_cours.get("id") == region["id"] \
                    and en_cours.get("etape") in ("telechargement", "import"):
                statut = en_cours["etape"]
            return {"nom": region["nom"], "etat": statut}

        return {**detail, "local": etat(local), "regional": etat(regional)}

    def disponibilite(self, zone, source="ign", strict=True, officiel=True) -> dict:
        """Prérequis d'un nouveau calcul au centre de la vue ou dans la zone du parcours."""
        if self.mode_serveur:
            if zone is None:
                return {"pret": False, "source": None, "attente": "zone"}
            paquet = self.lire_paquet(zone, source, str(int(bool(strict))), str(int(bool(officiel))))
            if not paquet.get("pret"):
                return {"pret": False, "source": None, "attente": "paquet"}
            if not self.installation.installee():
                return {"pret": False, "source": None, "attente": "moteur"}
            return {"pret": True, "source": "paquet"}
        overpass = franchissements.disponibilite_overpass()
        details = self._detail_sources_osm(zone, overpass)
        if zone is None:
            return {"pret": False, "source": None, "attente": "zone", "details": details}
        if not self.installation.installee():
            return {"pret": False, "source": None, "attente": "moteur", "details": details}
        if any(not self.installation.segment_present(n) for n in brouter.segments_zone(*zone)):
            return {"pret": False, "source": None, "attente": "segments", "details": details}
        tuiles = franchissements.tuiles_zone(*zone)
        if len(tuiles) > TUILES_MAX:
            return {"pret": False, "source": None, "attente": "zone", "details": details}
        extraits = [geofabrik.extrait_de_tuile(self.dossier, i, j) for i, j in tuiles]
        if all(extraits):
            return {"pret": True, "source": "extrait", "nom": extraits[0]["nom"], "details": details}
        if all(extrait is not None or franchissements.tuile_disponible(i, j, self.dossier)
               for (i, j), extrait in zip(tuiles, extraits)):
            return {"pret": True, "source": "cache", "details": details}
        return {"pret": overpass is True, "source": "overpass" if overpass else None,
                "verification": overpass is None, "attente": "osm" if overpass is not True else None,
                "details": details}

    def disponibilite_parcours(self, payload) -> dict:
        """Même contrôle, sur la zone du prochain calcul plutôt que sur la vue."""
        try:
            points = valider_points((payload or {}).get("points"))
        except ValueError:
            return self.disponibilite(None)
        payload = payload or {}
        zone = zone_autour(points)
        ign = bool(payload.get("ign"))
        source = payload.get("source", "ign")
        if ign:
            if source not in providers.SOURCES or not providers.source(source).disponible(zone):
                return {"pret": False, "source": None, "attente": "source"}
        return self.disponibilite(zone, source, bool(payload.get("strict", True)), ign)

    # ---------------------------------------------------------- données téléchargées

    def _caches(self) -> dict:
        """Les dossiers des caches de tuiles : ce que Vider efface, et qui se
        relit de lui-même au besoin."""
        return {"osm": [self.dossier / "overpass", self.dossier / "franchissements"],
                **{p.calque: [self.dossier / p.calque] for p in providers.SOURCES.values()}}

    def _restes(self) -> list:
        """Ce qui traîne au dossier des extraits : l'ancien index de Geofabrik
        (index-v1.json, avant geofabrik-v1.json) et les fichiers de travail
        d'un téléchargement interrompu, quand aucun n'est en cours."""
        racine = geofabrik.dossier_extraits(self.dossier)
        if not racine.is_dir():
            return []
        occupee = geofabrik.telechargements(self.dossier).occupee()
        return [p for p in racine.iterdir() if p.is_file()
                and (p.name == "index-v1.json" or (not occupee and (".part" in p.name or p.suffix == ".pbf")))]

    def donnees(self) -> dict:
        """Ce que hike2gpx a téléchargé, pour la section des réglages (Nico,
        2026-10-20 : « il faudrait une fonction pour vider le cache, dans les
        réglages », « utile aussi pour actualiser les données rapidement »)."""
        def mesure(fichiers) -> dict:
            fichiers = [p for p in fichiers if p.is_file()]
            return {"fichiers": len(fichiers), "octets": sum(p.stat().st_size for p in fichiers)}

        def date(chemin) -> str:
            return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(chemin.stat().st_mtime))

        caches = {nom: mesure([p for d in dossiers if d.is_dir() for p in d.glob("*.json")])
                  for nom, dossiers in self._caches().items()}
        extraits = [{"id": e["id"], "nom": e["nom"], "date": e["date"], "octets": Path(e["base"]).stat().st_size,
                     "provisoire": bool(e.get("voies_coupees"))} for e in geofabrik.installes(self.dossier)]
        segments = sorted(self.installation.segments.glob("*.rd5")) if self.installation.segments.is_dir() else []
        en_cours = geofabrik.telechargements(self.dossier)
        return {**caches, "extraits": extraits,
                "brouter": [{"nom": p.stem, "octets": p.stat().st_size, "date": date(p)} for p in segments],
                "restes": mesure(self._restes()),
                "occupe": {"extrait": en_cours.etat()["id"] if en_cours.occupee() else None,
                           "brouter": bool(self._fil_brouter and self._fil_brouter.is_alive())}}

    def agir_donnees(self, corps) -> dict:
        """Une action de la section : vider un cache, actualiser ou supprimer
        un extrait, actualiser les tuiles BRouter, nettoyer les restes. Rend
        le nouvel état de la section, ou {"erreur"}."""
        corps = corps if isinstance(corps, dict) else {}
        action, cible = corps.get("action"), corps.get("cible")
        taches = geofabrik.telechargements(self.dossier)
        if action == "vider_cache":
            if taches.occupee() or (self._fil_brouter and self._fil_brouter.is_alive()) or self._lectures:
                return {"erreur": "Un téléchargement ou une lecture est en cours. Réessayez après sa fin."}
            if not self._verrou_calcul.acquire(blocking=False):
                return {"erreur": "Un calcul est en cours. Réessayez après sa fin."}
            try:
                if not self._verrou_denivele.acquire(blocking=False):
                    return {"erreur": "Un calcul de dénivelé est en cours. Réessayez après sa fin."}
                try:
                    self.arreter()
                    for dossiers in self._caches().values():
                        for dossier in dossiers:
                            for p in dossier.glob("*.json") if dossier.is_dir() else []:
                                p.unlink(missing_ok=True)
                    for cache_dir in (self.dossier / "gpx2elev", self.installation.maison):
                        if cache_dir.is_dir():
                            shutil.rmtree(cache_dir)
                    for p in self.installation.segments.glob("*.rd5"):
                        p.unlink(missing_ok=True)
                    extraits = geofabrik.dossier_extraits(self.dossier)
                    for p in extraits.iterdir() if extraits.is_dir() else []:
                        if p.is_file():
                            p.unlink()
                    journal.info("Caches locaux OSM, IGN, gpx2elev et BRouter vidés depuis les réglages")
                finally:
                    self._verrou_denivele.release()
            finally:
                self._verrou_calcul.release()
        elif action.startswith("vider_") and action[6:] in self._caches():
            for dossier in self._caches()[action[6:]]:
                for p in dossier.glob("*.json") if dossier.is_dir() else []:
                    p.unlink(missing_ok=True)
            journal.info("Cache %s vidé depuis les réglages", action[6:])
        elif action in ("actualiser_extrait", "supprimer_extrait"):
            extrait = next((e for e in geofabrik.installes(self.dossier) if e["id"] == cible), None)
            if extrait is None:
                return {"erreur": "Extrait inconnu."}
            if taches.occupee() and taches.etat()["id"] == cible:
                return {"erreur": "Cet extrait se télécharge déjà."}
            if action == "supprimer_extrait":
                geofabrik._effacer(Path(extrait["base"]))
                journal.info("Extrait OSM %s supprimé depuis les réglages", cible)
            elif taches.lancer(extrait):
                journal.info("Extrait OSM %s : actualisation demandée depuis les réglages", cible)
            else:
                return {"erreur": "Échec récent : nouvel essai possible dans moins d'une heure."}
        elif action == "actualiser_brouter":
            erreur = self._actualiser_brouter()
            if erreur:
                return {"erreur": erreur}
        elif action == "nettoyer":
            for p in self._restes():
                geofabrik._effacer(p)
            journal.info("Restes du dossier des extraits nettoyés depuis les réglages")
        else:
            return {"erreur": "Action inconnue."}
        return self.donnees()

    def _renouveler_brouter_si_perime(self) -> dict | None:
        """Le délai des réglages s'applique aussi aux tuiles BRouter installées."""
        limite = time.time() - self.reglages()["renouvellement_jours"] * 86400
        maintenant = time.monotonic()
        noms = []
        for chemin in sorted(self.installation.segments.glob("*.rd5")):
            try:
                perimee = chemin.stat().st_mtime < limite
            except FileNotFoundError:  # un vidage du cache peut supprimer la tuile entre-temps
                continue
            echec_recent = maintenant - self._echecs_brouter.get(
                chemin.stem, -self.REESSAI_BROUTER_S) < self.REESSAI_BROUTER_S
            if perimee and not echec_recent:
                noms.append(chemin.stem)
        if not noms or self._actualiser_brouter(noms) is not None:
            return None
        journal.info("Tuiles BRouter périmées : renouvellement en tâche de fond (%s)", ", ".join(noms))
        return {"moteur": False, "segments": noms}

    def _actualiser_brouter(self, noms: list[str] | None = None) -> str | None:
        if noms is None:
            noms = [p.stem for p in sorted(self.installation.segments.glob("*.rd5"))] \
                if self.installation.segments.is_dir() else []
        with self._verrou_brouter:
            if self._fil_brouter and self._fil_brouter.is_alive():
                return "Un téléchargement BRouter est déjà en cours."
            if not noms:
                return "Aucune tuile BRouter à actualiser."
            self._brouter_en_cours = {"moteur": False, "segments": list(noms)}
            self._fil_brouter = threading.Thread(target=self._renouveler_segments, args=(noms,), daemon=True,
                                                 name="brouter-actualiser")
            self._fil_brouter.start()
        return None

    def _renouveler_segments(self, noms: list) -> None:
        """Les tuiles se téléchargent à côté des anciennes, qui servent pendant
        ce temps ; la bascule se fait d'un coup, moteurs arrêtés (sous Windows,
        un RD5 ouvert ne se remplace pas). Ils repartent au calcul suivant."""
        attente = self.installation.segments / "nouvelles"
        try:
            pretes = []
            for nom in noms:
                try:
                    self.installation.telecharger_segment(nom, vers=attente)
                    pretes.append(nom)
                except (brouter.ErreurBRouter, ValueError) as exc:
                    self._echecs_brouter[nom] = time.monotonic()
                    journal.warning("Tuile BRouter %s non actualisée : %s", nom, exc)
                finally:
                    self._brouter_en_cours["segments"].remove(nom)
            if pretes:
                with self._verrou_calcul:
                    self.arreter()
                    for nom in pretes:
                        atomique.remplacer(attente / f"{nom}.rd5", self.installation.segments / f"{nom}.rd5")
                journal.info("Tuiles BRouter actualisées : %s", ", ".join(pretes))
        except OSError as exc:
            for nom in noms:
                self._echecs_brouter[nom] = time.monotonic()
            journal.warning("Tuiles BRouter non actualisées : %s", exc)
        finally:
            shutil.rmtree(attente, ignore_errors=True)
            self._brouter_en_cours = {}

    def routes(self):
        if self.mode_serveur:
            # API pour les applications : lecture de données préparées et
            # calcul de secours. Aucun réglage, journal ni effacement de cache.
            return ({"init": self.etat, "etat": self.etat,
                     "paquet-zone": self.lire_paquet,
                     "mailles-disponibles": self.mailles_disponibles,
                     "osm": self.calque_osm,
                     **{p.calque: (lambda zone, vue=None, cle=cle: self.calque_officiel(cle, zone, vue))
                        for cle, p in providers.SOURCES.items()},
                     "progression": self.progression, "disponibilite": self.disponibilite},
                    {"itineraire": self.itineraire,
                     "denivele": self.denivele, "communes": communes.chercher,
                     "disponibilite": self.disponibilite_parcours})
        # /api/langue : le choix FR / EN du commun, gardé dans les préférences.
        get_langue, post_langue = langue_commune.routes(self.lire_langue, self.ecrire_langue)
        get = {"init": self.etat, "etat": self.etat, "reglages": self.reglages,
               "mailles-disponibles": self.mailles_disponibles,
               "osm": self.calque_osm,
               **{p.calque: (lambda zone, vue=None, cle=cle: self.calque_officiel(cle, zone, vue))
                  for cle, p in providers.SOURCES.items()},
               "extrait": self.extrait,
               "progression": self.progression, "donnees": self.donnees,
               "disponibilite": self.disponibilite,
               **get_langue, **({} if self.mode_serveur else
                               {"journal": self.lire_journal, "serveur": self.etat_serveur})}
        post = {"itineraire": self.itineraire, "disponibilite": self.disponibilite_parcours,
                "reglages": self.enregistrer_reglages,
                "moteur": self.installer_moteur, "denivele": self.denivele,
                "communes": communes.chercher, "arreter_calques": self.arreter_calques,
                "donnees": self.agir_donnees, **post_langue,
                "ouvrir_journaux": self.ouvrir_journaux, "serveur": self.enregistrer_serveur}
        if self.cloud:
            for route in cloud.ROUTES_CLOUD:
                if route in get:
                    locale = get[route]
                    def avec_repli_get(*args, _route=route, _locale=locale):
                        try:
                            resultat = self.cloud.calque(_route, args)
                            if not resultat.get("erreur"):
                                return resultat
                            journal.info("Calque %s : absent du serveur, repli sur les données locales : %s",
                                         _route, resultat["erreur"])
                        except cloud.Indisponible as exc:
                            if self.cloud.etat(force=True)["actif"]:
                                journal.warning("Calque %s : cache cloud indisponible, serveur joignable : %s",
                                                _route, exc)
                                return {"erreur": str(exc), "origine_calque": "cloud"}
                            journal.info("Calque %s : repli sur les données locales : %s", _route, exc)
                        return {**_locale(*args), "origine_calque": "local"}
                    get[route] = avec_repli_get
                if route in post:
                    locale = post[route]
                    def avec_repli_post(payload, _route=route, _locale=locale):
                        if self.cloud.etat()["actif"]:
                            try:
                                resultat = self.cloud.demander(_route, "POST", payload=payload)
                                if not (_route == "itineraire" and resultat.get("code") == "zone_non_preparee"):
                                    return resultat
                                journal.info("Itinéraire : paquet cloud absent, repli sur le calcul local")
                            except cloud.Indisponible:
                                pass
                        return _locale(payload)
                    post[route] = avec_repli_post
            # Le voyant de disponibilité doit interroger le même serveur que
            # le calcul cloud. Il indique donc la présence du paquet préparé,
            # plutôt que les extraits OSM et segments du poste local.
            disponibilite_get, disponibilite_post = get["disponibilite"], post["disponibilite"]

            def disponibilite_cloud_get(*args):
                if self.cloud.etat()["actif"]:
                    try:
                        resultat = self.cloud.demander("disponibilite", "GET", args=args)
                        if resultat.get("pret") or resultat.get("attente") != "paquet":
                            return resultat
                        journal.info("Disponibilité : paquet cloud absent, vérification locale")
                    except cloud.Indisponible:
                        pass
                return disponibilite_get(*args)

            def disponibilite_cloud_post(payload):
                if self.cloud.etat()["actif"]:
                    try:
                        resultat = self.cloud.demander("disponibilite", "POST", payload=payload)
                        if resultat.get("pret") or resultat.get("attente") != "paquet":
                            return resultat
                        journal.info("Disponibilité : paquet cloud absent, vérification locale")
                    except cloud.Indisponible:
                        pass
                return disponibilite_post(payload)

            get["disponibilite"] = disponibilite_cloud_get
            post["disponibilite"] = disponibilite_cloud_post
        return get, post

    def ouvrir_journaux(self, corps=None) -> dict:
        """Ouvre uniquement le dossier des journaux de cette installation."""
        return {"dossier": str(journaux.ouvrir(self.dossier))}
