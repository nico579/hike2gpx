"""Une instance de hike2gpx : réglages, moteur BRouter, et les routes /api/*
de la page.

Un itinéraire se calcule en quatre temps : la zone des points, élargie ;
les franchissements de cette zone ; BRouter avec leurs coupes ; puis, si le
tracé sort de la zone examinée, la zone s'agrandit et le calcul recommence,
pour qu'aucun détour ne passe par une barrière jamais vérifiée.
"""
from __future__ import annotations

import logging
import math
import os
import re
import shutil
import threading
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from nico579_commons import atomique
from nico579_commons import langue as langue_commune

from . import (__version__, brouter, communes, depot, fabrication, fonds, franchissements, geofabrik, hors_ligne,
               journaux, lot, maison, osmfr, partage, providers)

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
    return [{"debut_m": p["debut_m"], "longueur_m": round(p["longueur_m"]), "source": p["source"],
             "coords": [[c[1], c[0]] for c in coords[p["debut_rang"]:p["fin_rang"] + 1]]} for p in portions]


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
    def __init__(self, dossier: Path):
        self.dossier = Path(dossier)
        self.installation = brouter.Installation(self.dossier)
        self.maison = maison.TuilesMaison(self.installation, self.dossier)
        self.hors_ligne = hors_ligne.HorsLigne(self.dossier)
        # Le dépôt des lots du serveur ; HIKE2GPX_DEPOT en désigne un autre (un
        # PC qui sert ses lots, un essai).
        self.depot_lots = os.environ.get("HIKE2GPX_DEPOT", depot.DEPOT)
        # Fabrication d'un lot OSM en tâche de fond (fabrication.py), une à la fois.
        self._verrou_lot = threading.Lock()
        self._lot = {"actif": False}
        self._fil_lot = None
        # Lots du serveur téléchargés d'eux-mêmes (_lot_automatique) : case ou
        # "catalogue" -> instant du dernier échec ; et les cases retirées à la
        # main pendant la séance, qui ne reviennent pas toutes seules.
        self._echecs_lots = {}
        self._lots_retires = set()
        # Le partage au téléphone (partage.py), fermé tant qu'on ne l'ouvre pas.
        self.partage = partage.Partage(self.hors_ligne)
        self.preferences = self.dossier / "preferences.json"
        self.serveur = None
        self.serveur_maison = None
        self.serveur_lot_osm = None
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
        return {"app": "hike2gpx", "version": __version__, "dossier": str(self.dossier),
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
        return self._moteur("serveur_maison", segments, self.installation.profils_maison)

    def moteur_lot_osm(self) -> int:
        """Serveur BRouter sur les RD5 officielles des lots OSM, profils standard."""
        return self._moteur("serveur_lot_osm", self.hors_ligne.segments_osm, None)

    def _moteur(self, attribut, segments, profils) -> int:
        with self._verrou_moteur:
            s = getattr(self, attribut)
            if s is None or s.segments != segments or s.processus is None or s.processus.poll() is not None:
                if s is not None:
                    s.arreter()
                s = brouter.Serveur(self.installation, segments=segments, profils=profils)
                s.demarrer()
                setattr(self, attribut, s)
            return s.port

    def arreter(self) -> None:
        self.partage.fermer()
        self._arreter_moteurs()

    def _arreter_moteurs(self) -> None:
        """Les moteurs BRouter arrêtés ; ils repartent d'eux-mêmes au prochain calcul."""
        with self._verrou_moteur:
            for serveur in (self.serveur, self.serveur_maison, self.serveur_lot_osm):
                if serveur is not None:
                    serveur.arreter()
            self.serveur = self.serveur_maison = self.serveur_lot_osm = None

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
        calques = {cle: {"faites": l["faites"], "total": l["total"], "duree_s": round(maintenant - l["debut"], 1)}
                   for cle, l in list(self._lectures.items())}
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
                reponse = self._avec_lot_automatique(self._itineraire(payload))
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
        # Un calcul est un usage réel de la région : son extrait OSM part en
        # tâche de fond s'il manque, Overpass servant en attendant ; de même le
        # moteur et les tuiles BRouter, sans lesquels il n'y a pas de calcul.
        # Un lot installé qui couvre la zone suffit : rien à télécharger. Le lot
        # que publie le serveur pour la zone se télécharge de lui-même, plus
        # vite que la volée (Overpass, tuiles BRouter) : le calcul l'attend,
        # la page le relance à son arrivée (essai de Nico du 2026-10-28, les
        # deux se chevauchaient).
        lot_attendu = self._lot_automatique(zone, "calcul d'itinéraire")
        if lot_attendu and not self.hors_ligne.lot_couvrant(zone):
            return {"erreur": "Le lot hors ligne de la zone se télécharge : le calcul reprendra à son arrivée.",
                    "code": "attente_lot"}
        couvert = lot_attendu or bool(self.hors_ligne.lot_couvrant(zone))
        extrait = None if couvert else self._extrait_automatique(zone, "calcul d'itinéraire")
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
                # Règle unique : un lot qui couvre la zone sert seul (hors_ligne.py),
                # sans réseau ni fabrication ; sinon, le calcul à la volée.
                lot_local = self.hors_ligne.lot_couvrant(zone)
                manquants = [] if lot_local else [n for n in brouter.segments_zone(*zone)
                                                  if not self.installation.segment_present(n)]
                if manquants:
                    return {"erreur": "Données BRouter absentes pour cette zone.",
                            "segments_manquants": manquants, "brouter_en_cours": self._brouter_automatique(manquants)}
                trace, moteur_utilise = None, "standard"
                if lot_local:
                    liste = self.hors_ligne.franchissements(lot_local, zone)
                    self._avancer("itineraire", 0.82, passe=passe)
                    if lot_local.get("type") == "osm":
                        # RD5 officielle : table de tags et profil standards de BRouter.
                        trace = brouter.calculer(self.moteur_lot_osm(), points, liste, strict=strict)
                        if ign:
                            nom_source = providers.source(source).nom
                            detail_avertissement = f"lot {lot_local['case']} sans chemins officiels"
                            avertissement = f"Chemins {nom_source} indisponibles, calcul sur OSM seul : "                                             f"{detail_avertissement}"
                    else:
                        # RD5 enrichie : la coche autorise ou interdit ses chemins
                        # officiels par le profil, sans autre lot.
                        trace = brouter.calculer(self.moteur_maison(self.hors_ligne.segments), points, liste,
                                                 strict=strict, officiels=ign)
                    moteur_utilise = "lot"
                elif ign:
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
        portions = portions_ign(trace) if moteur_utilise in ("maison", "lot") else []
        reponse = {"itineraire": trace, "zone": zone, "franchissements": liste,
                   "longueur_m": _nombre(trace["properties"], "track-length"),
                   "denivele_m": _nombre(trace["properties"], "filtered ascend"),
                   "sur_le_trace": sorted(passages + entrees_ign(portions), key=lambda f: f["distance_m"]),
                   "portions_ign": portions, "moteur": moteur_utilise, "avertissement": avertissement,
                   "avertissement_detail": detail_avertissement, "strict": strict,
                   "source_officielle": source, "lot": self._lot_resume(lot_local) if lot_local else None}
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

        def suivre(faites, total):
            if self._vues[cle] == numero:
                self._lectures[cle] = {"numero": numero, "faites": faites, "total": total, "debut": debut}

        try:
            resultat = lire(*zone, self.dossier, continuer=lambda: self._vues[cle] == numero, suivi=suivre)
        except franchissements.VueRemplacee:
            return {"erreur": "Vue remplacée par une autre.", "code": "vue_remplacee"}
        except franchissements.ErreurDonnees as exc:
            return {"erreur": str(exc)}
        finally:
            # Seulement la sienne : une vue plus récente a peut-être déjà la place.
            if self._lectures.get(cle, {}).get("numero") == numero:
                self._lectures.pop(cle, None)
        return {**resultat, "bornes": franchissements.bornes_zone(*zone)}

    def calque_osm(self, zone, vue=None) -> dict:
        # La vue d'abord : une vue déjà remplacée ne lance rien, pas même un
        # extrait. Le calque des chemins OSM (zoom 14 au moins) est un usage
        # réel de la région : son extrait se télécharge s'il manque.
        numero = self._prendre_vue("osm", vue)
        if numero is None:
            return self._calque("osm", zone, None, None)
        # Le lot du serveur pour la vue se télécharge de lui-même, comme pour
        # un calcul ; un lot installé qui couvre la vue la montre seul, sans
        # réseau ni extrait.
        lot_attendu = self._lot_automatique(zone, "calque des chemins OSM") if zone else False
        lire_lot = self._lecture_du_lot(zone, "osm")
        if lire_lot:
            return self._avec_lot_automatique(self._calque("osm", zone, lire_lot, numero))
        if lot_attendu:                 # rien à la volée : la page relit le calque à l'arrivée du lot
            return self._avec_lot_automatique({"attente_lot": True})
        extrait = self._extrait_automatique(zone, "calque des chemins OSM") if zone and not lot_attendu else None
        resultat = self._avec_lot_automatique(self._calque("osm", zone, franchissements.voies_affichables, numero))
        return {**resultat, "extrait_en_cours": extrait} if extrait else resultat

    def calque_officiel(self, source, zone, vue=None) -> dict:
        fournisseur = providers.source(source)
        def lire(*bornes, **options):
            if not fournisseur.disponible(bornes):
                return {"troncons": []}
            return {"troncons": fournisseur.module.troncons_zone(*bornes, **options)}
        numero = self._prendre_vue(fournisseur.calque, vue)
        lot_attendu = self._lot_automatique(zone, f"calque {fournisseur.nom}") if numero is not None and zone else False
        lire_lot = self._lecture_du_lot(zone, fournisseur.calque)
        if lot_attendu and not lire_lot:
            return self._avec_lot_automatique({"attente_lot": True})
        return self._avec_lot_automatique(self._calque(fournisseur.calque, zone, lire_lot or lire, numero))

    def _lecture_du_lot(self, zone, calque):
        """Lecture du calque dans un lot installé qui couvre la zone, ou None.
        Le lot lit toutes les tuiles de 0,05° de la vue, celles dont _calque
        renvoie les bornes : la page ne redemande rien tant qu'elle y reste."""
        manifeste = self.hors_ligne.lot_du_calque(franchissements.bornes_zone(*zone), calque) if zone else None
        if manifeste is None:
            return None
        return lambda *bornes, **options: self.hors_ligne.calque(
            manifeste, calque, franchissements.bornes_zone(*bornes[:4]))

    def arreter_calques(self, corps=None) -> dict:
        """La page n'affiche plus ces calques (zoom trop faible, calque masqué) :
        leurs lectures en cours s'arrêtent avant la tuile suivante. vue : la
        date de cette demande, qui remplace toute vue plus ancienne."""
        corps = corps or {}
        demandes, vue = corps.get("calques"), corps.get("vue")
        cles = [c for c in self._vues if not isinstance(demandes, list) or c in demandes]
        with self._verrou_vues:
            for cle in cles:
                if isinstance(vue, (int, float)) and math.isfinite(vue):
                    self._vues[cle] = max(self._vues[cle], vue)
                else:
                    self._vues[cle] += 1
        return {"arretes": cles}

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

    def disponibilite(self, zone) -> dict:
        """Prérequis d'un nouveau calcul au centre de la vue ou dans la zone du parcours."""
        overpass = franchissements.disponibilite_overpass()
        details = self._detail_sources_osm(zone, overpass)
        if zone is None:
            return {"pret": False, "source": None, "attente": "zone", "details": details}
        # Un lot installé qui couvre la zone suffit au calcul, RD5 comprise
        # (règle unique) : l'indicateur le dit au lieu de compter les extraits
        # et les tuiles BRouter (capture de Nico du 2026-10-28).
        lot_local = self.hors_ligne.lot_couvrant(zone)
        if lot_local:
            details["lot"] = {"nom": lot_local["case"], "etat": "disponible"}
        elif self._lot.get("actif") and self._lot.get("case") in brouter.segments_zone(*zone):
            details["lot"] = {"nom": self._lot["case"], "etat": "telechargement"}
        if not self.installation.installee():
            return {"pret": False, "source": None, "attente": "moteur", "details": details}
        if lot_local:
            return {"pret": True, "source": "lot", "nom": lot_local["case"], "details": details}
        if any(not self.installation.segment_present(n) for n in brouter.segments_zone(*zone)):
            return {"pret": False, "source": None, "attente": "segments", "details": details}
        tuiles = franchissements.tuiles_zone(*zone)
        if len(tuiles) > TUILES_MAX:
            return {"pret": False, "source": None, "attente": "zone", "details": details}
        extraits = [geofabrik.extraits_de_tuile(self.dossier, i, j) for i, j in tuiles]
        if all(extraits):
            noms = list(dict.fromkeys(e["nom"] for liste in extraits for e in liste))
            return {"pret": True, "source": "extrait", "nom": ", ".join(noms), "details": details}
        if all(extrait or franchissements.tuile_disponible(i, j, self.dossier)
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
        zone = zone_autour(points)
        resultat = self.disponibilite(zone)
        if (payload or {}).get("ign"):
            source = (payload or {}).get("source")
            if source not in providers.SOURCES or not providers.source(source).disponible(zone):
                return {**resultat, "pret": False, "source": None, "attente": "source"}
        return resultat

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
            if taches.occupee() or (self._fil_brouter and self._fil_brouter.is_alive()) or self._lectures \
                    or (self._fil_lot and self._fil_lot.is_alive()):
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
                    # Les lots et les fonds aussi, pour repartir de zéro
                    # (décision de Nico du 2026-10-28) : ceux du serveur
                    # se retéléchargent vite.
                    self.hors_ligne.vider()
                    journal.info("Caches locaux OSM, IGN, gpx2elev et BRouter, lots et fonds hors ligne "
                                 "vidés depuis les réglages")
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
        # /api/langue : le choix FR / EN du commun, gardé dans les préférences.
        get_langue, post_langue = langue_commune.routes(self.lire_langue, self.ecrire_langue)
        get = {"init": self.etat, "etat": self.etat, "reglages": self.reglages,
               "osm": self.calque_osm,
               **{p.calque: (lambda zone, vue=None, cle=cle: self.calque_officiel(cle, zone, vue))
                  for cle, p in providers.SOURCES.items()},
               "extrait": self.extrait,
               "progression": self.progression, "journal": self.lire_journal, "donnees": self.donnees,
               "disponibilite": self.disponibilite, "hors_ligne": self.lots_hors_ligne,
               "lot_en_cours": self.lot_en_cours, "catalogue_lots": self.catalogue_lots,
               "partage": self.partage.etat,
               **get_langue}
        post = {"itineraire": self.itineraire, "disponibilite": self.disponibilite_parcours,
                "reglages": self.enregistrer_reglages,
                "moteur": self.installer_moteur, "denivele": self.denivele,
                "communes": communes.chercher, "arreter_calques": self.arreter_calques,
                "donnees": self.agir_donnees, "ouvrir_journaux": self.ouvrir_journaux,
                "installer_lot": self.installer_lot, "preparer_lot": self.preparer_lot,
                "supprimer_case": self.supprimer_case,
                "arreter_lot": self.arreter_lot, "telecharger_lot": self.telecharger_lot,
                "preparer_fond": self.preparer_fond, "partage": self.partager, **post_langue}
        return get, post

    CATALOGUE_TTL_S = 600.0

    def _lire_catalogue(self) -> dict:
        """Le catalogue du dépôt, relu au plus toutes les CATALOGUE_TTL_S ;
        depot.ErreurDepot s'il est injoignable."""
        cache = getattr(self, "_catalogue", None)
        if cache is None or time.monotonic() - cache[0] > self.CATALOGUE_TTL_S:
            cache = (time.monotonic(), depot.lire_catalogue(self.depot_lots))
            self._catalogue = cache
        return cache[1]

    @staticmethod
    def _etat_au_catalogue(entree: dict, local: dict | None) -> str:
        """absent, a_jour, ou ancien : le serveur ne publie que vers l'avant, un
        lot dont les sources diffèrent de celles du catalogue est plus ancien."""
        if local is None:
            return "absent"
        return "a_jour" if local.get("sources") == entree.get("sources") else "ancien"

    def catalogue_lots(self) -> dict:
        """Les lots que publie le dépôt du serveur (depot.py), avec pour chacun
        son état sur ce PC : absent, installé et à jour, ou plus ancien."""
        try:
            catalogue = self._lire_catalogue()
        except depot.ErreurDepot as exc:
            journal.warning("Dépôt des lots : %s", exc)
            return {"erreur": str(exc), "lots": []}
        installes = {m["case"]: m for m in self.hors_ligne.lots()}
        lots = [{k: entree.get(k) for k in ("case", "type", "fournisseurs", "zone", "sources", "octets")}
                | {"etat": self._etat_au_catalogue(entree, installes.get(entree["case"]))}
                for entree in catalogue["lots"]]
        return {"lots": lots, "depot": self.depot_lots}

    # Après un échec (catalogue injoignable, réseau, place disque, arrêt par
    # la page), pas de nouvel essai automatique avant une heure, comme les
    # extraits OSM.
    REESSAI_LOT_S = 3600.0

    def _echec_recent(self, cle: str) -> bool:
        return time.monotonic() - self._echecs_lots.get(cle, -self.REESSAI_LOT_S) < self.REESSAI_LOT_S

    def _lots_a_telecharger(self, catalogue: dict, zone) -> list:
        """Les entrées du catalogue à télécharger pour la zone : le lot de
        chaque case qu'elle touche, quand il manque ici, ou qu'il vient du dépôt
        et que le catalogue en a un plus récent. Un lot préparé sur cet
        ordinateur n'est jamais remplacé tout seul (la page propose sa mise à
        jour), ni une case retirée à la main pendant la séance."""
        cases = set(brouter.segments_zone(*zone))
        installes = {m["case"]: m for m in self.hors_ligne.lots()}
        a_faire = []
        for entree in catalogue["lots"]:
            case = entree["case"]
            couverture = entree.get("zone") if entree.get("type") == "osm" else entree.get("emprise_enrichie")
            if case not in cases or case in self._lots_retires or self._echec_recent(case) \
                    or not couverture or not hors_ligne.touche(couverture, zone):
                continue
            etat = self._etat_au_catalogue(entree, installes.get(case))
            if etat == "absent" or (etat == "ancien" and self.hors_ligne.origine(case) is not None):
                a_faire.append(entree)
        return a_faire

    def _lot_automatique(self, zone, raison: str) -> bool:
        """Le lot que publie le serveur pour une case qui sert vraiment (un
        calcul, un calque, pas un survol de la carte) se télécharge de lui-même
        en tâche de fond, sur le modèle des extraits OSM ; il prend le relais
        dès qu'il est installé (décision de Nico du 2026-10-28). Un seul lot à
        la fois. La décision se prend sur le dernier catalogue lu ; jamais lu,
        il se lit ici une fois (une fraction de seconde), sans quoi la première
        vue de la page lancerait l'extrait OSM avant de savoir qu'un lot existe
        (essai de Nico du 2026-10-28). Un échec vaut pour une heure. Vrai si un
        lot automatique est en route pour la zone : le mode à la volée
        l'attend alors sans télécharger d'extrait."""
        if getattr(self, "_catalogue", None) is None and not self._echec_recent("catalogue"):
            try:
                self._lire_catalogue()
            except depot.ErreurDepot as exc:
                self._echecs_lots["catalogue"] = time.monotonic()
                journal.warning("Lots du serveur : %s ; nouvel essai automatique dans une heure", exc)
        with self._verrou_lot:
            if self._fil_lot is not None and self._fil_lot.is_alive():
                return bool(self._lot.get("auto"))
            cache = getattr(self, "_catalogue", None)
            a_faire = self._lots_a_telecharger(cache[1], zone) if cache else []
            if not a_faire:
                return False
            self._lot = {"actif": True, "auto": True, "case": a_faire[0]["case"], "zone": a_faire[0].get("zone"),
                         "etape": "telechargement", "faites": 0, "total": a_faire[0].get("octets", 0),
                         "debut": time.time(), "arreter": False}
            self._fil_lot = threading.Thread(target=self._telecharger_lots_auto, args=(a_faire, raison),
                                             daemon=True, name="lot-automatique")
            self._fil_lot.start()
            return True

    def _telecharger_lots_auto(self, a_faire: list, raison: str) -> None:
        for i, entree in enumerate(a_faire):
            case = entree["case"]
            if self._lot.get("arreter"):
                break
            if i:
                self._lot = {"actif": True, "auto": True, "case": case, "zone": entree.get("zone"),
                             "etape": "telechargement", "faites": 0, "total": entree.get("octets", 0),
                             "debut": time.time(), "arreter": False}
            journal.info("Lot %s : téléchargement automatique depuis le serveur (%s)", case, raison)
            self._telecharger_lot(entree)
            if "erreur" in self._lot:
                self._echecs_lots[case] = time.monotonic()

    def _avec_lot_automatique(self, reponse: dict) -> dict:
        """La réponse d'un calcul ou d'un calque, avec l'état du lot qui se
        télécharge tout seul, pour que la page en suive l'avancement."""
        if self._lot.get("actif") and self._lot.get("auto"):
            return {**reponse, "lot_en_cours": self.lot_en_cours()}
        return reponse

    def supprimer_case(self, corps) -> dict:
        """Retire de l'ordinateur le lot et les fonds d'une case, depuis sa bulle sur la
        carte. corps : {"case": "E5_N40"}. Rend {"octets"} libérés, ou {"erreur"}."""
        case, _, erreur = self._case_et_zone(corps)
        if erreur:
            return {"erreur": erreur}
        if self._fil_lot and self._fil_lot.is_alive():
            return {"erreur": "Un lot se prépare. Réessayez après sa fin."}
        if not self._verrou_calcul.acquire(blocking=False):
            return {"erreur": "Un calcul est en cours. Réessayez après sa fin."}
        try:
            self._arreter_moteurs()       # un moteur garde la RD5 ouverte : Windows refuserait de l'effacer
            octets = self.hors_ligne.supprimer(case)
            self._lots_retires.add(case)    # elle ne revient pas toute seule pendant la séance
        finally:
            self._verrou_calcul.release()
        journal.info("Case %s retirée de l'ordinateur depuis la carte : %d octets libérés", case, octets)
        return {"octets": octets}

    def telecharger_lot(self, corps) -> dict:
        """Télécharge en tâche de fond le lot d'une case depuis le dépôt du
        serveur, vérifié fichier par fichier, puis l'installe."""
        case = (corps or {}).get("case")
        cache = getattr(self, "_catalogue", None)
        entree = next((e for e in cache[1]["lots"] if e["case"] == case), None) if cache else None
        if entree is None:
            return {"erreur": "Ce lot n'est pas au catalogue du dépôt."}
        with self._verrou_lot:
            if self._fil_lot is not None and self._fil_lot.is_alive():
                return {"erreur": "Un lot se prépare déjà.", "lot_en_cours": dict(self._lot)}
            self._lot = {"actif": True, "case": case, "zone": entree.get("zone"), "etape": "telechargement",
                         "faites": 0, "total": entree.get("octets", 0), "debut": time.time(), "arreter": False}
            self._fil_lot = threading.Thread(target=self._telecharger_lot, args=(entree,), daemon=True,
                                             name=f"lot-{case}")
            self._fil_lot.start()
        return {"lot_en_cours": self.lot_en_cours()}

    def _telecharger_lot(self, entree) -> None:
        case, debut = entree["case"], time.monotonic()
        travail = self.hors_ligne.racine / f".telechargement-{case}"
        try:
            depot.telecharger(entree, self.depot_lots, travail,
                              suivi=lambda faites, total: self._lot.update(faites=faites, total=total),
                              continuer=lambda: not self._lot.get("arreter"))
            self._lot["etape"] = "installation"
            # Une RD5 ouverte par BRouter ne se remplace pas sous Windows : les
            # moteurs s'arrêtent entre deux calculs et repartent au suivant.
            with self._verrou_calcul:
                self._arreter_moteurs()
                self.hors_ligne.installer(travail, origine={"depot": self.depot_lots})
        except depot.Abandon:
            journal.info("Lot %s : téléchargement arrêté après %.0f s", case, time.monotonic() - debut)
            self._lot.update(actif=False, erreur="Téléchargement arrêté.")
        except Exception as exc:          # réseau, empreinte, disque : la page l'affiche
            journal.exception("Lot %s : téléchargement en erreur après %.0f s", case, time.monotonic() - debut)
            self._lot.update(actif=False, erreur=str(exc))
        else:
            journal.info("Lot %s : téléchargé et installé en %.0f s", case, time.monotonic() - debut)
            self._lot.update(actif=False, etape="fini")
        finally:
            # Un téléchargement arrêté ou coupé repartira de zéro : rien de
            # partiel ne reste dans le dossier des lots.
            fabrication.nettoyer(travail)

    def preparer_lot(self, corps) -> dict:
        """Fabrique en tâche de fond le lot d'une case (fabrication.py), puis
        l'installe. corps : {"case": "E5_N40", "zone": [sud, ouest, nord, est]}
        (zone facultative, dans la case). Tout fournisseur national qui touche
        la zone entre au lot, plusieurs pour une case frontalière."""
        case, zone, erreur = self._case_et_zone(corps)
        if erreur:
            return {"erreur": erreur}
        return self._lancer_tache(self._fabriquer_lot, case, zone, "debut")

    @staticmethod
    def _case_et_zone(corps) -> tuple:
        """(case, zone, erreur) d'une demande de préparation ; zone facultative."""
        corps = corps or {}
        case = corps.get("case")
        if not isinstance(case, str) or not re.fullmatch(r"[EW]\d{1,3}_[NS]\d{1,2}", case):
            return None, None, "Case BRouter invalide."
        zone = corps.get("zone")
        if zone is not None and not (isinstance(zone, list) and len(zone) == 4
                                     and all(isinstance(v, (int, float)) for v in zone)):
            return None, None, "Zone invalide."
        return case, zone, None

    def _lancer_tache(self, cible, case, zone, etape) -> dict:
        """Une préparation hors ligne en tâche de fond, une seule à la fois :
        un lot ou un fond de carte, suivis par la même note de la page."""
        with self._verrou_lot:
            if self._fil_lot is not None and self._fil_lot.is_alive():
                return {"erreur": "Un lot se prépare déjà.", "lot_en_cours": dict(self._lot)}
            self._lot = {"actif": True, "case": case, "zone": zone, "etape": etape,
                         "faites": 0, "total": 0, "debut": time.time(), "arreter": False}
            self._fil_lot = threading.Thread(target=cible, args=(case, zone), daemon=True, name=f"lot-{case}")
            self._fil_lot.start()
        return {"lot_en_cours": self.lot_en_cours()}

    def preparer_fond(self, corps) -> dict:
        """Télécharge en tâche de fond le fond de carte d'une case ou d'une vue
        (fonds.py) : le SCAN 25 avec la clé IGN, le Plan IGN sans. corps comme
        pour preparer_lot. Le fond reste sur ce PC, jamais publié."""
        case, zone, erreur = self._case_et_zone(corps)
        if erreur:
            return {"erreur": erreur}
        return self._lancer_tache(self._fabriquer_fond, case, zone, "fond")

    def _fabriquer_fond(self, case, zone) -> None:
        cle = self.reglages()["cle_ign"]
        source = fonds.source_pour(cle)
        if zone:
            # Une vue s'arrête aux bords de sa case, comme un lot.
            s, o, n, e = lot.boite_case(case)
            zone = (max(zone[0], s), max(zone[1], o), min(zone[2], n), min(zone[3], e))
            zooms, nom = fonds.zooms_vue(zone), fonds.nom_fond(case, source, zone)
        else:
            zone, zooms, nom = lot.boite_case(case), fonds.ZOOMS_CASE, fonds.nom_fond(case, source)
        debut = time.monotonic()
        try:
            decrit = fonds.fabriquer(self.hors_ligne.dossier_fonds / f"{nom}.mbtiles", source, zone, zooms, cle,
                                     suivi=lambda faites, total: self._lot.update(faites=faites, total=total),
                                     continuer=lambda: not self._lot.get("arreter"))
        except fonds.Abandon:
            # Le fichier .part reste : la même demande reprendra où elle s'est arrêtée.
            journal.info("Fond %s : arrêté après %.0f s", nom, time.monotonic() - debut)
            self._lot.update(actif=False, erreur="Fond de carte arrêté.")
        except Exception as exc:          # réseau, clé refusée, disque : la page l'affiche
            journal.exception("Fond %s : en erreur après %.0f s", nom, time.monotonic() - debut)
            self._lot.update(actif=False, erreur=str(exc))
        else:
            journal.info("Fond %s : %d Mo, zooms %d-%d, en %.0f s", nom, decrit["octets"] // 10 ** 6, *zooms,
                         time.monotonic() - debut)
            self._lot.update(actif=False, etape="fini", fond=nom)

    def _fabriquer_lot(self, case, zone) -> None:
        travail = self.hors_ligne.racine / f".fabrication-{case}"
        debut = time.monotonic()

        def suivi(etape, faites, total):
            self._lot.update(etape=etape, faites=faites, total=total)

        try:
            fabrication.nettoyer(travail)
            fabrication.fabriquer(self.dossier, self.installation, case, travail,
                                  zone=tuple(zone) if zone else None, suivi=suivi, continuer=lambda: not self._lot.get("arreter"))
            self._lot["etape"] = "installation"
            with self._verrou_calcul:
                self._arreter_moteurs()
                self.hors_ligne.installer(travail)
        except fabrication.Abandon:
            journal.info("Lot %s : fabrication arrêtée après %.0f s", case, time.monotonic() - debut)
            self._lot.update(actif=False, erreur="Fabrication arrêtée.")
        except Exception as exc:          # réseau, disque, BRouter : la page l'affiche
            journal.exception("Lot %s : fabrication en erreur après %.0f s", case, time.monotonic() - debut)
            self._lot.update(actif=False, erreur=str(exc))
        else:
            journal.info("Lot %s : fabriqué et installé en %.0f s", case, time.monotonic() - debut)
            self._lot.update(actif=False, etape="fini")
        finally:
            fabrication.nettoyer(travail)

    def partager(self, corps) -> dict:
        """Ouvre ({"ouvrir": true}) ou ferme le partage au téléphone. Chaque
        ouverture tire un nouveau jeton : le QR code précédent ne vaut plus."""
        if not (corps or {}).get("ouvrir"):
            return self.partage.fermer()
        try:
            return self.partage.ouvrir()
        except (partage.ErreurPartage, OSError) as exc:
            journal.warning("Partage : %s", exc)
            return {"ouvert": False, "erreur": str(exc)}

    def lot_en_cours(self) -> dict:
        """État de la fabrication en cours ou de la dernière : étape, avancement, durée."""
        etat = {k: v for k, v in self._lot.items() if k != "arreter"}
        if "debut" in etat:
            etat["duree_s"] = round(time.time() - etat.pop("debut"))
        return etat

    def arreter_lot(self, corps=None) -> dict:
        self._lot["arreter"] = True
        return {"lot_en_cours": self.lot_en_cours()}

    def lots_hors_ligne(self) -> dict:
        """Lots installés : case, type, couverture, sources, taille et péremption ;
        et les fonds de carte (fonds.decrire)."""
        return {"lots": [self._lot_resume(m) for m in self.hors_ligne.lots()], "fonds": self.hors_ligne.fonds()}

    def _lot_resume(self, m) -> dict:
        limite = time.time() - self.reglages()["renouvellement_jours"] * 86400
        return {"case": m["case"], "type": m.get("type", "enrichi"), "zone": m.get("zone"),
                "sources": m.get("sources", {}), "emprise_enrichie": m.get("emprise_enrichie"),
                "octets": sum(f["octets"] for f in m.get("fichiers", [])),
                "perime": self.hors_ligne.date_du_lot(m) < limite}

    def installer_lot(self, corps) -> dict:
        """Installe le lot d'un dossier local, vérifié contre son manifeste."""
        chemin = (corps or {}).get("chemin")
        if not isinstance(chemin, str) or not chemin:
            return {"erreur": "Dossier du lot manquant."}
        try:
            manifeste = self.hors_ligne.installer(Path(chemin))
        except (hors_ligne.ErreurLot, OSError) as exc:
            journal.warning("Lot non installé depuis %s : %s", chemin, exc)
            return {"erreur": str(exc)}
        journal.info("Lot %s installé depuis %s", manifeste["case"], chemin)
        return {"installe": manifeste["case"], **self.lots_hors_ligne()}

    def ouvrir_journaux(self, corps=None) -> dict:
        """Ouvre uniquement le dossier des journaux de cette installation."""
        return {"dossier": str(journaux.ouvrir(self.dossier))}
