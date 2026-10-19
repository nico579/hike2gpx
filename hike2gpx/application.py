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
import re
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from nico579_commons import atomique
from nico579_commons import langue as langue_commune

from . import __version__, bdtopo, brouter, franchissements, maison

journal = logging.getLogger(__name__)

# Journal des calculs dans le dossier de données : 1 Mo, gardé trois fois.
FICHIER_JOURNAL = "hike2gpx.log"
LIGNES_JOURNAL = 300        # montrées par la page
LENT_S = 60.0               # au-delà, l'itinéraire est signalé lent dans le journal
# Étapes d'un calcul, telles que le journal en détaille les temps.
NOMS_ETAPES = {"debut": "préparation", "donnees": "lecture des données", "fusion": "fusion IGN",
               "tuiles": "tuile BRouter", "analyse": "franchissements", "itineraire": "calcul BRouter",
               "comparaison": "tracé standard"}
ZONE_CALQUE_MAX_DEG2 = 0.03  # un grand écran au zoom 14 ; au-delà, trop de tuiles à lire
MARGE_DEG = 0.01            # environ 1 km autour des points
MARGE_RELATIVE = 0.25
POINTS_MAX = 50
ELARGISSEMENTS = 3
# Tuiles de 0,05° lues (Overpass, BD TOPO) et fusionnées pour un calcul :
# environ 55 × 40 km. Au-delà, la première lecture prendrait des dizaines de
# minutes ; mieux vaut découper le parcours en étapes.
TUILES_MAX = 100
_CLE_IGN = re.compile(r"^[A-Za-z0-9_\-]{0,100}$")


def configurer_journal(dossier) -> Path:
    """Branche le journal de tous les modules de hike2gpx sur hike2gpx.log,
    pour retrouver une erreur, un blocage ou une lenteur. Appelé par le
    serveur seulement : les tests n'écrivent pas de journal."""
    chemin = Path(dossier) / FICHIER_JOURNAL
    racine = logging.getLogger("hike2gpx")
    if not any(isinstance(h, RotatingFileHandler) and Path(h.baseFilename) == chemin for h in racine.handlers):
        chemin.parent.mkdir(parents=True, exist_ok=True)
        fichier = RotatingFileHandler(chemin, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        fichier.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        racine.addHandler(fichier)
        racine.setLevel(logging.INFO)
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


RAISON_IGN = "Chemin de la BD TOPO absent d'OpenStreetMap : existence et accès à vérifier"


def portions_ign(trace) -> list:
    """Portions du tracé sur des chemins IGN, lues dans les messages de
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
        if "hike2gpx=ign" in ligne[i_tags]:
            if portions and portions[-1]["fin_rang"] == debut_rang:
                portions[-1].update(fin_rang=fin_rang, longueur_m=portions[-1]["longueur_m"] + longueur)
            else:
                portions.append({"debut_m": round(cumul), "longueur_m": longueur, "debut_rang": debut_rang,
                                 "fin_rang": fin_rang})
        cumul += longueur
        debut_rang = fin_rang
    return [{"debut_m": p["debut_m"], "longueur_m": round(p["longueur_m"]),
             "coords": [[c[1], c[0]] for c in coords[p["debut_rang"]:p["fin_rang"] + 1]]} for p in portions]


def entrees_ign(portions) -> list:
    """Les portions IGN comme points à vérifier sur le tracé."""
    return [{"cle": f"ign-{k}", "statut": "uncertain", "raison": RAISON_IGN,
             "nature": f"Chemin IGN de {p['longueur_m']} m", "longueur_m": p["longueur_m"],
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
        self.preferences = self.dossier / "preferences.json"
        self.serveur = None
        self.serveur_maison = None
        self._verrou_moteur = threading.Lock()
        self._verrou_calcul = threading.Lock()
        self._verrou_denivele = threading.Lock()
        # Numéro de la vue en cours de chaque calque : une vue plus récente
        # arrête la lecture des tuiles de la précédente.
        self._vues = {"osm": 0, "bdtopo": 0}
        self._verrou_vues = threading.Lock()
        self._progression = {"actif": False}
        self._debut_calcul = time.monotonic()
        self._temps_etapes, self._etape_courante = {}, None

    # ---------------------------------------------------------- réglages

    def reglages(self) -> dict:
        prefs = atomique.lire_json(self.preferences, {})
        cle = prefs.get("cle_ign") if isinstance(prefs, dict) else None
        return {"cle_ign": cle if isinstance(cle, str) and _CLE_IGN.match(cle) else ""}

    def enregistrer_reglages(self, payload) -> dict:
        cle = (payload or {}).get("cle_ign", "")
        if not isinstance(cle, str) or not _CLE_IGN.match(cle.strip()):
            return {"erreur": "Clé IGN invalide : lettres, chiffres, _ et - seulement."}
        prefs = atomique.lire_json(self.preferences, {})
        prefs = prefs if isinstance(prefs, dict) else {}
        prefs["cle_ign"] = cle.strip()
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
        try:
            self.installation.installer()
        except (brouter.ErreurBRouter, OSError, ValueError) as exc:
            return {"erreur": str(exc)}
        return self.etat()

    def telecharger_segment(self, payload) -> dict:
        nom = (payload or {}).get("nom")
        if not isinstance(nom, str) or not re.fullmatch(r"[EW]\d{1,3}_[NS]\d{1,2}", nom):
            return {"erreur": "Nom de tuile invalide."}
        try:
            self.installation.telecharger_segment(nom)
        except brouter.ErreurBRouter as exc:
            return {"erreur": str(exc)}
        return self.etat()

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
        return dict(self._progression)

    def lire_journal(self) -> dict:
        """Les dernières lignes du journal des calculs, pour la page."""
        chemin = self.dossier / FICHIER_JOURNAL
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
                             "%d portion(s) IGN%s", duree, reponse["longueur_m"] or 0, reponse["moteur"],
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
        if not self.installation.installee():
            return {"erreur": "Le moteur BRouter n'est pas installé.", "moteur_absent": True}
        debut = time.monotonic()
        zone = zone_autour(points)
        avertissement = detail_avertissement = None
        journal.info("Itinéraire : %d points, %d tuiles, chemins IGN %s, mode strict %s", len(points),
                     len(franchissements.tuiles_zone(*zone)), "oui" if ign else "non", "oui" if strict else "non")
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
                            "segments_manquants": manquants}
                trace, moteur_utilise = None, "standard"
                if ign:
                    # Tuiles maison : OSM plus les chemins IGN qui y manquent, avec
                    # les franchissements du réseau fusionné. Si elles ne peuvent se
                    # faire, le moteur standard calcule sur OSM seul ; un itinéraire
                    # introuvable sur elles reste une erreur.
                    def suivi_maison(etape, faites, total, passe=passe):
                        fraction = {"donnees": 0.05 + 0.45 * faites / max(total, 1), "fusion": 0.5,
                                    "tuiles": 0.6, "analyse": 0.78}[etape]
                        self._avancer(etape, fraction, faites, total, passe)
                    try:
                        segments, liste = self.maison.preparer(franchissements.tuiles_zone(*zone),
                                                               suivi=suivi_maison)
                        port = self.moteur_maison(segments)
                    except (franchissements.ErreurDonnees, brouter.ErreurBRouter, OSError, ImportError,
                            ValueError) as exc:
                        avertissement = f"Chemins IGN indisponibles, calcul sur OSM seul : {exc}"
                        detail_avertissement = str(exc)
                        journal.warning("Chemins IGN indisponibles : %s", exc)
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
            return {"erreur": str(exc)}
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
                   "avertissement_detail": detail_avertissement, "strict": strict}
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

    def _calque(self, cle, zone, lire):
        """Un calque pour la vue de la page, une vue à la fois : la demande
        d'une nouvelle vue arrête la lecture des tuiles de la précédente, que
        plus personne ne regarde. Le résultat donne les bornes des tuiles
        lues, que la page n'a pas à redemander tant que la vue y reste."""
        with self._verrou_vues:
            self._vues[cle] += 1
            numero = self._vues[cle]
        if zone is None:
            return {"erreur": "Zone invalide."}
        if (zone[2] - zone[0]) * (zone[3] - zone[1]) > ZONE_CALQUE_MAX_DEG2:
            return {"erreur": "Zone trop grande : zoomez davantage."}
        try:
            resultat = lire(*zone, self.dossier, continuer=lambda: self._vues[cle] == numero)
        except franchissements.VueRemplacee:
            return {"erreur": "Vue remplacée par une autre.", "code": "vue_remplacee"}
        except franchissements.ErreurDonnees as exc:
            return {"erreur": str(exc)}
        return {**resultat, "bornes": franchissements.bornes_zone(*zone)}

    def calque_osm(self, zone) -> dict:
        return self._calque("osm", zone, franchissements.voies_affichables)

    def calque_bdtopo(self, zone) -> dict:
        def lire(*bornes, **options):
            return {"troncons": bdtopo.troncons_zone(*bornes, **options)}
        return self._calque("bdtopo", zone, lire)

    def arreter_calques(self, corps=None) -> dict:
        """La page n'affiche plus ces calques (zoom trop faible, calque masqué) :
        leurs lectures en cours s'arrêtent avant la tuile suivante."""
        demandes = (corps or {}).get("calques")
        cles = [c for c in self._vues if not isinstance(demandes, list) or c in demandes]
        with self._verrou_vues:
            for cle in cles:
                self._vues[cle] += 1
        return {"arretes": cles}

    def routes(self):
        # /api/langue : le choix FR / EN du commun, gardé dans les préférences.
        get_langue, post_langue = langue_commune.routes(self.lire_langue, self.ecrire_langue)
        get = {"init": self.etat, "etat": self.etat, "reglages": self.reglages,
               "osm": self.calque_osm, "bdtopo": self.calque_bdtopo,
               "progression": self.progression, "journal": self.lire_journal, **get_langue}
        post = {"itineraire": self.itineraire, "reglages": self.enregistrer_reglages,
                "segment": self.telecharger_segment, "moteur": self.installer_moteur,
                "denivele": self.denivele, "arreter_calques": self.arreter_calques, **post_langue}
        return get, post
