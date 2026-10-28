"use strict";

// Page de tracé de hike2gpx : points posés sur la carte, itinéraire calculé
// par le serveur local (BRouter et les coupes des franchissements), export
// GPX. Les textes venus d'OpenStreetMap passent toujours par textContent.

const DELAI_CALCUL_MS = 250;
const CLE_VUE = "hike2gpx.vue";
const CLE_POINTS = "hike2gpx.points";
const COULEURS = { blocked: "#d32f2f", uncertain: "#ef6c00" };

const etat = { points: [], sequence: 0, minuterie: null, dernier: null, cleIgn: "", version: "", sequenceDenivele: 0,
  suivi: null, statut: ["", false], extrait: null, donneesAttendues: false };
const $ = (id) => document.getElementById(id);

// ------------------------------------------------------------ langue

// Textes de la page en français et en anglais, comme dans les autres
// applications : le choix FR / EN est celui du commun (/nico579-langue.js),
// qui l'enregistre et l'annonce par l'événement « nico579-langue » ; la page
// applique alors ce dictionnaire. Les éléments fixes portent data-i18n.
const TEXTES = {
  fr: {
    "page.titre": "hike2gpx — tracer un parcours",
    "onglets.titre": "Outils de randonnée",
    "onglets.parcours": "Parcours",
    "onglets.reglages": "Réglages",
    "aide": "Cliquez sur la carte pour poser le départ, puis les étapes et l'arrivée. Faites glisser un point pour le déplacer ; « Revenir au départ » ferme une boucle.",
    "bouton.retirerDernier": "Retirer",
    "bouton.retirerDernierInfo": "Retire le dernier point ajouté au parcours.",
    "bouton.toutEffacer": "Effacer",
    "bouton.toutEffacerInfo": "Efface tous les points et le tracé du parcours en cours.",
    "bouton.boucler": "Revenir",
    "bouton.bouclerInfo": "Ajoute le point de départ à la fin du parcours pour fermer la boucle.",
    "bouton.exporter": "Exporter le GPX",
    "bouton.chargerGpx": "Charger un GPX",
    "bouton.supprimerGpx": "Supprimer le GPX",
    "gpx.erreur": "Impossible de charger ce GPX : {message}",
    "gpx.invalide": "fichier GPX invalide ou sans tracé.",
    "gpx.tropGrand": "fichier trop volumineux (20 Mo maximum).",
    "option.strict": "Mode strict : éviter aussi les passages à vérifier",
    "option.cheminsRoutables": "Emprunter aussi les {nom} absents d’OSM (à vérifier sur place)",
    "option.cheminsAffichage": "{nom} : affichage seul, calcul sur les chemins OSM",
    "option.comparer": "Montrer le tracé qui ignore les barrières",
    "resultat.distance": "Distance",
"resultat.duree": "Durée estimée",
"resultat.altitudeMaxMin": "Altitude max/min",
    "resultat.denivele": "Dénivelé",
    "resume.parcours": "Votre parcours",
"resume.dureeInfo": "Modèle de Tobler sur le profil gpx2elev lissé : v = 6 × exp(−3,5 × |pente + 0,05|) km/h. La pente est calculée tous les 20 m dans le sens du parcours ; les durées sont additionnées sans pauses. Le facteur 0,6 ne s'applique qu'aux portions identifiées hors sentier ; les chemins officiels restent des chemins.",
"recherche.label": "Rechercher une ville ou des coordonnées GPS",
"recherche.placeholder": "Ville ou coordonnées (lat, lon)…",
"recherche.bouton": "Chercher",
"recherche.attente": "Recherche en cours…",
"recherche.aucun": "Aucune ville trouvée.",
"recherche.erreur": "Recherche indisponible : {message}",
    "menu.coordonnees": "Coordonnées GPS (latitude, longitude)",
    "menu.copier": "Copier les coordonnées",
    "menu.copie": "Coordonnées copiées",
    "menu.selection": "Coordonnées sélectionnées : copiez-les avec Ctrl+C.",
    "resume.deniveleInfo": "gpx2elev relève l'altitude tous les 5 m. Il choisit le meilleur modèle couvrant tout le parcours : IGN LiDAR HD en priorité, puis Mapterhorn, FABDEM, Copernicus GLO-30 ou SRTM. Il lisse le profil sur 20 m et calcule D+/D− avec un seuil de 2 m. Le modèle utilisé est indiqué sur le profil. Sans modèle disponible, le dénivelé reste indisponible ; la valeur BRouter ne le remplace pas.",
    "profil.titre": "Le relief du parcours",
    "profil.depart": "Départ",
    "profil.attente": "Calcul gpx2elev en cours…",
    "profil.indisponible": "Profil gpx2elev indisponible : {erreur}",
    "resultat.aVerifier": "Points à vérifier sur le tracé",
    "resultat.aucun": "Aucun franchissement connu sur ce tracé.",
    "legende.titre": "Légende",
    "legende.itineraire": "itinéraire hike2gpx",
    "legende.naif": "tracé standard, qui ignore les barrières",
    "legende.bloque": "franchissement bloquant",
    "legende.verifier": "franchissement à vérifier",
    "legende.osm": "chemins OSM (tirets : sentiers)",
    "legende.barriere": "clôtures et murs connus d'OSM",
    "legende.gpx": "GPX chargé",
    "reglages.titre": "Réglages",
    "reglages.cle": "Clé IGN pour le SCAN 25",
    "reglages.enregistrer": "Enregistrer",
    "reglages.note": "Le SCAN 25 n'est pas une donnée libre. Sans clé, la carte utilise le Plan IGN, sous Licence Ouverte.",
    "reglages.renouvellement": "Renouveler les données locales après",
    "reglages.jours": "jours",
    "reglages.masquerCartes": "Masquer le bandeau des cartes",
    "reglages.masquerDenivele": "Masquer le bandeau du dénivelé",
    "reglages.transparence": "Transparence des bandeaux",
    "reglages.ouvrirJournaux": "Ouvrir le dossier des journaux",
    "reglages.erreurJournaux": "Impossible d'ouvrir le dossier des journaux : {message}",
    "reglages.verifierMaj": "Vérifier les mises à jour",
    "reglages.verification": "Vérification…",
    "reglages.aJour": "Vous avez la dernière version.",
    "reglages.majDisponible": "Version {version} disponible : le bandeau propose de l'installer.",
    "reglages.majImpossible": "Vérification impossible (réseau ?).",
    "disponibilite.oui": "Tracé disponible",
    "disponibilite.non": "Tracé indisponible",
    "disponibilite.attente.moteur": "Installation de BRouter en cours",
    "disponibilite.attente.segments": "Tuiles BRouter en cours de téléchargement",
    "disponibilite.attente.osm": "Données OSM ou Overpass en attente",
    "disponibilite.attente.source": "Chemins officiels indisponibles dans cette zone",
    "disponibilite.attente.zone": "Zone du parcours à préciser",
    "disponibilite.info.titre": "Sources du prochain calcul",
    "disponibilite.info.verification": "Vérification des données en cours…",
    "disponibilite.info.overpass": "Overpass",
    "disponibilite.info.lot": "Lot hors ligne",
    "disponibilite.info.local": "Extrait OSM local",
    "disponibilite.info.regional": "Extrait OSM régional",
    "disponibilite.info.brouter": "BRouter",
    "disponibilite.info.pret": "prêt",
    "disponibilite.info.attente": "en attente",
    "disponibilite.etat.oui": "répond",
    "disponibilite.etat.non": "ne répond pas",
    "disponibilite.etat.verification": "vérification en cours",
    "disponibilite.etat.disponible": "disponible",
    "disponibilite.etat.absent": "absent",
    "disponibilite.etat.telechargement": "téléchargement en cours",
    "disponibilite.etat.import": "import en cours",
    "disponibilite.etat.non_applicable": "sans objet",
    "statut.donneesIndisponibles": "Données OSM indisponibles pour ce tracé. Nouvelle tentative automatique après téléchargement.",
    "donnees.titre": "Données téléchargées",
    "donnees.note": "Tout se retélécharge de soi-même au besoin : vider ou supprimer libère de la place, actualiser donne des données fraîches.",
    "donnees.osm": "Chemins OSM lus sur Overpass : {n} tuiles, {taille}",
    "donnees.extrait": "Extrait {nom} du {date}, {taille}",
    "donnees.extrait.provisoire": "Extrait {nom} du {date}, {taille}, en attendant sa région",
    "donnees.brouter": "Tuiles BRouter {noms} : {taille}",
    "donnees.restes": "Fichiers inutiles : {taille}",
    "donnees.vider": "Vider",
    "donnees.actualiser": "Actualiser",
    "donnees.supprimer": "Supprimer",
    "donnees.nettoyer": "Nettoyer",
    "donnees.confirmer": "Supprimer l'extrait {nom} ? Il se retéléchargera de lui-même s'il resert.",
    "donnees.viderTout": "Vider le cache",
    "donnees.aideCache": "Détail des caches vidés",
    "donnees.detailCache": "Ce bouton efface les réponses Overpass et les franchissements OSM, les chemins officiels, les extraits OSM téléchargés, les données BRouter et les modèles d'altitude gpx2elev. Ils seront retéléchargés au besoin. Les tuiles des fonds de carte, conservées dans le cache du navigateur, ne sont pas effacées.",
    "donnees.confirmerTout": "Vider les données locales OSM, IGN, gpx2elev et BRouter, ainsi que les lots et les fonds hors ligne ? Les données en ligne et les lots du serveur seront retéléchargés au besoin ; les lots et les fonds préparés sur cet ordinateur seront à refaire. Les tuiles de fond de carte affichées restent dans le cache du navigateur.",
    "donnees.vide": "Cache local vidé, lots et fonds hors ligne compris. Les tuiles du fond de carte affiché restent gérées par le navigateur.",
    "horsLigne.supprimer": "Supprimer de cet ordinateur",
    "horsLigne.confirmerSuppression": "Retirer de cet ordinateur le lot et les fonds de carte de la case {nom} ({taille}) ? Un lot du serveur se retélécharge ; un lot ou un fond préparé sur cet ordinateur sera à refaire.",
    "horsLigne.supprimee": "Case {nom} retirée de cet ordinateur : {taille} libérés.",
    "donnees.infoCache": "Les tuiles IGN et OSM du fond de carte restent dans le cache du navigateur.",
    "unite.mo": "Mo",
    "pied": "Barrières et chemins © contributeurs OpenStreetMap (ODbL), chemins et cartes officiels selon le pays, calcul BRouter. Une barrière absente d'OpenStreetMap ne peut pas être évitée : le terrain a toujours le dernier mot.",
    "statut.deuxiemePoint": "Posez un deuxième point.",
    "statut.calcul": "Calcul en cours… La première fois dans une zone, la lecture des barrières OSM prend jusqu'à une minute",
    "statut.calculOfficiel": ", puis la fusion avec les chemins {nom} quelques secondes.",
    "avertissement.officiel": "Chemins {nom} indisponibles, calcul sur OSM seul : {detail}",
    "statut.erreur": "Erreur : {message}",
    "statut.bilan": "Calculé en {duree} s ; franchissements connus dans la zone examinée : {total}.",
    "comparaison.traverse": "Le tracé standard (profil Randonnée de BRouter, sans les barrières) mesure {km} ; franchissements bloquants traversés : {n}.",
    "comparaison.aucun": "Le tracé standard (profil Randonnée de BRouter, sans les barrières) mesure {km} et ne traverse aucun franchissement bloquant connu.",
    "liste.centrer": "Centrer la carte sur ce point",
    "bulle.bloquant": "bloquant",
    "bulle.verifier": "à vérifier",
    "bulle.osm": "Voir dans OpenStreetMap",
    "bulle.retirer": "Retirer ce point",
    "bulle.revenir": "Revenir ici en fin de parcours",
    "brouter.moteur": "moteur BRouter",
    "brouter.enCours": "Données BRouter : téléchargement en cours ({quoi})…",
    "brouter.attente": "Téléchargement des données BRouter ({quoi}) : le calcul reprendra de lui-même.",
    "serveur.injoignable": "Serveur injoignable : {message}",
    "denivele.calcul": "Calcul du dénivelé par gpx2elev en cours…",
    "denivele.indisponible": "Dénivelé indisponible : gpx2elev, {erreur}",
    "denivele.source": "Source des altitudes du parcours : {modele} · calcul gpx2elev (pas 5 m, lissage 20 m, seuil 2 m).",
    "calque.osm": "Chemins OSM",
    "calque.chargement": "Chargement des {nom}… (la première fois, jusqu'à une minute)",
    "calque.avancement": "Chargement des {nom}… {faites} sur {total} tuiles · {duree} s",
    "liaison.et": " et ",
    "calque.zoom": "Zoomez davantage (niveau {niveau}) pour voir les chemins.",
    "extrait.telechargement": "Données OSM hors ligne : téléchargement de l'extrait {nom}, {pourcent} %",
    "extrait.import": "Données OSM hors ligne : import de l'extrait {nom}, {voies} voies lues…",
    "extrait.relais.telechargement": "Données OSM hors ligne : extrait {nom} du {date} ; la région {region} se télécharge pour prendre le relais, {pourcent} %",
    "extrait.relais.import": "Données OSM hors ligne : extrait {nom} du {date} ; la région {region} s'importe pour prendre le relais, {voies} voies lues…",
    "extrait.installe": "Données OSM hors ligne : extrait {nom} du {date}, renouvelé tous les {jours} jours.",
    "extrait.erreur": "Extrait {nom} non installé : {message}",
    "extrait.attente": "Overpass ne répond pas ; l'extrait OSM {nom} se télécharge, le calcul reprendra de lui-même.",
    "fond.osmRando": "OSM rando",
    "fond.osm": "OSM",
    "fond.satellite": "Satellite",
    "fond.horsLigne": "Carte hors ligne",
    "attribution.osm": "contributeurs OpenStreetMap",
    "cle.enregistree": "Clé enregistrée : SCAN 25 disponible.",
    "cle.retiree": "Clé retirée : Plan IGN par défaut.",
    "aide.titre": "Aide : le mode d'emploi (README)",
    "reglages.casesHorsLigne": "Afficher les cases hors ligne (5°)",
    "reglages.casesNombre": "{nombre} case(s) prête(s) · vert : prête, bleu : sur le serveur, orange : en préparation, gris : à préparer",
    "reglages.casesAucune": "Aucune case prête hors ligne. Cliquez une case de la carte pour la préparer.",
    "horsLigne.bouton": "Hors ligne",
    "horsLigne.boutonTitre": "Afficher les cases hors ligne (5°) : lots et fonds de carte pour marcher sans réseau",
    "horsLigne.aide": "Cliquez une case : télécharger son lot depuis le serveur, préparer la vue ou toute la case, ou son fond de carte.",
    "horsLigne.case": "Case {nom}",
    "horsLigne.prete": "Prête hors ligne : {taille}, OSM du {date}.",
    "horsLigne.absente": "Pas encore disponible hors ligne.",
    "horsLigne.absenteServeur": "Publiée par le serveur, pas encore sur cet ordinateur : elle se téléchargera d'elle-même dès qu'un parcours ou les chemins de la carte s'en serviront.",
    "horsLigne.telechargerMaintenant": "Télécharger maintenant",
    "horsLigne.serveur": "Sur le serveur : {taille}, OSM du {osm}{officiels}.",
    "horsLigne.serveurOfficiels": ", chemins officiels du {date}",
    "horsLigne.serveurAJour": "À jour avec le serveur.",
    "horsLigne.telechargerMaj": "Mettre à jour depuis le serveur",
    "horsLigne.enPreparation": "En préparation.",
    "horsLigne.preparerVue": "Préparer la vue actuelle",
    "horsLigne.preparerCase": "Préparer toute la case (environ une heure)",
    "horsLigne.mettreAJour": "Mettre à jour",
    "horsLigne.arreter": "Arrêter",
    "horsLigne.avancement": "Préparation hors ligne de {nom} : {etape}{compte}, depuis {duree}",
    "horsLigne.attenteCalques": "Chemins de la carte : en attente du lot hors ligne de la zone, qui se télécharge.",
    "horsLigne.attenteCalcul": "Le lot hors ligne de la zone se télécharge : le calcul reprendra dès son arrivée.",
    "horsLigne.automatique": "Lot de la case {nom}, téléchargé de lui-même depuis le serveur :{compte}, depuis {duree}. Il prendra le relais du mode à la volée.",
    "horsLigne.fini": "Case {nom} prête hors ligne.",
    "horsLigne.perime": "Le lot hors ligne de {nom} date du {date}, au-delà du délai de renouvellement. Le mettre à jour ?",
    "horsLigne.plusTard": "Plus tard",
    "horsLigne.erreur": "Préparation de {nom} interrompue : {erreur}",
    "horsLigne.etape.debut": "démarrage",
    "horsLigne.etape.rd5": "itinéraires BRouter",
    "horsLigne.etape.extraits": "extraits OSM",
    "horsLigne.etape.calques": "chemins et franchissements",
    "horsLigne.etape.installation": "installation",
    "horsLigne.etape.telechargement": "téléchargement depuis le serveur",
    "horsLigne.etape.osm": "lecture d'OSM",
    "horsLigne.etape.fusion": "fusion des chemins officiels",
    "horsLigne.etape.relief": "relief",
    "horsLigne.etape.compilation": "itinéraires BRouter",
    "horsLigne.etape.fond": "fond de carte",
    "horsLigne.fonds": "Fond de carte hors ligne : {liste}.",
    "horsLigne.fondVue": "vue",
    "horsLigne.fondCase": "toute la case",
    "horsLigne.preparerFondVue": "Fond de carte de la vue ({source})",
    "horsLigne.preparerFondCase": "Fond de carte de toute la case ({source}, zooms 6 à 13, environ {duree})",
    "horsLigne.fondFini": "Fond de carte {nom} prêt hors ligne.",
    "partage.ouvrir": "Partager au téléphone",
    "partage.fermer": "Arrêter le partage",
    "partage.ouvert": "Scannez ce code avec hike2gpx sur le téléphone, sur le même Wi-Fi : {lots} lot(s) et {fonds} fond(s) de carte, {taille}. Le code change à chaque partage.",
    "partage.erreur": "Partage impossible : {erreur}",
    "pleinEcran.entrer": "Plein écran",
    "pleinEcran.quitter": "Quitter le plein écran",
    "etape.debut": "Préparation du calcul",
    "etape.donnees": "Lecture des données de la zone : {faites} / {total} tuiles",
    "etape.fusion": "Fusion avec les chemins officiels",
    "etape.tuiles": "Fabrication de la tuile BRouter",
    "etape.analyse": "Analyse des franchissements",
    "etape.itineraire": "Calcul de l'itinéraire",
    "etape.comparaison": "Tracé standard, pour comparaison",
    "etape.elargie": " (zone élargie)",
    "icone.depart": "D",
    "icone.arrivee": "A",
    "gpx.deniveleIndisponible": "dénivelé gpx2elev indisponible",
    "gpx.description": "Distance {km}, {denivele}, passages à vérifier : {n}. ",
    "gpx.barrieres": "Barrières © contributeurs OpenStreetMap",
    "gpx.trace": " ; tracé hike2gpx.",
    "gpx.aVerifier": "À vérifier : {nature}",
    "erreur.zone_trop_etendue": "Zone trop étendue : {nombre} tuiles de 0,05° à examiner, au plus {max}. Découpez le parcours en étapes plus courtes.",
    "erreur.itineraire_refuse": "Itinéraire refusé : le tracé passe un franchissement {mot} ({nature}, à {distance} du départ).",
    "mot.bloquant": "bloquant",
    "mot.strict": "à vérifier, en mode strict",
  },
  en: {
    "page.titre": "hike2gpx — plan a route",
    "onglets.titre": "Hiking tools",
    "onglets.parcours": "Route",
    "onglets.reglages": "Settings",
    "aide": "Click the map to place the start, then the waypoints and the finish. Drag a point to move it; “Back to start” closes a loop.",
    "bouton.retirerDernier": "Remove",
    "bouton.retirerDernierInfo": "Removes the last point added to the route.",
    "bouton.toutEffacer": "Clear",
    "bouton.toutEffacerInfo": "Clears all points and the current route.",
    "bouton.boucler": "Return",
    "bouton.bouclerInfo": "Adds the starting point to the end of the route to close the loop.",
    "bouton.exporter": "Export GPX",
    "bouton.chargerGpx": "Load a GPX",
    "bouton.supprimerGpx": "Remove GPX",
    "gpx.erreur": "Unable to load this GPX: {message}",
    "gpx.invalide": "invalid GPX file or no track found.",
    "gpx.tropGrand": "file too large (20 MB maximum).",
    "option.strict": "Strict mode: also avoid crossings to check",
    "option.cheminsRoutables": "Also use {nom} missing from OSM (check on site)",
    "option.cheminsAffichage": "{nom}: map display only; routing uses OSM paths",
    "option.comparer": "Show the route that ignores barriers",
    "resultat.distance": "Distance",
"resultat.duree": "Estimated time",
"resultat.altitudeMaxMin": "Max/min altitude",
    "resultat.denivele": "Elevation",
    "resume.parcours": "Your route",
"resume.dureeInfo": "Tobler's model on the smoothed gpx2elev profile: v = 6 × exp(−3.5 × |slope + 0.05|) km/h. Slope is measured every 20 m in travel direction; segment times are added without breaks. The 0.6 factor applies only to identified off-path sections; official paths remain paths.",
"recherche.label": "Search for a town or GPS coordinates",
"recherche.placeholder": "Town or coordinates (lat, lon)…",
"recherche.bouton": "Search",
"recherche.attente": "Searching…",
"recherche.aucun": "No town found.",
"recherche.erreur": "Search unavailable: {message}",
    "menu.coordonnees": "GPS coordinates (latitude, longitude)",
    "menu.copier": "Copy coordinates",
    "menu.copie": "Coordinates copied",
    "menu.selection": "Coordinates selected: copy them with Ctrl+C.",
    "resume.deniveleInfo": "gpx2elev samples elevation every 5 m. It selects the best model covering the whole route: IGN LiDAR HD first, then Mapterhorn, FABDEM, Copernicus GLO-30 or SRTM. It smooths the profile over 20 m and calculates ascent/descent with a 2 m threshold. The selected model appears on the profile. If none is available, elevation remains unavailable; the BRouter estimate is not substituted.",
    "profil.titre": "Route elevation",
    "profil.depart": "Start",
    "profil.attente": "Calculating with gpx2elev…",
    "profil.indisponible": "gpx2elev profile unavailable: {erreur}",
    "resultat.aVerifier": "Points to check along the route",
    "resultat.aucun": "No known crossing on this route.",
    "legende.titre": "Legend",
    "legende.itineraire": "hike2gpx route",
    "legende.naif": "standard route, ignoring barriers",
    "legende.bloque": "blocking crossing",
    "legende.verifier": "crossing to check",
    "legende.osm": "OSM paths (dashed: footpaths)",
    "legende.barriere": "fences and walls known to OSM",
    "legende.gpx": "Loaded GPX",
    "reglages.titre": "Settings",
    "reglages.cle": "IGN key for SCAN 25",
    "reglages.enregistrer": "Save",
    "reglages.note": "SCAN 25 is not open data. Without a key, the map uses Plan IGN, under the Open Licence.",
    "reglages.renouvellement": "Refresh local data after",
    "reglages.jours": "days",
    "reglages.masquerCartes": "Hide the map layers panel",
    "reglages.masquerDenivele": "Hide the elevation panel",
    "reglages.transparence": "Panel transparency",
    "reglages.ouvrirJournaux": "Open logs folder",
    "reglages.erreurJournaux": "Unable to open the logs folder: {message}",
    "reglages.verifierMaj": "Check for updates",
    "reglages.verification": "Checking…",
    "reglages.aJour": "You have the latest version.",
    "reglages.majDisponible": "Version {version} available: the banner offers to install it.",
    "reglages.majImpossible": "Could not check (network?).",
    "disponibilite.oui": "Routing available",
    "disponibilite.non": "Routing unavailable",
    "disponibilite.attente.moteur": "BRouter installation in progress",
    "disponibilite.attente.segments": "BRouter tiles downloading",
    "disponibilite.attente.osm": "Waiting for OSM data or Overpass",
    "disponibilite.attente.source": "Official paths unavailable in this area",
    "disponibilite.attente.zone": "Route area needs to be specified",
    "disponibilite.info.titre": "Sources for the next route",
    "disponibilite.info.verification": "Checking data…",
    "disponibilite.info.overpass": "Overpass",
    "disponibilite.info.lot": "Offline bundle",
    "disponibilite.info.local": "Local OSM extract",
    "disponibilite.info.regional": "Regional OSM extract",
    "disponibilite.info.brouter": "BRouter",
    "disponibilite.info.pret": "ready",
    "disponibilite.info.attente": "waiting",
    "disponibilite.etat.oui": "responding",
    "disponibilite.etat.non": "not responding",
    "disponibilite.etat.verification": "checking",
    "disponibilite.etat.disponible": "available",
    "disponibilite.etat.absent": "absent",
    "disponibilite.etat.telechargement": "downloading",
    "disponibilite.etat.import": "importing",
    "disponibilite.etat.non_applicable": "not applicable",
    "statut.donneesIndisponibles": "OSM data unavailable for this route. Automatic retry after download.",
    "donnees.titre": "Downloaded data",
    "donnees.note": "Everything downloads again by itself when needed: clearing or deleting frees space, refreshing brings fresh data.",
    "donnees.osm": "OSM paths read from Overpass: {n} tiles, {taille}",
    "donnees.extrait": "{nom} extract of {date}, {taille}",
    "donnees.extrait.provisoire": "{nom} extract of {date}, {taille}, until its region arrives",
    "donnees.brouter": "BRouter tiles {noms}: {taille}",
    "donnees.restes": "Leftover files: {taille}",
    "donnees.vider": "Clear",
    "donnees.actualiser": "Refresh",
    "donnees.supprimer": "Delete",
    "donnees.nettoyer": "Clean up",
    "donnees.confirmer": "Delete the {nom} extract? It will download again by itself if needed.",
    "donnees.viderTout": "Clear cache",
    "donnees.aideCache": "Details of cleared caches",
    "donnees.detailCache": "This clears Overpass responses and OSM crossings, official paths, downloaded OSM extracts, BRouter data and gpx2elev elevation models. They are downloaded again when needed. Background map tiles held in the browser cache are not cleared.",
    "donnees.confirmerTout": "Clear local OSM, IGN, gpx2elev and BRouter data, and the offline bundles and maps? Online data and the server's bundles will download again when needed; bundles and maps prepared on this computer will have to be made again. Displayed background map tiles remain in the browser cache.",
    "donnees.vide": "Local cache cleared, offline bundles and maps included. Displayed background map tiles remain managed by the browser.",
    "horsLigne.supprimer": "Remove from this computer",
    "horsLigne.confirmerSuppression": "Remove the bundle and the background maps of the {nom} area from this computer ({taille})? A server bundle downloads again; a bundle or map prepared on this computer will have to be made again.",
    "horsLigne.supprimee": "{nom} area removed from this computer: {taille} freed.",
    "donnees.infoCache": "IGN and OSM background map tiles remain in the browser cache.",
    "unite.mo": "MB",
    "pied": "Barriers and paths © OpenStreetMap contributors (ODbL), official paths and maps according to the country, routing by BRouter. A barrier missing from OpenStreetMap cannot be avoided: the ground always has the last word.",
    "statut.deuxiemePoint": "Place a second point.",
    "statut.calcul": "Calculating… The first time in an area, reading the OSM barriers takes up to a minute",
    "statut.calculOfficiel": ", then merging {nom} paths takes a few seconds.",
    "avertissement.officiel": "{nom} paths unavailable, routing on OSM only: {detail}",
    "statut.erreur": "Error: {message}",
    "statut.bilan": "Calculated in {duree} s; known crossings in the examined area: {total}.",
    "comparaison.traverse": "The standard route (BRouter hiking profile, without the barriers) is {km} long; blocking crossings passed: {n}.",
    "comparaison.aucun": "The standard route (BRouter hiking profile, without the barriers) is {km} long and passes no known blocking crossing.",
    "liste.centrer": "Center the map on this point",
    "bulle.bloquant": "blocking",
    "bulle.verifier": "to check",
    "bulle.osm": "View on OpenStreetMap",
    "bulle.retirer": "Remove this point",
    "bulle.revenir": "Come back here at the end",
    "brouter.moteur": "BRouter engine",
    "brouter.enCours": "BRouter data: downloading ({quoi})…",
    "brouter.attente": "Downloading BRouter data ({quoi}): the calculation will resume by itself.",
    "serveur.injoignable": "Server unreachable: {message}",
    "denivele.calcul": "Calculating elevation with gpx2elev…",
    "denivele.indisponible": "Elevation unavailable: gpx2elev, {erreur}",
    "denivele.source": "Route elevation source: {modele} · gpx2elev calculation (5 m sampling, 20 m smoothing, 2 m threshold).",
    "calque.osm": "OSM paths",
    "calque.chargement": "Loading the {nom}… (the first time, up to a minute)",
    "calque.avancement": "Loading the {nom}… {faites} of {total} tiles · {duree} s",
    "liaison.et": " and ",
    "calque.zoom": "Zoom in further (level {niveau}) to see the paths.",
    "extrait.telechargement": "Offline OSM data: downloading the {nom} extract, {pourcent} %",
    "extrait.import": "Offline OSM data: importing the {nom} extract, {voies} ways read…",
    "extrait.relais.telechargement": "Offline OSM data: {nom} extract of {date}; the {region} region is downloading to take over, {pourcent} %",
    "extrait.relais.import": "Offline OSM data: {nom} extract of {date}; the {region} region is importing to take over, {voies} ways read…",
    "extrait.installe": "Offline OSM data: {nom} extract of {date}, renewed every {jours} days.",
    "extrait.erreur": "{nom} extract not installed: {message}",
    "extrait.attente": "Overpass is not responding; the {nom} OSM extract is downloading, the calculation will resume by itself.",
    "fond.osmRando": "OSM hiking",
    "fond.osm": "OSM",
    "fond.satellite": "Satellite",
    "fond.horsLigne": "Offline map",
    "attribution.osm": "OpenStreetMap contributors",
    "cle.enregistree": "Key saved: SCAN 25 available.",
    "cle.retiree": "Key removed: Plan IGN by default.",
    "aide.titre": "Help: the user guide (README)",
    "reglages.casesHorsLigne": "Show offline areas (5°)",
    "reglages.casesNombre": "{nombre} area(s) ready · green: ready, blue: on the server, orange: being prepared, gray: to prepare",
    "reglages.casesAucune": "No area is ready offline yet. Click an area on the map to prepare it.",
    "horsLigne.bouton": "Offline",
    "horsLigne.boutonTitre": "Show the offline areas (5°): bundles and base maps to hike with no network",
    "horsLigne.aide": "Click an area: download its bundle from the server, prepare the view or the whole area, or its base map.",
    "horsLigne.case": "Area {nom}",
    "horsLigne.prete": "Ready offline: {taille}, OSM of {date}.",
    "horsLigne.absente": "Not available offline yet.",
    "horsLigne.absenteServeur": "Published by the server, not on this computer yet: it will download by itself as soon as a route or the map's paths use it.",
    "horsLigne.telechargerMaintenant": "Download now",
    "horsLigne.serveur": "On the server: {taille}, OSM of {osm}{officiels}.",
    "horsLigne.serveurOfficiels": ", official paths of {date}",
    "horsLigne.serveurAJour": "Up to date with the server.",
    "horsLigne.telechargerMaj": "Update from the server",
    "horsLigne.enPreparation": "Being prepared.",
    "horsLigne.preparerVue": "Prepare the current view",
    "horsLigne.preparerCase": "Prepare the whole area (about an hour)",
    "horsLigne.mettreAJour": "Update",
    "horsLigne.arreter": "Stop",
    "horsLigne.avancement": "Preparing {nom} for offline use: {etape}{compte}, for {duree}",
    "horsLigne.attenteCalques": "Map paths: waiting for the area's offline bundle, which is downloading.",
    "horsLigne.attenteCalcul": "The area's offline bundle is downloading: the route will be computed as soon as it arrives.",
    "horsLigne.automatique": "Bundle of the {nom} area, downloading by itself from the server:{compte}, for {duree}. It will take over from on-the-fly mode.",
    "horsLigne.fini": "Area {nom} ready offline.",
    "horsLigne.perime": "The offline data of {nom} dates from {date}, past the refresh delay. Update it?",
    "horsLigne.plusTard": "Later",
    "horsLigne.erreur": "Preparation of {nom} interrupted: {erreur}",
    "horsLigne.etape.debut": "starting",
    "horsLigne.etape.rd5": "BRouter routing data",
    "horsLigne.etape.extraits": "OSM extracts",
    "horsLigne.etape.calques": "paths and crossings",
    "horsLigne.etape.installation": "installation",
    "horsLigne.etape.telechargement": "download from the server",
    "horsLigne.etape.osm": "reading OSM",
    "horsLigne.etape.fusion": "merging official paths",
    "horsLigne.etape.relief": "elevation",
    "horsLigne.etape.compilation": "BRouter routing data",
    "horsLigne.etape.fond": "base map",
    "horsLigne.fonds": "Offline base map: {liste}.",
    "horsLigne.fondVue": "view",
    "horsLigne.fondCase": "whole area",
    "horsLigne.preparerFondVue": "Base map of the view ({source})",
    "horsLigne.preparerFondCase": "Base map of the whole area ({source}, zooms 6 to 13, about {duree})",
    "horsLigne.fondFini": "Base map {nom} ready offline.",
    "partage.ouvrir": "Share with the phone",
    "partage.fermer": "Stop sharing",
    "partage.ouvert": "Scan this code with hike2gpx on the phone, on the same Wi-Fi: {lots} bundle(s) and {fonds} base map(s), {taille}. The code changes with every share.",
    "partage.erreur": "Sharing failed: {erreur}",
    "pleinEcran.entrer": "Full screen",
    "pleinEcran.quitter": "Exit full screen",
    "etape.debut": "Preparing the calculation",
    "etape.donnees": "Reading the area's data: {faites} / {total} tiles",
    "etape.fusion": "Merging official paths",
    "etape.tuiles": "Building the BRouter tile",
    "etape.analyse": "Analysing the crossings",
    "etape.itineraire": "Calculating the route",
    "etape.comparaison": "Standard route, for comparison",
    "etape.elargie": " (area enlarged)",
    "icone.depart": "S",
    "icone.arrivee": "F",
    "gpx.deniveleIndisponible": "gpx2elev elevation unavailable",
    "gpx.description": "Distance {km}, {denivele}, crossings to check: {n}. ",
    "gpx.barrieres": "Barriers © OpenStreetMap contributors",
    "gpx.trace": "; route by hike2gpx.",
    "gpx.aVerifier": "To check: {nature}",
    "erreur.zone_trop_etendue": "Area too large: {nombre} tiles of 0.05° to examine, {max} at most. Split the route into shorter stages.",
    "erreur.itineraire_refuse": "Route refused: it passes a {mot} crossing ({nature}, {distance} from the start).",
    "mot.bloquant": "blocking",
    "mot.strict": "to-check (strict mode)",
  },
};

// Textes fixes venus du serveur (raisons des franchissements, natures des
// barrières, messages de BRouter et d'erreur), dits en anglais tels quels.
// Un texte absent d'ici, comme le détail d'une panne réseau, reste en français.
const SERVEUR_EN = {
  "Entrée condamnée": "Entrance sealed",
  "Passage autorisé": "Passage allowed",
  "Accès soumis à des conditions ou horaires": "Access subject to conditions or opening hours",
  "Sens de la voie OSM indéterminé": "Direction of the OSM way undetermined",
  "Passage interdit dans ce sens": "No passage in this direction",
  "Accès interdit ou privé": "Access forbidden or private",
  "Entrée à usage ou sens limité": "Entrance with limited use or direction",
  "Portail verrouillé, passage autorisé à confirmer": "Locked gate, allowed passage to confirm",
  "Barrière verrouillée": "Locked barrier",
  "Accès limité ou à confirmer": "Limited access, or to confirm",
  "Ouverture cartographiée, accès à confirmer": "Mapped opening, access to confirm",
  "Ouverture cartographiée": "Mapped opening",
  "Obstacle linéaire traversé sans ouverture cartographiée": "Linear obstacle crossed with no mapped opening",
  "Obstacle physique pour ce mode de déplacement": "Physical obstacle for this travel mode",
  "Passage piéton possible": "Pedestrian passage possible",
  "Franchissement à vérifier sur place": "Crossing to check on site",
  "Sentier balisé : passage probable, à vérifier": "Marked trail: passage likely, to check",
  "Niveau de franchissement à confirmer": "Crossing level to confirm",
  "Clôture": "Fence", "Mur": "Wall", "Haie": "Hedge", "Portail": "Gate", "Barrière levante": "Lift gate",
  "Barrière pivotante": "Swing gate", "Échalier": "Stile", "Portillon": "Kissing gate", "Borne": "Bollard",
  "Chicane": "Cycle barrier", "Bloc": "Block", "Chaîne": "Chain", "Passage": "Passage", "Ouverture": "Opening",
  "Barrière": "Barrier",
  "Données BRouter absentes pour cette zone.": "BRouter data missing for this area.",
  "Aucun chemin praticable trouvé près d'un des points.": "No usable path found near one of the points.",
  "Aucun itinéraire ne respecte les barrières entre ces points.": "No route respects the barriers between these points.",
  "Le point d'arrivée est isolé du réseau praticable.": "The finish point is cut off from the usable network.",
  "Calcul trop long : rapprochez les points.": "Calculation too long: bring the points closer.",
  "Le moteur BRouter n'est pas installé.": "The BRouter engine is not installed.",
  "Le tracé sort sans cesse de la zone examinée : rapprochez les points.": "The route keeps leaving the examined area: bring the points closer.",
  "Zone invalide.": "Invalid area.",
  "Zone trop grande : zoomez davantage.": "Area too large: zoom in further.",
  "Point invalide.": "Invalid point.",
  "Il faut entre 2 et 50 points.": "Between 2 and 50 points are needed.",
  "Nom de tuile invalide.": "Invalid tile name.",
  "Clé IGN invalide : lettres, chiffres, _ et - seulement.": "Invalid IGN key: letters, digits, _ and - only.",
  "Données OSM ou chemins officiels de la zone indisponibles.": "OSM or official path data for this area unavailable.",
  "Hors connexion : les barrières de cette zone n'ont jamais été chargées.": "Offline: the barriers of this area were never loaded.",
  "Réponse Overpass trop volumineuse : barrières non vérifiées.": "Overpass response too large: barriers not checked.",
  "Extrait inconnu.": "Unknown extract.",
  "Cet extrait se télécharge déjà.": "This extract is already downloading.",
  "Échec récent : nouvel essai possible dans moins d'une heure.": "Recent failure: a new try will be possible within the hour.",
  "Un téléchargement BRouter est déjà en cours.": "A BRouter download is already running.",
  "Aucune tuile BRouter à actualiser.": "No BRouter tile to refresh.",
  "Action inconnue.": "Unknown action.",
};

let langue = "fr";

function t(cle, valeurs = {}) {
  const providers = Object.values(window.HIKE2GPX_MAP_PROVIDERS || {});
  const texteProvider = providers.map((p) => p.texts?.[langue]?.[cle]).find((s) => s !== undefined);
  let s = texteProvider ?? TEXTES[langue][cle] ?? TEXTES.fr[cle] ?? cle;
  for (const [k, v] of Object.entries(valeurs)) s = s.split(`{${k}}`).join(v);
  return s;
}

function ts(texte) {
  if (langue !== "en") return texte;
  const traduit = Object.values(window.HIKE2GPX_MAP_PROVIDERS || {})
    .map((p) => p.serverTexts?.[texte]).find((s) => s !== undefined);
  return traduit ?? SERVEUR_EN[texte] ?? texte;
}

function decimal(valeur, chiffres) {
  const s = Number(valeur).toFixed(chiffres);
  return langue === "en" ? s : s.replace(".", ",");
}

function km(metres) {
  return metres == null ? "?" : `${decimal(metres / 1000, 2)} km`;
}

// Erreur rendue par le serveur : son code, quand il en a un, se dit dans la
// langue de la page ; sinon le texte, traduit s'il est connu.
function texteErreur(r) {
  if (langue === "en" && r.code && TEXTES.en[`erreur.${r.code}`]) {
    const v = { ...(r.valeurs || {}) };
    if (r.code === "itineraire_refuse") {
      v.nature = ts(v.nature);
      v.mot = t(v.statut === "blocked" ? "mot.bloquant" : "mot.strict");
      v.distance = km(v.distance_m);
    }
    return t(`erreur.${r.code}`, v);
  }
  return ts(r.erreur);
}

function natureDe(f) {
  const cle = String(f.cle || "");
  const fournisseur = Object.values(FOURNISSEURS_CARTES).find((p) =>
    p.paths?.source && cle.startsWith(`${p.paths.source}-`));
  if (fournisseur) {
    return langue === "en" ? `${fournisseur.paths.label} path, ${f.longueur_m} m`
      : `Chemin ${fournisseur.paths.label} de ${f.longueur_m} m`;
  }
  return ts(f.nature);
}

function appliquerLangue(code) {
  langue = code === "en" ? "en" : "fr";
  document.documentElement.lang = langue;
  document.title = t("page.titre");
  $("panelTabs").setAttribute("aria-label", t("onglets.titre"));
  for (const el of document.querySelectorAll("[data-i18n]")) el.textContent = t(el.dataset.i18n);
  lienAide();
  afficherOptionsIgn();
  $("cityQuery").placeholder = t("recherche.placeholder");
  if ($("pleinEcran")) {
    $("pleinEcran").title = t(document.body.classList.contains("plein-ecran") ? "pleinEcran.quitter" : "pleinEcran.entrer");
  }
  rafraichirPoints();
  construireFonds();
  rafraichirCalques();
  afficherExtrait(etat.extrait);
  afficherDonnees();
  afficherEntreeHorsLigne();
  afficherStatut(...etat.statut);
  if (etat.dernier) ecrireResultat(etat.dernier);
  afficherDisponibilite(derniereDisponibilite);
  actualiserDisponibilite();
}

document.addEventListener("nico579-langue", (e) => appliquerLangue(e.detail.code));

// L'aide est le README de la version installée, dans la langue de la page :
// celui de main peut avoir pris de l'avance sur le programme.
function lienAide() {
  const fichier = langue === "en" ? "README.md" : "README.fr.md";
  $("aide").href = `https://github.com/nico579/hike2gpx/blob/${etat.version ? `v${etat.version}` : "main"}/${fichier}`;
  $("aide").title = t("aide.titre");
  $("aide").setAttribute("aria-label", t("aide.titre"));
}

async function api(route, corps, signal) {
  const options = corps === undefined ? { signal } : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(corps),
    signal,
  };
  const reponse = await fetch(`/api/${route}`, options);
  const donnees = await reponse.json().catch(() => ({}));
  if (!reponse.ok) throw new Error(donnees.error || `HTTP ${reponse.status}`);
  // Un calcul ou un calque a lancé de lui-même le lot du serveur de la zone :
  // la page suit son avancement, comme celui d'un lot demandé à la main.
  if (donnees.lot_en_cours?.auto && donnees.lot_en_cours.actif && !minuterieLot) suivreLot();
  return donnees;
}

// Le statut se réécrit au changement de langue : on garde de quoi le refaire,
// un texte ou une fonction qui le produit.
function afficherStatut(texte, erreur = false) {
  etat.statut = [texte, erreur];
  $("statut").textContent = typeof texte === "function" ? texte() : texte;
  $("statut").classList.toggle("erreur", erreur);
}

// ------------------------------------------------------------ carte

function lireVue() {
  try {
    const vue = JSON.parse(localStorage.getItem(CLE_VUE) || "null");
    if (vue && [vue.lat, vue.lon, vue.zoom].every(Number.isFinite)) return vue;
  } catch (e) { /* stockage indisponible : vue par défaut */ }
  return { lat: 46.6, lon: 2.5, zoom: 6 };
}

const vueInitiale = lireVue();
let paysCarte = Object.hasOwn(window.HIKE2GPX_MAP_PROVIDERS, vueInitiale.pays)
  ? vueInitiale.pays : (vueInitiale.hors_france === true ? "autre" : "fr");
let horsFrance = paysCarte !== "fr";
const carte = L.map("carte").setView([vueInitiale.lat, vueInitiale.lon], vueInitiale.zoom);
// L'échelle de la carte, dans l'en-tête à droite de la recherche de ville
// (demande de Nico du 2026-10-28) ; Leaflet la tient à jour où qu'elle soit.
const echelle = L.control.scale({ imperial: false, maxWidth: 120 }).addTo(carte).getContainer();
echelle.classList.add("echelle-entete");
$("citySubmit").after(echelle);
carte.on("contextmenu", (evenement) => {
  const { lat, lng } = evenement.latlng;
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
  const coordonnees = `${lat.toFixed(6)}, ${lng.toFixed(6)}`;
  const contenu = document.createElement("div");
  contenu.className = "map-coordinates-menu";
  const titre = document.createElement("label");
  titre.textContent = t("menu.coordonnees");
  const champ = document.createElement("input");
  champ.type = "text";
  champ.readOnly = true;
  champ.value = coordonnees;
  titre.append(champ);
  const bouton = document.createElement("button");
  bouton.type = "button";
  bouton.textContent = t("menu.copier");
  const retour = document.createElement("span");
  retour.setAttribute("role", "status");
  bouton.addEventListener("click", async () => {
    let copie = false;
    try {
      if (globalThis.navigator?.clipboard?.writeText) {
        await globalThis.navigator.clipboard.writeText(coordonnees);
        copie = true;
      }
    } catch (_) { /* le champ reste sélectionnable */ }
    if (!copie) {
      champ.focus();
      champ.select();
      copie = Boolean(document.execCommand?.("copy"));
    }
    retour.textContent = t(copie ? "menu.copie" : "menu.selection");
  });
  contenu.append(titre, bouton, retour);
  L.DomEvent.disableClickPropagation(contenu);
  L.popup({ className: "map-coordinates-popup", minWidth: 230 })
    .setLatLng(evenement.latlng).setContent(contenu).openOn(carte);
});
let sequenceRecherche = 0;
const resultatsVilles = $("cityResults");
function lireCoordonnees(recherche) {
  // Deux décimaux séparés par un point-virgule, une virgule ou un espace.
  // Le point-virgule permet aussi la virgule décimale française.
  const points = recherche.match(/^\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*$/);
  const parties = points ? [points[1], points[2]] : recherche.includes(";") ? recherche.split(";")
    : recherche.trim().split(/\s+/);
  if (parties.length !== 2) return null;
  if (!parties.every((p) => /^[+-]?\d+(?:[.,]\d+)?$/.test(p.trim()))) return null;
  const nombres = parties.map((p) => Number(p.trim().replace(",", ".")));
  return nombres.every(Number.isFinite) && Math.abs(nombres[0]) <= 90 && Math.abs(nombres[1]) <= 180
    ? nombres : null;
}
$("cityQuery").addEventListener("input", () => {
  sequenceRecherche++;
  resultatsVilles.hidden = true;
  $("citySubmit").disabled = false;
});
$("cityQuery").addEventListener("keydown", (e) => {
  if (e.key === "Escape") resultatsVilles.hidden = true;
});
$("citySearch").addEventListener("submit", async (e) => {
  e.preventDefault();
  const recherche = $("cityQuery").value.trim();
  if (recherche.length < 2) return;
  const coordonnees = lireCoordonnees(recherche);
  if (coordonnees) {
    ++sequenceRecherche;
    const [lat, lon] = coordonnees;
    carte.setView([lat, lon], 14);
    memoriserVue(lat, lon, 14);
    resultatsVilles.hidden = true;
    return;
  }
  const numero = ++sequenceRecherche;
  resultatsVilles.replaceChildren();
  resultatsVilles.textContent = t("recherche.attente");
  resultatsVilles.hidden = false;
  $("citySubmit").disabled = true;
  try {
    const reponse = await api("communes", { recherche });
    if (numero !== sequenceRecherche) return;
    if (reponse.erreur) throw new Error(reponse.erreur);
    resultatsVilles.replaceChildren();
    if (!reponse.communes.length) resultatsVilles.textContent = t("recherche.aucun");
    let premier = null;
    for (const ville of reponse.communes) {
      const bouton = document.createElement("button");
      bouton.type = "button";
      bouton.textContent = ville.detail ? `${ville.nom} · ${ville.detail}` : ville.nom;
      bouton.addEventListener("click", () => {
        choisirPays(Object.hasOwn(window.HIKE2GPX_MAP_PROVIDERS, ville.code_pays) ? ville.code_pays : "autre");
        carte.setView([ville.lat, ville.lon], 13);
        memoriserVue(ville.lat, ville.lon, 13);
        $("cityQuery").value = ville.nom;
        resultatsVilles.hidden = true;
      });
      resultatsVilles.append(bouton);
      premier ||= bouton;
    }
    if (reponse.communes.length === 1) premier.click();
  } catch (erreur) {
    if (numero === sequenceRecherche) resultatsVilles.textContent = t("recherche.erreur", { message: erreur.message });
  } finally {
    if (numero === sequenceRecherche) $("citySubmit").disabled = false;
  }
});
function memoriserVue(lat, lon, zoom) {
  try {
    localStorage.setItem(CLE_VUE, JSON.stringify({ lat, lon, zoom, pays: paysCarte, hors_france: horsFrance }));
  } catch (e) { /* sans importance */ }
}
carte.on("moveend", () => {
  const c = carte.getCenter();
  memoriserVue(c.lat, c.lng, carte.getZoom());
  actualiserDisponibilite();
});

let sequenceDisponibilite = 0;
let derniereDisponibilite = null;
function afficherDisponibilite(d) {
  derniereDisponibilite = d;
  const pret = Boolean(d?.pret);
  $("readiness").classList.toggle("available", pret);
  $("readiness").classList.toggle("unavailable", !pret);
  $("readinessText").textContent = t(pret ? "disponibilite.oui" : "disponibilite.non");
  $("readiness").title = pret ? (d.source === "lot" ? `${t("disponibilite.info.lot")} : ${d.nom}`
    : `OSM : ${d.source === "extrait" ? d.nom : d.source === "cache" ? "cache" : "Overpass"}`)
    : t(`disponibilite.attente.${d?.attente || "osm"}`);
  $("readinessInfo").setAttribute("aria-label", t("disponibilite.info.titre"));
  const details = d?.details;
  if (!details) {
    $("readinessInfoText").textContent = t("disponibilite.info.verification");
    return;
  }
  const extrait = (cle) => {
    const source = details[cle] || { etat: "non_applicable" };
    return `${t(`disponibilite.info.${cle}`)}${source.nom ? ` (${source.nom})` : ""} : `
      + t(`disponibilite.etat.${source.etat}`);
  };
  // Un lot installé (ou qui se télécharge) passe en tête : il sert seul.
  $("readinessInfoText").textContent = [t("disponibilite.info.titre"),
    ...(details.lot ? [extrait("lot")] : []),
    `${t("disponibilite.info.overpass")} : ${t(`disponibilite.etat.${details.overpass}`)}`,
    extrait("local"), extrait("regional"),
    `${t("disponibilite.info.brouter")} : ${t(d.attente === "moteur" || d.attente === "segments"
      ? "disponibilite.info.attente" : "disponibilite.info.pret")}`].join("\n");
}

async function actualiserDisponibilite() {
  const numero = ++sequenceDisponibilite;
  const centre = etat.points[0] || { lat: carte.getCenter().lat, lon: carte.getCenter().lng };
  const parametres = new URLSearchParams({ s: (centre.lat - 0.00001).toFixed(6),
    w: (centre.lon - 0.00001).toFixed(6), n: (centre.lat + 0.00001).toFixed(6),
    e: (centre.lon + 0.00001).toFixed(6) });
  try {
    const d = etat.points.length >= 2 ? await api("disponibilite", {
      points: etat.points.map((p) => [p.lat, p.lon]),
      ign: $("ign").checked && Boolean(FOURNISSEURS_CARTES[paysCarte]?.paths?.source),
      source: FOURNISSEURS_CARTES[paysCarte]?.paths?.source,
    }) : await api(`disponibilite?${parametres}`);
    if (numero === sequenceDisponibilite) afficherDisponibilite(d);
  } catch (e) {
    if (numero === sequenceDisponibilite) afficherDisponibilite(null);
  }
}
setInterval(actualiserDisponibilite, 10000);

const CLE_FOND = "hike2gpx.fond";
const FOURNISSEURS_CARTES = window.HIKE2GPX_MAP_PROVIDERS;
const CHEMINS_OFFICIELS = Object.fromEntries(Object.values(FOURNISSEURS_CARTES)
  .filter((fournisseur) => fournisseur.paths?.overlay)
  .map((fournisseur) => [fournisseur.paths.overlay, fournisseur.paths]));
const NOMS_CALQUES = Object.assign({}, ...Object.values(FOURNISSEURS_CARTES)
  .map((fournisseur) => ({ ...fournisseur.overlayNames,
    ...(fournisseur.paths?.overlay ? { [fournisseur.paths.overlay]: fournisseur.paths.name } : {}) })));
function nomCalque(cle) {
  return NOMS_CALQUES[cle]?.[langue] || t(`calque.${cle}`);
}
function nomFond(cle) {
  return FOURNISSEURS_CARTES[paysCarte]?.baseNames?.[cle]?.[langue] || t(`fond.${cle}`);
}
const LEGENDES_PROVIDERS = new Map();
for (const fournisseur of Object.values(FOURNISSEURS_CARTES)) {
  const entrees = [
    ...(fournisseur.paths?.overlay ? [[fournisseur.paths.overlay, fournisseur.paths.name,
      fournisseur.paths.legendStyle]] : []),
    ...(fournisseur.overlays || []).map((cle) => [cle, fournisseur.overlayNames?.[cle],
      fournisseur.overlayLegendStyles?.[cle]]),
  ];
  for (const [cle, noms, style] of entrees) {
    if (LEGENDES_PROVIDERS.has(cle)) continue;
    const ligne = document.createElement("li");
    ligne.dataset.mapOverlay = cle;
    ligne.hidden = true;
    const trait = document.createElement("span");
    trait.className = "trait";
    Object.assign(trait.style, style || { borderTop: "3px dashed #8650ac" });
    const libelle = document.createElement("span");
    libelle.textContent = ` ${noms?.fr || cle}`;
    ligne.append(trait, libelle);
    $("legendRows").append(ligne);
    LEGENDES_PROVIDERS.set(cle, { ligne, libelle, noms });
  }
}
function cheminsDisponibles(chemins, points = []) {
  if (!chemins?.bounds) return Boolean(chemins);
  const [s, w, n, e] = chemins.bounds;
  const positions = points.length ? points : [carte.getCenter()];
  return positions.every((p) => (p.lat ?? p[0]) >= s && (p.lat ?? p[0]) <= n
    && (p.lng ?? p.lon ?? p[1]) >= w && (p.lng ?? p.lon ?? p[1]) <= e);
}
let controleFonds = null;
let fondActif = null;
let couchesFonds = {};      // clé -> fond de carte Leaflet
function ajusterRecouvrementTuiles() {
  const surzoom = Math.max(0, carte.getZoom() - (fondActif?.options?.maxNativeZoom ?? carte.getZoom()));
  $("carte").style.setProperty("--tile-overlap", `${2 / 2 ** surzoom}px`);
}
carte.on("zoomend", ajusterRecouvrementTuiles);
carte.on("baselayerchange", (e) => {
  fondActif = e.layer;
  ajusterRecouvrementTuiles();
  const cle = Object.keys(couchesFonds).find((nom) => couchesFonds[nom] === e.layer);
  if (cle) {
    try { localStorage.setItem(`${CLE_FOND}.${paysCarte}`, cle); } catch (erreur) { /* stockage indisponible */ }
  }
});

// ------------------------------------------------------------ calques de chemins

// Le tracé et ses franchissements passent au-dessus des chemins dessinés.
carte.createPane("trace").style.zIndex = 450;
carte.createPane("sensTrace").style.zIndex = 451;
carte.createPane("gpxImporte").style.zIndex = 449;
carte.createPane("obstaclesOsm").style.zIndex = 452;
const traceGpxImporte = L.layerGroup();
let nomGpxImporte = null;
let sequenceImportGpx = 0;
const rendu = L.canvas({ padding: 0.2 });
const renduObstacles = L.canvas({ padding: 0.2, pane: "obstaclesOsm" });
const ZOOM_CALQUES = 14;
const CLE_CALQUES = "hike2gpx.calques";
// charge : bornes des tuiles déjà dessinées ; annulation : la requête en cours.
const CALQUES = Object.fromEntries(["osm", ...Object.keys(CHEMINS_OFFICIELS)]
  .map((cle) => [cle, { groupe: L.layerGroup(), charge: null, sequence: 0, annulation: null }]));
for (const [cle, chemins] of Object.entries(CHEMINS_OFFICIELS)) {
  if (chemins.attribution) CALQUES[cle].groupe.getAttribution = () => chemins.attribution;
}
const CALQUES_PAYS = Object.fromEntries(Object.values(FOURNISSEURS_CARTES)
  .flatMap((fournisseur) => Object.entries(fournisseur.calques || {})
    .map(([cle, creer]) => [cle, creer(L)])));
function calquesDuPays() {
  const fournisseur = FOURNISSEURS_CARTES[paysCarte];
  return [...(fournisseur?.overlays || []), ...(cheminsDisponibles(fournisseur?.paths)
    ? [fournisseur.paths.overlay] : [])];
}
function coucheCalque(cle) {
  return CALQUES[cle]?.groupe || CALQUES_PAYS[cle];
}
let changementPays = false;
function cochesCalques() {
  try {
    const sauves = JSON.parse(localStorage.getItem(CLE_CALQUES) || "null");
    if (Array.isArray(sauves)) {
      for (const fournisseur of Object.values(FOURNISSEURS_CARTES)) {
        for (const [ancien, nouveau] of Object.entries(fournisseur.legacyOverlays || {})) {
          if (sauves.includes(ancien) && !sauves.includes(nouveau)) sauves.push(nouveau);
        }
      }
      return sauves;
    }
  } catch (e) { /* préférence illisible */ }
  return ["osm", ...Object.values(FOURNISSEURS_CARTES).flatMap((fournisseur) =>
    [...(fournisseur.overlays || []), ...(fournisseur.paths?.overlay ? [fournisseur.paths.overlay] : [])])];
}
function memoriserCalques() {
  if (changementPays) return;
  const applicables = ["osm", ...calquesDuPays()];
  const coches = new Set(cochesCalques());
  for (const cle of applicables) {
    if (carte.hasLayer(coucheCalque(cle))) coches.add(cle);
    else coches.delete(cle);
  }
  try { localStorage.setItem(CLE_CALQUES, JSON.stringify([...coches])); }
  catch (e) { /* sans importance */ }
}
const STYLES_OSM = {
  sentier: { color: "#7b1fa2", weight: 3, dashArray: "6 4" },
  piste: { color: "#7b1fa2", weight: 3 },
  route: { color: "#7b1fa2", weight: 2, opacity: 0.45 },
};

function texte(contenu) {
  return document.createTextNode(contenu);   // jamais d'étiquette OSM ou IGN interprétée en HTML
}

const DESSINS = {
  osm(groupe, donnees) {
    for (const v of donnees.voies) {
      L.polyline(v.pts, { ...STYLES_OSM[v.genre], renderer: rendu, interactive: false }).addTo(groupe);
    }
    for (const b of donnees.barrieres) {
      L.polyline(b.pts, { color: "#e53935", weight: 3, renderer: rendu })
        .bindTooltip(texte(`${ts(b.nature)} (OSM)`), { sticky: true }).addTo(groupe);
    }
    for (const f of donnees.franchissements || []) {
      L.circleMarker([f.lat, f.lon], { radius: 6, weight: 2, color: "#fff", fillOpacity: 1,
        fillColor: COULEURS[f.statut], renderer: renduObstacles, pane: "obstaclesOsm" })
        .bindPopup(() => bulleFranchissement(f)).addTo(groupe);
    }
  },
};
for (const [cle, chemins] of Object.entries(CHEMINS_OFFICIELS)) {
  DESSINS[cle] = (groupe, donnees) => chemins.draw({ L, groupe, donnees, rendu, texte, t });
}

// Barre d'une note du panneau (préfixe de ses identifiants : noteCalques,
// extrait, brouter) : fraction de 0 à 1, null sans fraction connue (un
// segment va et vient), undefined pour la masquer.
function majPiste(prefixe, fraction) {
  const piste = $(`${prefixe}Piste`);
  piste.hidden = fraction === undefined;
  piste.classList.toggle("indeterminee", fraction === null);
  $(`${prefixe}Barre`).style.width = typeof fraction === "number"
    ? `${Math.round(100 * Math.min(1, Math.max(0, fraction)))}%` : "";
}

function noteCalques(message, fraction) {
  $("noteCalquesTexte").textContent = message || "";
  $("noteCalques").hidden = !message;
  majPiste("noteCalques", message ? fraction : undefined);
}

// Calques en cours de lecture (clé -> numéro de la vue et nom) : leur note
// montre l'avancement que publie le serveur (/api/progression : tuiles lues
// sur tant), relu toutes les 0,7 s tant qu'une lecture dure.
const lectures = new Map();
let minuterieLectures = null;

function afficherLectures(calques) {
  const noms = [...lectures.values()].map((l) => l.nom).join(t("liaison.et"));
  const suivis = [...lectures.keys()].map((cle) => calques?.[cle]).filter((l) => l?.total);
  if (!suivis.length) {
    noteCalques(t("calque.chargement", { nom: noms }), null);
    return;
  }
  const faites = suivis.reduce((somme, l) => somme + l.faites, 0);
  const total = suivis.reduce((somme, l) => somme + l.total, 0);
  const duree = Math.round(Math.max(...suivis.map((l) => l.duree_s)));
  noteCalques(t("calque.avancement", { nom: noms, faites, total, duree }), faites / total);
}

async function suivreLectures() {
  minuterieLectures = null;
  try {
    const p = await api("progression");
    if (lectures.size) afficherLectures(p.calques);
  } catch (e) { /* la barre n'est qu'une indication : le tour suivant réessaie */ }
  if (lectures.size && !minuterieLectures) minuterieLectures = setTimeout(suivreLectures, 700);
}

function debutLecture(cle, numero, nom) {
  lectures.set(cle, { numero, nom });
  afficherLectures(null);
  if (!minuterieLectures) minuterieLectures = setTimeout(suivreLectures, 700);
}

// Rend vrai s'il reste la lecture d'un autre calque.
function finLecture(cle, numero) {
  if (lectures.get(cle)?.numero === numero) lectures.delete(cle);
  if (!lectures.size) {
    clearTimeout(minuterieLectures);
    minuterieLectures = null;
  }
  return lectures.size > 0;
}

// La vue telle qu'affichée, sans marge : le serveur la complète déjà aux
// tuiles de 0,05° qui la couvrent, et renvoie leurs bornes.
function zoneVue() {
  const b = carte.getBounds();
  return { s: b.getSouth(), w: b.getWest(), n: b.getNorth(), e: b.getEast() };
}

function couvre(zone, vue) {
  return Boolean(zone) && zone.s <= vue.s && zone.w <= vue.w && zone.n >= vue.n && zone.e >= vue.e;
}

// Abandonne la vue en cours d'un calque : sa requête est coupée et une réponse
// encore en route ne redessine rien. Rend vrai si une lecture était en cours.
function abandonner(calque) {
  const enCours = Boolean(calque.annulation);
  calque.sequence += 1;
  if (calque.annulation) calque.annulation.abort();
  calque.annulation = null;
  lectures.delete(Object.keys(CALQUES).find((cle) => CALQUES[cle] === calque));
  return enCours;
}

// La date de chaque vue d'un calque (ms), strictement croissante, même d'un
// rechargement de la page à l'autre : le serveur ne lit que la plus récente,
// et refuse d'emblée une requête plus ancienne arrivée après elle.
let derniereVue = 0;
function dateDeVue() {
  derniereVue = Math.max(performance.timeOrigin + performance.now(), derniereVue + 0.001);
  return derniereVue;
}

// Le serveur arrête de lui-même la vue précédente quand une nouvelle arrive ;
// sans nouvelle vue (zoom trop faible, calque masqué), il faut le lui dire.
function arreterAuServeur(cles) {
  if (cles.length) api("arreter_calques", { calques: cles, vue: dateDeVue() }).catch(() => {});
}

async function chargerCalque(cle, zone) {
  const calque = CALQUES[cle];
  abandonner(calque);
  const numero = calque.sequence;
  const annulation = calque.annulation = new AbortController();
  const nom = nomCalque(cle);
  const parametres = new URLSearchParams([...Object.entries(zone).map(([k, v]) => [k, v.toFixed(5)]),
    ["vue", dateDeVue().toFixed(3)]]);
  debutLecture(cle, numero, `${nom.charAt(0).toLowerCase()}${nom.slice(1)}`);
  let donnees;
  try {
    donnees = await api(`${cle}?${parametres}`, undefined, annulation.signal);
  } catch (e) {
    finLecture(cle, numero);
    if (numero === calque.sequence) noteCalques(`${nom} : ${e.message}`);
    return;
  }
  const autres = finLecture(cle, numero);
  if (numero !== calque.sequence || !carte.hasLayer(calque.groupe)) return;
  calque.annulation = null;
  if (donnees.extrait_en_cours) majExtrait();   // le serveur vient de lancer l'extrait de la région
  if (donnees.code === "vue_remplacee") {
    // Remplacée par la vue d'une autre page ouverte sur le même serveur : la
    // note ne reste pas sur un chargement qui ne viendra pas.
    if (!autres) noteCalques("");
    return;
  }
  if (donnees.erreur) {
    noteCalques(`${nom} : ${ts(donnees.erreur)}`);
    return;
  }
  if (donnees.attente_lot) {
    // Le lot de la zone se télécharge : rien à la volée, le calque se relit
    // depuis le lot à son arrivée (suivreLot).
    calque.charge = null;
    noteCalques(t("horsLigne.attenteCalques"));
    return;
  }
  calque.groupe.clearLayers();
  DESSINS[cle](calque.groupe, donnees);
  // Les tuiles lues débordent la vue : tant qu'elle y reste, rien à redemander.
  const [s, w, n, e] = donnees.bornes || [zone.s, zone.w, zone.n, zone.e];
  calque.charge = { s, w, n, e };
  // L'autre calque encore en lecture garde sa note, que son suivi met à jour.
  if (!autres) noteCalques("");
}

async function rafraichirCalques() {
  const actifs = Object.keys(CALQUES).filter((cle) => carte.hasLayer(CALQUES[cle].groupe));
  if (!actifs.length) { noteCalques(""); return; }
  if (carte.getZoom() < ZOOM_CALQUES) {
    // Vider plutôt que garder un morceau de réseau : de loin, il ferait
    // croire que le reste de la carte n'a pas de chemins.
    const interrompus = actifs.filter((cle) => abandonner(CALQUES[cle]));
    for (const cle of actifs) {
      CALQUES[cle].groupe.clearLayers();
      CALQUES[cle].charge = null;
    }
    arreterAuServeur(interrompus);
    noteCalques(t("calque.zoom", { niveau: ZOOM_CALQUES }));
    return;
  }
  const vue = zoneVue();
  await Promise.all(actifs.filter((cle) => !couvre(CALQUES[cle].charge, vue))
    .map((cle) => chargerCalque(cle, vue)));
}

let minuterieCalques = null;
let cheminRegionalVisible = null;
carte.on("moveend", () => {
  const chemins = FOURNISSEURS_CARTES[paysCarte]?.paths;
  if (chemins?.bounds) {
    const visible = cheminsDisponibles(chemins);
    if (cheminRegionalVisible !== visible) {
      cheminRegionalVisible = visible;
      if (!visible) {
        const calque = CALQUES[chemins.overlay];
        calque.groupe.remove();
        if (abandonner(calque)) arreterAuServeur([chemins.overlay]);
        calque.groupe.clearLayers();
        calque.charge = null;
      } else restaurerCalques();
      construireFonds();
      afficherOptionsIgn();
    }
  }
  afficherOptionChemins();
  clearTimeout(minuterieCalques);
  minuterieCalques = setTimeout(rafraichirCalques, 400);
});
carte.on("overlayadd overlayremove", (e) => {
  const officiel = Object.keys(CALQUES_PAYS).find((cle) => CALQUES_PAYS[cle] === e.layer);
  if (officiel) { memoriserCalques(); return; }
  const cle = Object.keys(CALQUES).find((c) => CALQUES[c].groupe === e.layer);
  if (!cle) return;
  const calque = CALQUES[cle];
  if (e.type === "overlayremove") {
    if (abandonner(calque)) arreterAuServeur([cle]);
    calque.groupe.clearLayers();
    calque.charge = null;
  }
  memoriserCalques();
  rafraichirCalques();
});

function restaurerCalques() {
  const coches = cochesCalques();
  for (const cle of ["osm", ...calquesDuPays()]) {
    if (coches.includes(cle) && !carte.hasLayer(coucheCalque(cle))) coucheCalque(cle).addTo(carte);
  }
}

function choisirPays(pays) {
  if (paysCarte === pays) return;
  ++sequenceExtrait;
  changementPays = true;
  // Les retraits automatiques de calques ne changent pas leurs préférences.
  for (const cle of Object.keys(CHEMINS_OFFICIELS)) {
    const calque = CALQUES[cle];
    calque.groupe.remove();
    if (abandonner(calque)) arreterAuServeur([cle]);
    calque.groupe.clearLayers();
    calque.charge = null;
  }
  for (const couche of Object.values(CALQUES_PAYS)) couche.remove();
  paysCarte = pays;
  cheminRegionalVisible = cheminsDisponibles(FOURNISSEURS_CARTES[paysCarte]?.paths);
  horsFrance = pays !== "fr";
  afficherOptionsIgn();
  restaurerCalques();
  construireFonds();
  changementPays = false;
}

function afficherOptionsIgn() {
  const chemins = FOURNISSEURS_CARTES[paysCarte]?.paths;
  $("legendIgn").hidden = !chemins?.source;
  if (chemins?.legend) $("legendOfficielTexte").textContent = chemins.legend[langue];
  afficherOptionChemins();
  for (const [cle, { ligne, libelle, noms }] of LEGENDES_PROVIDERS) {
    ligne.hidden = !calquesDuPays().includes(cle);
    libelle.textContent = ` ${noms?.[langue] || cle}`;
  }
}

function afficherOptionChemins() {
  const fournisseur = FOURNISSEURS_CARTES[paysCarte];
  const disponible = cheminsDisponibles(fournisseur?.paths);
  const couche = (disponible && fournisseur?.paths?.overlay) || fournisseur?.overlays?.[0];
  $("ignOption").hidden = !couche;
  const routable = Boolean(disponible && fournisseur?.paths?.source);
  $("ign").disabled = !routable;
  $("ign").checked = routable && choixIgn;
  if (couche) $("ignOptionTexte").textContent = t(routable ? "option.cheminsRoutables" : "option.cheminsAffichage",
    { nom: routable ? (fournisseur.paths.routeName || fournisseur.paths.name)[langue] : nomCalque(couche) });
}

// ------------------------------------------------------------ données OSM hors ligne

// L'extrait OSM du centre de la carte (le département d'OSM France, osmfr.py,
// sinon une région de Geofabrik, geofabrik.py), en cours de téléchargement ou
// installé. Le serveur le télécharge de lui-même
// dès qu'un calcul ou le calque des chemins OSM sert dans la région ; une fois
// installé, il y remplace Overpass.
const ZOOM_EXTRAIT = 10;
let minuterieExtrait = null;
let sequenceExtrait = 0;
let essaisPays = 0;

function dateCourte(iso) {
  return new Date(iso).toLocaleDateString(langue === "en" ? "en-GB" : "fr-FR");
}

// Ce que le serveur télécharge en ce moment : l'extrait OSM, le moteur ou des
// tuiles BRouter.
function extraitActif(r) {
  return Boolean(r?.en_cours && ["telechargement", "import"].includes(r.en_cours.etape));
}

function brouterActif(r) {
  return Boolean(r?.brouter && (r.brouter.moteur || r.brouter.segments?.length));
}

function quoiBrouter(b) {
  return [...(b.moteur ? [t("brouter.moteur")] : []), ...(b.segments || [])].join(", ");
}

// forcer : lire l'état même au zoom faible (lancement de la page, calcul en attente).
async function majExtrait(forcer = false) {
  clearTimeout(minuterieExtrait);
  const numero = ++sequenceExtrait;
  const enCours = extraitActif(etat.extrait) || brouterActif(etat.extrait) || etat.donneesAttendues;
  if (carte.getZoom() < ZOOM_EXTRAIT && !enCours && !forcer) { afficherExtrait(null); return; }
  const parametres = new URLSearchParams(Object.entries(zoneVue()).map(([k, v]) => [k, v.toFixed(5)]));
  try {
    const resultat = await api(`extrait?${parametres}`);
    if (numero !== sequenceExtrait) return;
    if (resultat.pays) {
      essaisPays = 0;
      choisirPays(resultat.pays);
    } else if (typeof resultat.hors_france === "boolean") {
      choisirPays(resultat.hors_france ? "autre" : "fr");
      essaisPays = resultat.hors_france ? essaisPays + 1 : 0;
    } else {
      ++essaisPays;
    }
    afficherExtrait(resultat);
    // L'index des contours français peut encore se préparer au premier usage.
    if (essaisPays && essaisPays <= 30 && !minuterieExtrait) {
      minuterieExtrait = setTimeout(() => majExtrait(true), 3000);
    }
  } catch (e) { /* serveur momentanément injoignable : la ligne reste telle quelle */ }
}

function afficherExtrait(r) {
  const avant = extraitActif(etat.extrait) ? etat.extrait.en_cours.id : null;
  const avantInstalle = Boolean(etat.extrait?.installe);
  etat.extrait = r;
  if (r?.installe && !avantInstalle) actualiserDisponibilite();
  const e = r?.en_cours;
  const actif = extraitActif(r);
  // L'extrait suivi jusqu'ici a fini, même si la région de Geofabrik part
  // aussitôt prendre le relais du département (cascade du 2026-10-20).
  const fini = avant !== null && !(actif && e.id === avant);
  // L'extrait vient de s'installer pendant que les chemins OSM se lisaient
  // encore : leur lecture, partie avant lui, attendait Overpass (deux minutes
  // le 2026-10-20) ; relancée, elle lit l'extrait.
  if (fini && r?.installe && lectures.has("osm")) chargerCalque("osm", zoneVue());
  const nombre = (n) => Number(n).toLocaleString(langue === "en" ? "en-GB" : "fr-FR");
  if (actif && e.relais && r?.installe) {
    // Le département sert déjà ; sa région se prépare pour prendre le relais.
    const sert = { nom: r.installe.nom, date: dateCourte(r.installe.date), region: e.nom };
    $("extraitTexte").textContent = e.etape === "telechargement"
      ? t("extrait.relais.telechargement", { ...sert, pourcent: Math.round(100 * e.fraction) })
      : t("extrait.relais.import", { ...sert, voies: nombre(e.voies) });
  } else if (actif) {
    $("extraitTexte").textContent = e.etape === "telechargement"
      ? t("extrait.telechargement", { nom: e.nom, pourcent: Math.round(100 * e.fraction) })
      : t("extrait.import", { nom: e.nom, voies: nombre(e.voies) });
  } else if (r?.installe) {
    $("extraitTexte").textContent = t("extrait.installe", { nom: r.installe.nom, date: dateCourte(r.installe.date),
      jours: etat.renouvellementJours ?? 30 });
  } else if (e?.etape === "erreur") {
    $("extraitTexte").textContent = t("extrait.erreur", { nom: e.nom, message: e.erreur });
  }
  $("extraitOsm").hidden = !(actif || r?.installe || e?.etape === "erreur");
  // Le téléchargement a sa fraction ; l'import, dont on ne sait pas le nombre
  // de voies d'avance, un segment qui va et vient.
  majPiste("extrait", actif ? (e.etape === "telechargement" ? e.fraction : null) : undefined);
  const moteur = brouterActif(r);
  if (moteur) $("brouterTexte").textContent = t("brouter.enCours", { quoi: quoiBrouter(r.brouter) });
  $("brouterEnCours").hidden = !moteur;
  if (actif || moteur) minuterieExtrait = setTimeout(majExtrait, 1500);
  // Les données qu'attendait un calcul sont arrivées : le calcul reprend,
  // sans attendre la région qui se prépare ensuite pour prendre le relais.
  if (etat.donneesAttendues && !moteur && !(actif && e.id === etat.donneesAttendues.extrait)) {
    etat.donneesAttendues = false;
    if (etat.points.length >= 2) planifierCalcul();
  }
}

carte.on("moveend", () => {
  ++sequenceExtrait;
  essaisPays = 0;
  clearTimeout(minuterieExtrait);
  minuterieExtrait = setTimeout(() => majExtrait(true), 600);
});

// Fonds de carte et contrôle des calques, refaits quand la clé IGN ou la
// langue change ; le fond affiché reste le même.
function construireFonds() {
  let clePreferee = null;
  try {
    clePreferee = localStorage.getItem(`${CLE_FOND}.${paysCarte}`)
      || (paysCarte === "fr" ? localStorage.getItem(CLE_FOND) : null);
  } catch (erreur) { /* fond par défaut */ }
  couchesFonds = {};
  Object.assign(couchesFonds, FOURNISSEURS_CARTES[paysCarte].bases({ L, cleIgn: etat.cleIgn }));
  couchesFonds.osmRando = L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    { maxNativeZoom: 17, maxZoom: 19,
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>, SRTM '
        + '| © <a href="https://opentopomap.org/">OpenTopoMap</a> (CC-BY-SA)' });
  couchesFonds.osm = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    { maxNativeZoom: 19, maxZoom: 19,
      attribution: `© <a href="https://www.openstreetmap.org/copyright">${t("attribution.osm")}</a>` });
  couchesFonds.satellite = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { maxNativeZoom: 19, maxZoom: 19,
      attribution: 'Esri, Vantor, Earthstar Geographics, and the GIS User Community' });
  if (fondsInstalles.length) couchesFonds.horsLigne = coucheHorsLigne();
  // presentation.js place la légende dans le contrôle Leaflet. La récupérer
  // avant de le retirer, sinon elle disparaît du DOM au changement de pays.
  const legende = $("mapLegend");
  if (legende && controleFonds) document.body.append(legende);
  if (controleFonds) controleFonds.remove();
  if (fondActif) fondActif.remove();
  const defaut = FOURNISSEURS_CARTES[paysCarte].defaultBase;
  const choix = (clePreferee && couchesFonds[clePreferee]) ? clePreferee : defaut;
  fondActif = (couchesFonds[choix] || couchesFonds.plan || couchesFonds.osm).addTo(carte);
  ajusterRecouvrementTuiles();
  const fonds = Object.fromEntries(Object.entries(couchesFonds).map(([cle, couche]) => [nomFond(cle), couche]));
  const calques = Object.fromEntries(Object.entries(CALQUES)
    .filter(([cle]) => cle === "osm" || calquesDuPays().includes(cle))
    .map(([cle, c]) => [nomCalque(cle), c.groupe]));
  for (const cle of calquesDuPays()) {
    if (CALQUES_PAYS[cle]) calques[nomCalque(cle)] = CALQUES_PAYS[cle];
  }
  if (nomGpxImporte) calques[echapper(nomGpxImporte)] = traceGpxImporte;
  controleFonds = L.control.layers(fonds, calques, { collapsed: false, position: "topright" }).addTo(carte);
}

// ------------------------------------------------------------ hors ligne
// Les cases BRouter de 5° prêtes hors ligne (lots installés), dessinées sur
// la carte depuis les réglages comme les mailles du serveur. Un clic sur une
// case la prépare : le serveur fabrique son lot en tâche de fond (fabrication.py)
// et la note de l'onglet Parcours en suit l'avancement.
const CASE_DEG = 5;
const CLE_CASES = "hike2gpx.casesHorsLigne";
// Au-dessus des calques (400) et des panneaux du tracé et des franchissements
// (449 à 452), dont les canevas couvrent la carte et prendraient les clics,
// mais sous les points du parcours (600). Grille affichée, ses cases
// reçoivent les clics ; décochée, la carte revient au tracé.
carte.createPane("casesHorsLigne").style.zIndex = 455;
const grilleCases = L.layerGroup();
let lotsInstalles = [];
let lotsServeur = [];            // le catalogue du dépôt (catalogue_lots), avec l'état de chaque lot ici
let lotEnCours = { actif: false };
let minuterieLot = null;
let lotSuivi = false;       // un lot suivi était en cours : à sa fin, calques et calcul repartent
// Les fonds de carte téléchargés sur ce PC (fonds.py) : un MBTiles chacun,
// servi tuile par tuile par /fonds/<nom>/{z}/{x}/{y}, sans réseau.
let fondsInstalles = [];

// Un seul fond « Carte hors ligne » : une couche par fichier, bornée à sa
// zone, la case sous ses vues, chacune agrandie au-delà de son zoom le plus fin.
function coucheHorsLigne() {
  const groupe = L.layerGroup();
  const ordre = [...fondsInstalles].sort((a, b) => a.zoom[1] - b.zoom[1]);
  for (const f of ordre) {
    const [s, o, n, e] = f.zone;
    L.tileLayer(`/fonds/${encodeURIComponent(f.nom)}/{z}/{x}/{y}`, { bounds: [[s, o], [n, e]],
      minNativeZoom: f.zoom[0], maxNativeZoom: f.zoom[1], maxZoom: 19,
      attribution: '© <a href="https://www.ign.fr/">IGN</a>' }).addTo(groupe);
  }
  return groupe;
}

// Relus au démarrage et après chaque préparation : un fond de plus ou de
// moins refait le contrôle des fonds.
async function chargerFonds() {
  try {
    const avant = JSON.stringify(fondsInstalles.map((f) => f.nom));
    fondsInstalles = (await api("hors_ligne")).fonds || [];
    if (JSON.stringify(fondsInstalles.map((f) => f.nom)) !== avant) construireFonds();
  } catch (_) { /* serveur injoignable : pas de fond hors ligne */ }
}

function nomCase(lat, lon) {
  const la = Math.floor(lat / CASE_DEG) * CASE_DEG, lo = Math.floor(lon / CASE_DEG) * CASE_DEG;
  return `${lo < 0 ? "W" : "E"}${Math.abs(lo)}_${la < 0 ? "S" : "N"}${Math.abs(la)}`;
}

function boiteCase(nom) {
  const [, est, lon, nord, lat] = nom.match(/^([EW])(\d+)_([NS])(\d+)$/);
  const o = Number(lon) * (est === "W" ? -1 : 1), s = Number(lat) * (nord === "S" ? -1 : 1);
  return [s, o, s + CASE_DEG, o + CASE_DEG];
}

function casesVisibles() {
  const b = carte.getBounds();
  const noms = [];
  for (let lat = Math.floor(b.getSouth() / CASE_DEG) * CASE_DEG; lat < b.getNorth(); lat += CASE_DEG) {
    for (let lon = Math.floor(b.getWest() / CASE_DEG) * CASE_DEG; lon < b.getEast(); lon += CASE_DEG) {
      noms.push(nomCase(lat, lon));
    }
  }
  return noms.slice(0, 60);       // au plus 60 cases : au-delà, la carte est trop dézoomée pour choisir
}

function etatCase(nom) {
  if (lotEnCours.actif && lotEnCours.case === nom) return "preparation";
  if (lotsInstalles.some((l) => l.case === nom)) return "prete";
  return lotsServeur.some((l) => l.case === nom) ? "serveur" : "absente";
}

// Sur un fond chargé (SCAN 25, relief), un voile de 5 à 8 % ne se voyait
// pas : les cases prêtes et celles du serveur ont un trait plein et épais et
// un fond franc ; seule la case vide reste discrète.
const STYLES_CASE = {
  prete: { color: "#1b7a3e", weight: 3.5, fillColor: "#23a04f", fillOpacity: 0.3 },
  preparation: { color: "#e07b00", weight: 3.5, dashArray: "8 5", fillColor: "#e07b00", fillOpacity: 0.25 },
  // Un fond presque transparent : un clic dans la case ouvre sa bulle, comme
  // les mailles du serveur ; décocher la grille rend les clics au tracé.
  absente: { color: "#37474f", weight: 1.5, dashArray: "5 5", fillColor: "#37474f", fillOpacity: 0.03 },
  // Pas encore ici, mais publiée par le serveur : un clic propose de la télécharger.
  serveur: { color: "#1565c0", weight: 3, fillColor: "#1e88e5", fillOpacity: 0.18 },
};

function tailleTexte(octets) {
  return `${Math.round((octets || 0) / 1e6)} ${t("unite.mo")}`;
}

function dureeTexte(secondes) {
  return secondes < 60 ? `${secondes} s` : `${Math.round(secondes / 60)} min`;
}

function bouton(texteBouton, action) {
  const b = document.createElement("button");
  b.type = "button";
  b.textContent = texteBouton;
  b.addEventListener("click", action);
  return b;
}

function bulleCase(nom) {
  const div = document.createElement("div");
  div.className = "bulle";
  div.append(paragraphe(t("horsLigne.case", { nom }), true));
  const lotCase = lotsInstalles.find((l) => l.case === nom);
  const etatActuel = etatCase(nom);
  if (etatActuel === "preparation") {
    div.append(paragraphe(t("horsLigne.enPreparation")), bouton(t("horsLigne.arreter"), arreterLot));
    return div;
  }
  // Une case que publie le serveur se télécharge (d'elle-même, ou tout de
  // suite) : la préparer ici, une heure de calcul, n'aurait pas de sens.
  const surServeur = lotsServeur.find((l) => l.case === nom);
  div.append(paragraphe(lotCase
    ? t("horsLigne.prete", { taille: tailleTexte(lotCase.octets), date: (lotCase.sources?.osm || "").slice(0, 10) })
    : t(surServeur ? "horsLigne.absenteServeur" : "horsLigne.absente")));
  const [s, o, n, e] = boiteCase(nom);
  const b = carte.getBounds();
  const vueDansCase = b.getSouth() >= s && b.getNorth() <= n && b.getWest() >= o && b.getEast() <= e;
  if (vueDansCase && !surServeur) {
    div.append(bouton(t("horsLigne.preparerVue"), () => preparerCase(nom,
      [b.getSouth(), b.getWest(), b.getNorth(), b.getEast()])));
  }
  if (!surServeur) {
    div.append(bouton(lotCase ? t("horsLigne.mettreAJour") : t("horsLigne.preparerCase"), () => preparerCase(nom)));
  }
  if (surServeur) {
    const officiels = Object.entries(surServeur.sources || {}).find(([cle]) => !["osm", "relief", "rd5"].includes(cle));
    div.append(paragraphe(t("horsLigne.serveur", { taille: tailleTexte(surServeur.octets),
      osm: (surServeur.sources?.osm || "").slice(0, 10),
      officiels: officiels ? t("horsLigne.serveurOfficiels", { date: String(officiels[1]).slice(0, 10) }) : "" })));
    if (surServeur.etat === "a_jour") div.append(paragraphe(t("horsLigne.serveurAJour")));
    else div.append(bouton(t(surServeur.etat === "ancien" ? "horsLigne.telechargerMaj" : "horsLigne.telechargerMaintenant"),
      () => telechargerCase(nom)));
  }
  if (paysCarte === "fr") ajouterFonds(div, nom, vueDansCase ? [b.getSouth(), b.getWest(), b.getNorth(), b.getEast()] : null);
  // Un voyage fini, une case qu'on ne visitera plus : son lot et ses fonds
  // quittent l'ordinateur (décision de Nico du 2026-10-28).
  const fondsIci = fondsInstalles.filter((f) => f.nom.startsWith(`${nom}-`));
  if (lotCase || fondsIci.length) {
    const octets = (lotCase?.octets || 0) + fondsIci.reduce((somme, f) => somme + (f.octets || 0), 0);
    div.append(bouton(t("horsLigne.supprimer"), () => supprimerCase(nom, octets)));
  }
  return div;
}

async function supprimerCase(nom, octets) {
  if (!confirm(t("horsLigne.confirmerSuppression", { nom, taille: tailleTexte(octets) }))) return;
  carte.closePopup();
  const r = await api("supprimer_case", { case: nom });
  afficherLot(r.erreur ? { case: nom, erreur: r.erreur } : {});
  if (!r.erreur) {
    $("lotHorsLigneTexte").textContent = t("horsLigne.supprimee", { nom, taille: tailleTexte(r.octets) });
    $("lotHorsLigne").hidden = false;
  }
  await chargerLots();
  chargerFonds();
}

// Le fond de la page, hors ligne : le SCAN 25 avec la clé IGN, le Plan IGN
// sans. Il reste sur ce PC (et son téléphone), jamais publié.
function ajouterFonds(div, nom, vue) {
  const ici = fondsInstalles.filter((f) => f.nom.startsWith(`${nom}-`));
  if (ici.length) {
    div.append(paragraphe(t("horsLigne.fonds", { liste: ici.map((f) =>
      `${t(f.nom.includes("-vue-") ? "horsLigne.fondVue" : "horsLigne.fondCase")} ${f.source === "scan25" ? "SCAN 25" : "Plan IGN"}`
      + ` ${tailleTexte(f.octets)}`).join(", ") })));
  }
  const source = etat.cleIgn ? "SCAN 25" : "Plan IGN";
  if (vue) div.append(bouton(t("horsLigne.preparerFondVue", { source }), () => preparerFond(nom, vue)));
  div.append(bouton(t("horsLigne.preparerFondCase", { source, duree: "45 min" }), () => preparerFond(nom)));
}

// ------------------------------------------------------------ partage au téléphone
// Le PC sert ses lots et ses fonds sur le Wi-Fi (partage.py), fermé par
// défaut. Le QR code porte l'adresse du catalogue et un jeton tiré à chaque
// ouverture ; il est dessiné par le serveur (SVG).
function afficherPartage(r) {
  etat.partage = r;
  $("partagerTelephone").hidden = Boolean(r.ouvert);
  $("partageOuvert").hidden = !r.ouvert;
  $("partageQr").innerHTML = r.ouvert ? r.qr : "";
  $("partageTexte").textContent = r.erreur ? t("partage.erreur", { erreur: ts(r.erreur) })
    : r.ouvert ? t("partage.ouvert", { lots: r.lots.length, fonds: r.fonds.length, taille: tailleTexte(r.octets) }) : "";
  $("partageTexte").hidden = !$("partageTexte").textContent;
}

async function basculerPartage(ouvrir) {
  try {
    afficherPartage(await api("partage", { ouvrir }));
  } catch (e) {
    afficherPartage({ ouvert: false, erreur: e.message });
  }
}
$("partagerTelephone").addEventListener("click", () => basculerPartage(true));
$("fermerPartage").addEventListener("click", () => basculerPartage(false));

async function preparerFond(nom, zone = null) {
  carte.closePopup();
  const reponse = await api("preparer_fond", zone ? { case: nom, zone } : { case: nom });
  if (reponse.erreur) {
    afficherLot({ case: nom, erreur: reponse.erreur });
    return;
  }
  if (minuterieLot) clearTimeout(minuterieLot);
  suivreLot();
}

async function telechargerCase(nom) {
  carte.closePopup();
  const reponse = await api("telecharger_lot", { case: nom });
  if (reponse.erreur) {
    afficherLot({ case: nom, erreur: reponse.erreur });
    return;
  }
  if (minuterieLot) clearTimeout(minuterieLot);
  suivreLot();
}

function dessinerCases() {
  grilleCases.clearLayers();
  if (!$("showOfflineGrid").checked) return;
  for (const nom of casesVisibles()) {
    const [s, o, n, e] = boiteCase(nom);
    L.rectangle([[s, o], [n, e]], { pane: "casesHorsLigne", bubblingMouseEvents: false,
      ...STYLES_CASE[etatCase(nom)] })
      .bindPopup(() => bulleCase(nom)).addTo(grilleCases);
  }
}

function afficherStatutCases() {
  const statut = $("offlineGridStatus");
  if (!$("showOfflineGrid").checked) { statut.textContent = ""; return; }
  statut.textContent = lotsInstalles.length
    ? t("reglages.casesNombre", { nombre: lotsInstalles.length }) : t("reglages.casesAucune");
}

async function chargerLots() {
  // Grille masquée : rien à lire, seulement à effacer.
  if ($("showOfflineGrid").checked) {
    try {
      lotsInstalles = (await api("hors_ligne")).lots || [];
    } catch (_) { /* serveur injoignable : la grille reste vide */ }
    // Le catalogue du dépôt vient de GitHub, parfois en quelques secondes : la
    // grille n'attend pas, elle se redessine à son arrivée.
    api("catalogue_lots").then((r) => { lotsServeur = r.lots || []; dessinerCases(); })
      .catch(() => { lotsServeur = []; });
  }
  afficherStatutCases();
  dessinerCases();
}

function basculerCases() {
  try { localStorage.setItem(CLE_CASES, $("showOfflineGrid").checked ? "1" : "0"); }
  catch (_) { /* réglage de carte non persistant */ }
  if ($("showOfflineGrid").checked) grilleCases.addTo(carte); else grilleCases.remove();
  afficherEntreeHorsLigne();
  chargerLots();
}
// Les cases font 5° : de près, on n'en voit qu'un morceau. Afficher la grille
// dézoome jusqu'à en montrer plusieurs (demande de Nico du 2026-10-28) ; la
// grille restaurée au chargement de la page garde la vue.
const ZOOM_CASES = 6;
function montrerCases() {
  if ($("showOfflineGrid").checked && carte.getZoom() > ZOOM_CASES) carte.setZoom(ZOOM_CASES);
}
$("showOfflineGrid").addEventListener("change", () => { basculerCases(); montrerCases(); });

// L'entrée du mode hors ligne, sur la carte : le bouton « Hors ligne » fait
// la même chose que la case des réglages (les deux restent d'accord), et dit
// en une ligne ce qu'on peut faire d'une case.
function afficherEntreeHorsLigne() {
  const active = $("showOfflineGrid").checked;
  $("offlineButton").setAttribute("aria-pressed", String(active));
  $("offlineButton").classList.toggle("actif", active);
  $("offlineButton").title = t("horsLigne.boutonTitre");
  $("offlineHint").textContent = active ? t("horsLigne.aide") : "";
  $("offlineHint").hidden = !active;
}
$("offlineButton").addEventListener("click", () => {
  $("showOfflineGrid").checked = !$("showOfflineGrid").checked;
  basculerCases();
  montrerCases();
});
carte.on("moveend", dessinerCases);

function afficherLot(r) {
  const nom = r.case || "";
  let message = "";
  if (r.actif) {
    // Un téléchargement compte en octets, une fabrication en tuiles ou mailles.
    const compte = !r.total ? "" : r.etape === "telechargement"
      ? ` ${tailleTexte(r.faites)} / ${tailleTexte(r.total)}` : ` ${r.faites}/${r.total}`;
    const duree = dureeTexte(r.duree_s || 0);
    message = r.auto && r.etape === "telechargement" ? t("horsLigne.automatique", { nom, compte, duree })
      : t("horsLigne.avancement", { nom, etape: t(`horsLigne.etape.${r.etape}`), compte, duree });
  } else if (r.erreur) {
    message = t("horsLigne.erreur", { nom, erreur: ts(r.erreur) });
  } else if (r.etape === "fini") {
    message = r.fond ? t("horsLigne.fondFini", { nom: r.fond }) : t("horsLigne.fini", { nom });
  }
  $("lotHorsLigneTexte").textContent = message;
  $("lotHorsLigne").hidden = !message;
  $("arreterLot").hidden = !r.actif;
  $("majLot").hidden = $("plusTardLot").hidden = true;
  majPiste("lotHorsLigne", r.actif ? (r.total ? r.faites / r.total : null) : undefined);
}

// Règle unique : un lot qui couvre la zone sert seul. Trop vieux, il ne se
// renouvelle pas tout seul comme les caches : on demande. « Plus tard » vaut
// pour la séance. Le lot est refait sur sa zone, avec les fournisseurs
// nationaux qui la touchent.
const lotsReportes = new Set();
let lotPerime = null;

function proposerMiseAJour(lotUtilise) {
  if (!lotUtilise?.perime || lotsReportes.has(lotUtilise.case) || lotEnCours?.actif) return;
  lotPerime = lotUtilise;
  $("lotHorsLigneTexte").textContent = t("horsLigne.perime",
    { nom: lotUtilise.case, date: (lotUtilise.sources?.osm || "").slice(0, 10) });
  $("lotHorsLigne").hidden = false;
  $("arreterLot").hidden = true;
  $("majLot").hidden = $("plusTardLot").hidden = false;
}

$("majLot").addEventListener("click", () => {
  // Un lot enrichi de l'ancienne chaîne n'a pas de zone : son emprise enrichie.
  if (lotPerime) preparerCase(lotPerime.case, lotPerime.zone || lotPerime.emprise_enrichie);
});
$("plusTardLot").addEventListener("click", () => {
  if (lotPerime) lotsReportes.add(lotPerime.case);
  $("lotHorsLigne").hidden = true;
});

async function suivreLot() {
  minuterieLot = null;
  try {
    lotEnCours = await api("lot_en_cours");
  } catch (_) {
    return;
  }
  afficherLot(lotEnCours);
  if (lotEnCours.actif) {
    lotSuivi = true;
    minuterieLot = setTimeout(suivreLot, 2000);
    dessinerCases();
  } else {
    await chargerLots();
    chargerFonds();         // sans l'attendre : la grille est déjà à jour
    if (lotSuivi) {
      // Le lot est arrivé (ou a échoué) : les calques et le calcul qui
      // l'attendaient repartent, sur lui ou à la volée.
      lotSuivi = false;
      rafraichirCalques();
      if (etat.attenteLot) {
        etat.attenteLot = false;
        if (etat.points.length >= 2) planifierCalcul();
      }
    }
  }
}

async function preparerCase(nom, zone = null) {
  carte.closePopup();
  // Le serveur prend tous les fournisseurs nationaux qui touchent la zone.
  const reponse = await api("preparer_lot", zone ? { case: nom, zone } : { case: nom });
  if (reponse.erreur) {
    afficherLot({ case: nom, erreur: reponse.erreur });
    return;
  }
  if (minuterieLot) clearTimeout(minuterieLot);
  suivreLot();
}

async function arreterLot() {
  carte.closePopup();
  await api("arreter_lot", {});
  if (minuterieLot) clearTimeout(minuterieLot);
  suivreLot();
}
$("arreterLot").addEventListener("click", arreterLot);

function restaurerCases() {
  try { $("showOfflineGrid").checked = localStorage.getItem(CLE_CASES) === "1"; }
  catch (_) { /* pas de préférence */ }
  if ($("showOfflineGrid").checked) grilleCases.addTo(carte);
  afficherEntreeHorsLigne();
  chargerLots();
  suivreLot();
}

// ------------------------------------------------------------ points

const couches = L.layerGroup().addTo(carte);
const fleches = L.layerGroup().addTo(carte);
let flechesTrace = [];
carte.on("zoomend", () => afficherFleches());

function preparerFleches(coordonnees) {
  const segments = [];
  let total = 0;
  for (let i = 1; i < coordonnees.length; i++) {
    const depart = coordonnees[i - 1];
    const arrivee = coordonnees[i];
    const longueur = L.latLng([depart[1], depart[0]]).distanceTo(L.latLng([arrivee[1], arrivee[0]]));
    if (longueur > 0) {
      segments.push({ depart, arrivee, debut: total, fin: total + longueur });
      total += longueur;
    }
  }
  if (!total) return [];
  const ecart = Math.max(300, total / 9);
  const cibles = [];
  for (let distance = ecart / 2; distance < total - ecart / 2; distance += ecart) cibles.push(distance);
  if (!cibles.length) cibles.push(total / 2);
  let rang = 0;
  return cibles.map((distance) => {
    while (rang < segments.length - 1 && segments[rang].fin < distance) rang++;
    const { depart, arrivee, debut, fin } = segments[rang];
    const fraction = (distance - debut) / (fin - debut);
    const lat = depart[1] + (arrivee[1] - depart[1]) * fraction;
    const lon = depart[0] + (arrivee[0] - depart[0]) * fraction;
    const dx = (arrivee[0] - depart[0]) * Math.cos(lat * Math.PI / 180);
    const dy = arrivee[1] - depart[1];
    return { lat, lon, angle: Math.atan2(-dy, dx) * 180 / Math.PI };
  });
}

function afficherFleches() {
  fleches.clearLayers();
  if (carte.getZoom() < 12) return;
  for (const { lat, lon, angle } of flechesTrace) {
    const iconeFleche = L.divIcon({
      className: "route-direction-icon", iconSize: [14, 14], iconAnchor: [7, 7],
      html: `<svg viewBox="0 0 18 18" aria-hidden="true" style="transform:rotate(${angle}deg)"><path d="M4 4 14 9 4 14 6 9Z"/></svg>`,
    });
    L.marker([lat, lon], { icon: iconeFleche, interactive: false, keyboard: false, pane: "sensTrace" }).addTo(fleches);
  }
}

function icone(rang, total) {
  const depart = rang === 0;
  const arrivee = total > 1 && rang === total - 1;
  return L.divIcon({
    className: `point${depart ? " depart" : arrivee ? " arrivee" : ""}`,
    html: depart ? t("icone.depart") : arrivee ? t("icone.arrivee") : String(rang),
    iconSize: [24, 24],
  });
}

function rafraichirPoints() {
  etat.points.forEach((p, rang) => p.marqueur.setIcon(icone(rang, etat.points.length)));
  $("retirerDernier").disabled = etat.points.length === 0;
  $("toutEffacer").disabled = etat.points.length === 0;
  $("boucler").disabled = !bouclable();
}

// Une boucle se ferme par un bouton : un clic sur le marqueur du départ ouvre
// sa bulle, il ne peut pas aussi poser un point.
function bouclable() {
  const depart = etat.points[0];
  const dernier = etat.points.at(-1);
  return etat.points.length >= 2 && (dernier.lat !== depart.lat || dernier.lon !== depart.lon);
}

function boucler() {
  if (bouclable()) ajouterPoint(L.latLng(etat.points[0].lat, etat.points[0].lon));
}

function bullePoint(point) {
  const div = document.createElement("div");
  div.className = "bulle";
  div.append(boutonAction(t("bulle.retirer"), () => retirerPoint(point)));
  if (point === etat.points[0] && bouclable()) {
    div.append(boutonAction(t("bulle.revenir"), () => { point.marqueur.closePopup(); boucler(); }));
  }
  return div;
}

function ajouterPoint(latlng, recalculer = true) {
  const point = { lat: latlng.lat, lon: latlng.lng };
  point.marqueur = L.marker(latlng, { draggable: true, keyboard: false, icon: icone(0, 1) }).addTo(carte);
  point.marqueur.on("dragend", () => {
    const position = point.marqueur.getLatLng();
    point.lat = position.lat;
    point.lon = position.lng;
    rafraichirPoints();
    planifierCalcul();
  });
  point.marqueur.bindPopup(() => bullePoint(point));
  etat.points.push(point);
  rafraichirPoints();
  if (recalculer) planifierCalcul();
}

function retirerPoint(point) {
  point.marqueur.remove();
  etat.points = etat.points.filter((p) => p !== point);
  rafraichirPoints();
  planifierCalcul();
}

// ------------------------------------------------------------ calcul

// Toute modification rend aussitôt le résultat affiché périmé : il ne peut
// plus s'exporter, et une réponse déjà en route sera ignorée (audit B06). Le
// tracé reste visible jusqu'au suivant, pour ne pas faire clignoter la carte.
function planifierCalcul() {
  clearTimeout(etat.minuterie);
  try {
    localStorage.setItem(CLE_POINTS, JSON.stringify(etat.points.map((p) => [p.lat, p.lon])));
  } catch (e) { /* le parcours reste utilisable si le stockage est indisponible */ }
  etat.sequence++;
  etat.dernier = null;
  afficherDisponibilite(null);
  actualiserDisponibilite();
  $("exporter").disabled = true;
  etat.minuterie = setTimeout(calculer, DELAI_CALCUL_MS);
}

function effacerResultat() {
  couches.clearLayers();
  flechesTrace = [];
  fleches.clearLayers();
  cacherMarqueurProfil();
  profilRoute = null;
  etat.dernier = null;
  actualiserDisponibilite();
  $("resultat").hidden = true;
  $("exporter").disabled = true;
}

// Pendant un calcul : pointeur d'attente (cursor: progress, la carte reste
// utilisable) et barre de progression en bas de la carte, nourrie par l'étape
// que le serveur publie (/api/progression), lue toutes les demi-secondes.
function occupe(oui) {
  document.body.classList.toggle("calcul", oui);
  clearInterval(etat.suivi);
  etat.suivi = null;
  $("progression").hidden = !oui;
  if (oui) {
    afficherProgression({ etape: "debut", fraction: 0.02, duree_s: 0, passe: 1 });
    etat.suivi = setInterval(lireProgression, 500);
  }
}

async function lireProgression() {
  try {
    const p = await api("progression");
    if (p.actif && etat.suivi) afficherProgression(p);
  } catch (e) {
    // Le tour suivant réessaie : la barre n'est qu'une indication.
  }
}

function afficherProgression(p) {
  const cle = TEXTES.fr[`etape.${p.etape}`] ? `etape.${p.etape}` : "etape.debut";
  const texteEtape = t(cle, { faites: p.faites, total: p.total }) + (p.passe > 1 ? t("etape.elargie") : "");
  $("progressionTexte").textContent = `${texteEtape} · ${Math.round(p.duree_s)} s`;
  $("progressionBarre").style.width = `${Math.round(100 * p.fraction)}%`;
}

async function calculer() {
  const numero = ++etat.sequence;
  $("actions").replaceChildren();
  if (etat.points.length < 2) {
    occupe(false);
    effacerResultat();
    afficherStatut(etat.points.length ? () => t("statut.deuxiemePoint") : "");
    return;
  }
  const fournisseur = FOURNISSEURS_CARTES[paysCarte]?.paths;
  const source = cheminsDisponibles(fournisseur, etat.points) ? fournisseur?.source : null;
  const ign = Boolean(source && $("ign").checked);
  afficherStatut(() => t("statut.calcul") + (ign ? t("statut.calculOfficiel", { nom: fournisseur.label }) : "."));
  occupe(true);
  let reponse;
  try {
    reponse = await api("itineraire", {
      points: etat.points.map((p) => [p.lat, p.lon]),
      strict: $("strict").checked,
      ign,
      source: source || "ign",
      comparer: $("comparer").checked,
    });
  } catch (e) {
    if (numero === etat.sequence) {
      occupe(false);
      effacerResultat();      // l'ancien tracé ne correspond plus aux points ni aux options
      afficherStatut(() => t("statut.erreur", { message: e.message }), true);
    }
    return;
  }
  if (numero !== etat.sequence) return;   // un calcul plus récent est en route
  occupe(false);
  if (reponse.erreur) afficherErreur(reponse);
  else {
    afficher(reponse);
    majExtrait(true);       // le calcul a pu lancer l'extrait OSM de la région
  }
}

// ------------------------------------------------------------ plein écran

// La carte seule, sans le panneau ni le choix des fonds et calques : un bouton
// sous le zoom bascule, Échap ou le même bouton ramènent la page normale.
const PleinEcran = L.Control.extend({
  options: { position: "topleft" },
  onAdd() {
    const bouton = L.DomUtil.create("button", "bouton-plein-ecran");
    bouton.type = "button";
    bouton.id = "pleinEcran";
    bouton.title = t("pleinEcran.entrer");
    bouton.textContent = "⛶";
    L.DomEvent.disableClickPropagation(bouton);
    L.DomEvent.on(bouton, "click", basculerPleinEcran);
    return bouton;
  },
});

function appliquerPleinEcran(actif) {
  document.body.classList.toggle("plein-ecran", actif);
  $("pleinEcran").title = t(actif ? "pleinEcran.quitter" : "pleinEcran.entrer");
  carte.invalidateSize();
}

function basculerPleinEcran() {
  const actif = !document.body.classList.contains("plein-ecran");
  appliquerPleinEcran(actif);
  // Le navigateur peut refuser son plein écran : la carte seule reste acquise.
  if (actif && document.documentElement.requestFullscreen) document.documentElement.requestFullscreen().catch(() => {});
  if (!actif && document.fullscreenElement) document.exitFullscreen().catch(() => {});
}

function boutonAction(libelle, action) {
  const bouton = document.createElement("button");
  bouton.type = "button";
  bouton.textContent = libelle;
  bouton.addEventListener("click", async () => {
    bouton.disabled = true;
    try {
      await action();
    } catch (e) {
      afficherStatut(() => t("statut.erreur", { message: e.message }), true);
    } finally {
      bouton.disabled = false;
    }
  });
  return bouton;
}

function afficherErreur(reponse) {
  if (reponse.code === "attente_lot") {
    // Pas une erreur : le calcul attend le lot de la zone, puis reprend (suivreLot).
    afficherStatut(() => t("horsLigne.attenteCalcul"));
    etat.attenteLot = true;
    return;
  }
  effacerResultat();
  const osmIndisponible = /Overpass|barrières non vérifiées|OSM.*indisponibles/i.test(reponse.erreur || "");
  afficherStatut(() => osmIndisponible ? t("statut.donneesIndisponibles") : texteErreur(reponse), true);
  // Il manquait des données : le serveur les télécharge de lui-même (moteur et
  // tuiles BRouter, ou l'extrait OSM quand Overpass est en panne), et le
  // calcul reprendra une fois qu'elles seront là. Aucun bouton à cliquer.
  const b = reponse.brouter_en_cours;
  if (b && (b.moteur || b.segments?.length)) {
    afficherStatut(() => t("brouter.attente", { quoi: quoiBrouter(b) }));
    etat.donneesAttendues = { extrait: null };
  } else if (reponse.extrait_en_cours) {
    afficherStatut(() => t("extrait.attente", { nom: reponse.extrait_en_cours.nom }));
    // L'extrait attendu, nommé : la région qui part ensuite prendre son relais
    // ne fait pas attendre le calcul.
    etat.donneesAttendues = { extrait: reponse.extrait_en_cours.id };
  }
  majExtrait(true);
  actualiserDisponibilite();
}

function lignes(feature) {
  return feature.geometry.coordinates.map((c) => [c[1], c[0]]);
}

let profilRoute = null;
let marqueurProfil = null;

function cacherMarqueurProfil() {
  if (marqueurProfil) marqueurProfil.remove();
  marqueurProfil = null;
}

function preparerRouteProfil(coordonnees) {
  const points = coordonnees.map(([lon, lat]) => [lat, lon]);
  const distances = [0];
  for (let i = 1; i < points.length; i++) {
    distances.push(distances[i - 1] + L.latLng(points[i - 1]).distanceTo(L.latLng(points[i])));
  }
  return { points, distances, total: distances.at(-1) };
}

function positionSurProfil(fraction) {
  if (!profilRoute || !profilRoute.total || !Number.isFinite(fraction)) return null;
  const { points, distances, total } = profilRoute;
  const cible = Math.max(0, Math.min(1, fraction)) * total;
  let debut = 1;
  let fin = distances.length - 1;
  while (debut < fin) {
    const milieu = Math.floor((debut + fin) / 2);
    if (distances[milieu] < cible) debut = milieu + 1;
    else fin = milieu;
  }
  const part = (cible - distances[debut - 1]) / (distances[debut] - distances[debut - 1] || 1);
  return [0, 1].map(i => points[debut - 1][i] + part * (points[debut][i] - points[debut - 1][i]));
}

document.addEventListener("hike2gpx:profil-position", event => {
  const position = positionSurProfil(event.detail);
  if (!position) return cacherMarqueurProfil();
  if (marqueurProfil) marqueurProfil.setLatLng(position);
  else marqueurProfil = L.circleMarker(position, {
    radius: 7, color: "#fff", weight: 2, fillColor: "#1565c0", fillOpacity: 1,
    interactive: false, pane: "trace", className: "profile-map-cursor",
  }).addTo(carte);
});

function paragraphe(contenu, gras = false) {
  const p = document.createElement("p");
  if (gras) {
    const fort = document.createElement("strong");
    fort.textContent = contenu;
    p.append(fort);
  } else {
    p.textContent = contenu;
  }
  return p;
}

function bulleFranchissement(f) {
  const div = document.createElement("div");
  div.className = "bulle";
  const lien = document.createElement("a");
  lien.href = `https://www.openstreetmap.org/${f.osm}`;
  lien.target = "_blank";
  lien.rel = "noopener";
  lien.textContent = t("bulle.osm");
  div.append(paragraphe(`${natureDe(f)} : ${t(f.statut === "blocked" ? "bulle.bloquant" : "bulle.verifier")}`, true),
             paragraphe(ts(f.raison)));
  if (f.osm) div.append(lien);
  return div;
}

function afficher(r) {
  etat.dernier = r;
  cacherMarqueurProfil();
  profilRoute = null;
  couches.clearLayers();
  if (r.naif && $("comparer").checked) {
    L.polyline(lignes(r.naif), { color: "#555", weight: 4, opacity: 0.7, dashArray: "6 8", interactive: false, pane: "trace" })
      .addTo(couches);
  }
  L.polyline(lignes(r.itineraire), { color: "#1565c0", weight: 5, opacity: 0.85, interactive: false, pane: "trace" })
    .addTo(couches);
  flechesTrace = preparerFleches(r.itineraire.geometry.coordinates);
  afficherFleches();
  for (const p of r.portions_ign || []) {
    L.polyline(p.coords, { color: COULEURS.uncertain, weight: 5, opacity: 0.95, dashArray: "8 6", interactive: false, pane: "trace" })
      .addTo(couches);
  }
  for (const f of r.franchissements) {
    L.circleMarker([f.lat, f.lon], { radius: 6, weight: 2, color: "#fff", fillOpacity: 1, fillColor: COULEURS[f.statut], pane: "trace" })
      .bindPopup(() => bulleFranchissement(f))
      .addTo(couches);
  }
  ecrireResultat(r);
  calculerDenivele(r);
  proposerMiseAJour(r.lot);
  $("resultat").hidden = false;
  $("exporter").disabled = false;
  actualiserDisponibilite();
  // Repli sur OSM seul : les chemins officiels demandés n'ont pas pu servir, il faut le voir.
  afficherStatut(() => {
    const bilan = t("statut.bilan", { duree: decimal(r.duree_s, 2), total: r.franchissements.length });
    if (!r.avertissement) return bilan;
    const nom = Object.values(FOURNISSEURS_CARTES).find((p) => p.paths?.source === r.source_officielle)?.paths.label
      || r.source_officielle;
    const avertissement = langue === "en"
      ? t("avertissement.officiel", { nom, detail: r.avertissement_detail }) : r.avertissement;
    return `${avertissement} ${bilan}`;
  }, Boolean(r.avertissement));
}

// Les textes du résultat, réécrits aussi quand la langue change.
function ecrireResultat(r) {
  $("distance").textContent = km(r.longueur_m);
  if (r.denivele) {
    ecrireDenivele(r.denivele);
  } else {
    for (const id of ["denivele", "duree", "pointHaut", "pointBas"])
      $(id).textContent = r.erreurDenivele ? "—" : "…";
    $("sourceDenivele").textContent = r.erreurDenivele ? t("denivele.indisponible", { erreur: r.erreurDenivele })
      : t("denivele.calcul");
  }
  const n = (r.naif_traverse || []).length;
  $("comparaison").textContent = !r.naif ? ""
    : t(n ? "comparaison.traverse" : "comparaison.aucun", { km: km(r.naif_longueur_m), n });
  const liste = $("aVerifier");
  liste.replaceChildren();
  for (const f of r.sur_le_trace) {
    const li = document.createElement("li");
    const raison = ts(f.raison);
    li.textContent = `${km(f.distance_m)} : ${natureDe(f)}, ${raison.charAt(0).toLowerCase()}${raison.slice(1)}`;
    li.title = t("liste.centrer");
    li.addEventListener("click", () => carte.setView([f.lat, f.lon], Math.max(carte.getZoom(), 17)));
    liste.append(li);
  }
  $("aucunAVerifier").hidden = r.sur_le_trace.length > 0;
  $("aVerifierTitle").hidden = r.sur_le_trace.length === 0;
  $("resultat").classList.toggle("empty", r.sur_le_trace.length === 0);
}

// ------------------------------------------------------------ dénivelé

// Le dénivelé de gpx2elev arrive après l'itinéraire : le modèle de terrain
// peut demander quelques secondes la première fois, la carte n'attend pas.
async function calculerDenivele(r) {
  const numero = ++etat.sequenceDenivele;
  let d;
  try {
    d = await api("denivele", { coordonnees: r.itineraire.geometry.coordinates });
  } catch (e) {
    d = { erreur: e.message };
  }
  if (numero !== etat.sequenceDenivele || etat.dernier !== r) return;   // un tracé plus récent est affiché
  if (d.erreur) {
    cacherMarqueurProfil();
    profilRoute = null;
    r.erreurDenivele = ts(d.erreur);
    for (const id of ["denivele", "duree", "pointHaut", "pointBas"]) $(id).textContent = "—";
    $("sourceDenivele").textContent = t("denivele.indisponible", { erreur: r.erreurDenivele });
    if (typeof CustomEvent !== "undefined") document.dispatchEvent(new CustomEvent("hike2gpx:denivele", { detail: d }));
    return;
  }
  r.denivele = d;
  profilRoute = preparerRouteProfil(r.itineraire.geometry.coordinates);
  ecrireDenivele(d);
  if (typeof CustomEvent !== "undefined") document.dispatchEvent(new CustomEvent("hike2gpx:denivele", { detail: d }));
}

function ecrireDenivele(d) {
  $("denivele").textContent = `+ ${d.montee_m} m / − ${d.descente_m} m`;
  $("pointHaut").textContent = `${d.altitude_max_m} m`;
  $("pointBas").textContent = `${d.altitude_min_m} m`;
  const minutes = Math.ceil(d.duree_marche_s / 300) * 5;
  $("duree").textContent = Number.isFinite(minutes)
    ? (minutes >= 60 ? `${Math.floor(minutes / 60)} h ${String(minutes % 60).padStart(2, "0")}` : `${minutes} min`)
    : "—";
  $("sourceDenivele").textContent = t("denivele.source",
    { modele: d.modele, min: d.altitude_min_m, max: d.altitude_max_m });
}

// ------------------------------------------------------------ GPX

function echapper(contenu) {
  return String(contenu).replace(/[<>&'"]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", "'": "&apos;", '"': "&quot;" }[c]));
}

function descriptionGpx(r) {
  const denivele = r.denivele
    ? `D+ ${r.denivele.montee_m} m, D- ${r.denivele.descente_m} m (gpx2elev, ${r.denivele.modele})`
    : t("gpx.deniveleIndisponible");
  return t("gpx.description", { km: km(r.longueur_m), denivele, n: r.sur_le_trace.length })
    + t("gpx.barrieres") + ((r.portions_ign || []).length
      ? Object.values(FOURNISSEURS_CARTES).find((f) => f.paths?.source === r.source_officielle)?.paths.gpx?.[langue] || "" : "")
    + t("gpx.trace");
}

function gpx(r) {
  const nom = `hike2gpx ${new Date().toLocaleDateString(langue === "en" ? "en-GB" : "fr-FR")}`;
  const wpt = r.sur_le_trace.map((f) => `  <wpt lat="${f.lat}" lon="${f.lon}"><name>${echapper(t("gpx.aVerifier", { nature: natureDe(f) }))}</name>`
    + `<desc>${echapper(ts(f.raison))}</desc><type>${f.statut === "blocked" ? "bloquant" : "a_verifier"}</type></wpt>\n`);
  const trkpt = r.itineraire.geometry.coordinates.map((c) => `      <trkpt lat="${c[1]}" lon="${c[0]}">`
    + `${c.length > 2 && Number.isFinite(Number(c[2])) ? `<ele>${Number(c[2])}</ele>` : ""}</trkpt>\n`);
  return '<?xml version="1.0" encoding="UTF-8"?>\n'
    + `<gpx version="1.1" creator="hike2gpx ${echapper(etat.version)}" xmlns="http://www.topografix.com/GPX/1/1">\n`
    + `  <metadata><name>${echapper(nom)}</name><desc>${echapper(descriptionGpx(r))}</desc></metadata>\n`
    + wpt.join("")
    + `  <trk>\n    <name>${echapper(nom)}</name>\n    <trkseg>\n${trkpt.join("")}    </trkseg>\n  </trk>\n</gpx>\n`;
}

function exporter() {
  if (!etat.dernier) return;
  const d = new Date();
  const deux = (n) => String(n).padStart(2, "0");
  const lien = document.createElement("a");
  lien.download = `hike2gpx-${d.getFullYear()}${deux(d.getMonth() + 1)}${deux(d.getDate())}-${deux(d.getHours())}${deux(d.getMinutes())}.gpx`;
  lien.href = URL.createObjectURL(new Blob([gpx(etat.dernier)], { type: "application/gpx+xml" }));
  document.body.append(lien);
  lien.click();
  lien.remove();
  setTimeout(() => URL.revokeObjectURL(lien.href), 1000);
}

function lireTracesGpx(source) {
  const xml = new DOMParser().parseFromString(source, "application/xml");
  if (xml.documentElement?.localName !== "gpx" || xml.getElementsByTagName("parsererror").length) {
    throw new Error(t("gpx.invalide"));
  }
  const segments = [];
  const lirePoints = (parent, nom) => Array.from(parent.getElementsByTagNameNS("*", nom), (point) => {
    const latitude = point.getAttribute("lat");
    const longitude = point.getAttribute("lon");
    const lat = Number(latitude);
    const lon = Number(longitude);
    if (!latitude?.trim() || !longitude?.trim() || !Number.isFinite(lat) || !Number.isFinite(lon)
      || Math.abs(lat) > 90 || Math.abs(lon) > 180) throw new Error(t("gpx.invalide"));
    return [lat, lon];
  });
  for (const segment of xml.getElementsByTagNameNS("*", "trkseg")) {
    const points = lirePoints(segment, "trkpt");
    if (points.length) segments.push(points);
  }
  for (const route of xml.getElementsByTagNameNS("*", "rte")) {
    const points = lirePoints(route, "rtept");
    if (points.length) segments.push(points);
  }
  if (!segments.length) throw new Error(t("gpx.invalide"));
  return segments;
}

async function chargerGpx(fichier) {
  const sequence = ++sequenceImportGpx;
  $("erreurGpx").hidden = true;
  try {
    if (fichier.size > 20_000_000) throw new Error(t("gpx.tropGrand"));
    const segments = lireTracesGpx(await fichier.text());
    if (sequence !== sequenceImportGpx) return;
    traceGpxImporte.clearLayers();
    let minLat = 90, minLon = 180, maxLat = -90, maxLon = -180;
    for (const points of segments) {
      L.polyline(points, { pane: "gpxImporte", color: "#344132", weight: 7, opacity: 0.9,
        dashArray: "9 6", interactive: false }).addTo(traceGpxImporte);
      L.polyline(points, { pane: "gpxImporte", color: "#ffe14a", weight: 4, opacity: 1,
        dashArray: "9 6", interactive: false }).addTo(traceGpxImporte);
      for (const [lat, lon] of points) {
        minLat = Math.min(minLat, lat); minLon = Math.min(minLon, lon);
        maxLat = Math.max(maxLat, lat); maxLon = Math.max(maxLon, lon);
      }
    }
    nomGpxImporte = fichier.name.replace(/\.gpx$/i, "") || fichier.name;
    traceGpxImporte.addTo(carte);
    if (controleFonds) controleFonds.addOverlay(traceGpxImporte, echapper(nomGpxImporte));
    else construireFonds();
    $("legendGpx").hidden = false;
    $("chargerGpx").dataset.i18n = "bouton.supprimerGpx";
    $("chargerGpx").textContent = t("bouton.supprimerGpx");
    carte.fitBounds([[minLat, minLon], [maxLat, maxLon]], { padding: [30, 30], maxZoom: 16 });
  } catch (erreur) {
    if (sequence === sequenceImportGpx) {
      $("erreurGpx").textContent = t("gpx.erreur", { message: erreur.message });
      $("erreurGpx").hidden = false;
    }
  }
}

function supprimerGpx() {
  ++sequenceImportGpx;
  if (controleFonds) controleFonds.removeLayer(traceGpxImporte);
  traceGpxImporte.remove();
  traceGpxImporte.clearLayers();
  $("fichierGpx").value = "";
  nomGpxImporte = null;
  $("legendGpx").hidden = true;
  $("chargerGpx").dataset.i18n = "bouton.chargerGpx";
  $("chargerGpx").textContent = t("bouton.chargerGpx");
  $("erreurGpx").hidden = true;
}

// ------------------------------------------------------------ démarrage

carte.on("click", (e) => ajouterPoint(e.latlng));
$("retirerDernier").addEventListener("click", () => { const p = etat.points.at(-1); if (p) retirerPoint(p); });
$("boucler").addEventListener("click", boucler);
$("toutEffacer").addEventListener("click", () => {
  etat.points.forEach((p) => p.marqueur.remove());
  etat.points = [];
  rafraichirPoints();
  planifierCalcul();
});
$("exporter").addEventListener("click", exporter);
$("chargerGpx").addEventListener("click", () => {
  if (!nomGpxImporte) $("fichierGpx").click();
  else supprimerGpx();
});
$("fichierGpx").addEventListener("change", (event) => {
  const fichier = event.target.files?.[0];
  event.target.value = "";
  if (fichier) return chargerGpx(fichier);
});
new PleinEcran().addTo(carte);
// Échap quitte le plein écran du navigateur : la page revient avec lui.
document.addEventListener("fullscreenchange", () => {
  if (!document.fullscreenElement && document.body.classList.contains("plein-ecran")) appliquerPleinEcran(false);
});
const CLE_OPTIONS = "hike2gpx.options";
let choixIgn = $("ign").checked;
function restaurerOptions() {
  try {
    const options = JSON.parse(localStorage.getItem(CLE_OPTIONS) || "null");
    if (!options || typeof options !== "object") return;
    for (const id of ["strict", "ign", "comparer"]) {
      if (typeof options[id] === "boolean") $(id).checked = options[id];
    }
    choixIgn = $("ign").checked;
  } catch (erreur) { /* conserver les valeurs par défaut */ }
}
function memoriserOptions() {
  const options = { strict: $("strict").checked, ign: choixIgn, comparer: $("comparer").checked };
  try { localStorage.setItem(CLE_OPTIONS, JSON.stringify(options)); } catch (erreur) { /* sans importance */ }
}
restaurerOptions();
function restaurerPoints() {
  let points;
  try { points = JSON.parse(localStorage.getItem(CLE_POINTS) || "null"); }
  catch (e) { return; }
  if (!Array.isArray(points) || !points.every((p) => Array.isArray(p) && p.length === 2
    && Number.isFinite(p[0]) && Math.abs(p[0]) <= 90
    && Number.isFinite(p[1]) && Math.abs(p[1]) <= 180)) return;
  for (const [lat, lon] of points) ajouterPoint(L.latLng(lat, lon), false);
  if (points.length) planifierCalcul();
}
restaurerPoints();
for (const id of ["strict", "ign", "comparer"]) {
  $(id).addEventListener("change", () => {
    if (id === "ign") choixIgn = $("ign").checked;
    memoriserOptions();
    planifierCalcul();
  });
}
$("enregistrerCle").addEventListener("click", async () => {
  try {
    const r = await api("reglages", { cle_ign: $("cleIgn").value, renouvellement_jours: Number($("renouvellementJours").value) });
    if (r.erreur) { afficherStatut(() => ts(r.erreur), true); return; }
    etat.cleIgn = r.cle_ign;
    etat.renouvellementJours = r.renouvellement_jours;
    afficherExtrait(etat.extrait);
    construireFonds();
    afficherStatut(() => t(etat.cleIgn ? "cle.enregistree" : "cle.retiree"));
    verifierBrouter();
  } catch (e) {
    afficherStatut(() => t("statut.erreur", { message: e.message }), true);
  }
});
$("ouvrirDossierJournaux").addEventListener("click", async () => {
  const bouton = $("ouvrirDossierJournaux");
  bouton.disabled = true;
  $("erreurDossierJournaux").hidden = true;
  try {
    await api("ouvrir_journaux", {});
  } catch (erreur) {
    $("erreurDossierJournaux").textContent = t("reglages.erreurJournaux", { message: erreur.message });
    $("erreurDossierJournaux").hidden = false;
  } finally {
    bouton.disabled = false;
  }
});

// ------------------------------------------------------------ mises à jour

// /api/maj et /api/maj-verifier sont les routes du commun (absentes depuis les
// sources). Le panneau ne fait que demander une vérification : c'est le bandeau
// commun (nico579-maj.js) qui propose « Installer » et suit l'installation.
function plusRecente(publiee, locale) {
  const a = String(publiee || "").split(".").map(Number);
  const b = String(locale || "").split(".").map(Number);
  for (let k = 0; k < Math.max(a.length, b.length); k++) {
    if ((a[k] || 0) !== (b[k] || 0)) return (a[k] || 0) > (b[k] || 0);
  }
  return false;
}

function afficherVersion(d) {
  if (!d?.version_locale) return;
  $("versionApplication").textContent = `hike2gpx ${d.version_locale}`;
  $("versionApplication").hidden = false;
}

api("maj").then(afficherVersion).catch(() => {});

$("verifierMaj").addEventListener("click", async () => {
  const bouton = $("verifierMaj");
  bouton.disabled = true;
  $("statutMaj").textContent = t("reglages.verification");
  $("statutMaj").hidden = false;
  try {
    const d = await api("maj-verifier", {});
    afficherVersion(d);
    if (!d.ok) throw new Error("vérification impossible");
    $("statutMaj").textContent = plusRecente(d.version, d.version_locale)
      ? t("reglages.majDisponible", { version: d.version }) : t("reglages.aJour");
    window.nico579Maj?.suivre();
  } catch {
    $("statutMaj").textContent = t("reglages.majImpossible");
  } finally {
    bouton.disabled = false;
  }
});

// ------------------------------------------------------------ données téléchargées

// Les tuiles de fond restent dans le cache HTTP du navigateur ; seul le
// serveur peut vider les données locales qu'il a téléchargées.
function afficherDonnees(d) {
  if (d) etat.donnees = d;
  const donnees = etat.donnees;
  if (!donnees) return;
  const boite = $("donnees");
  boite.replaceChildren();
  const occupe = donnees.occupe || {};
  const bouton = document.createElement("button");
  bouton.type = "button";
  bouton.textContent = t("donnees.viderTout");
  bouton.disabled = Boolean(occupe.extrait || occupe.brouter);
  bouton.addEventListener("click", () => agirDonnees("vider_cache", null, t("donnees.confirmerTout")));
  const controles = document.createElement("div");
  controles.className = "cache-controls";
  const info = document.createElement("span");
  info.className = "info-tooltip";
  info.tabIndex = 0;
  info.setAttribute("aria-label", t("donnees.aideCache"));
  info.setAttribute("aria-describedby", "cacheTooltip");
  info.textContent = "i";
  const explication = document.createElement("span");
  explication.id = "cacheTooltip";
  explication.setAttribute("role", "tooltip");
  explication.textContent = t("donnees.detailCache");
  info.append(explication);
  controles.append(bouton, info);
  const statut = document.createElement("p");
  statut.id = "cacheStatus";
  statut.setAttribute("role", "status");
  boite.append(controles, statut);
}

async function chargerDonnees() {
  try {
    afficherDonnees(await api("donnees"));
  } catch (e) { /* serveur momentanément injoignable : la section reste telle quelle */ }
}

async function agirDonnees(action, cible, confirmer) {
  if (confirmer && !confirm(confirmer)) return;
  try {
    const r = await api("donnees", { action, cible });
    if (r.erreur) { afficherStatut(() => ts(r.erreur), true); return; }
    afficherDonnees(r);
    if (action === "vider_cache") {
      $("cacheStatus").textContent = t("donnees.vide");
      chargerLots();          // les lots et les fonds hors ligne sont partis aussi
      chargerFonds();
    }
    majExtrait(true);       // un téléchargement lancé se suit dans le panneau
  } catch (e) {
    afficherStatut(() => t("statut.erreur", { message: e.message }), true);
  }
}


async function verifierBrouter() {
  try {
    const resultat = await api("moteur", {});
    if (resultat.brouter_en_cours) majExtrait(true);
  } catch (e) { /* vérification reportée au prochain passage */ }
}

async function demarrer() {
  afficherOptionsIgn();
  try {
    const [infos, reglages] = await Promise.all([api("etat"), api("reglages")]);
    etat.version = infos.version;
    $("version").textContent = `${infos.version}, BRouter ${infos.brouter}`;
    lienAide();
    etat.cleIgn = reglages.cle_ign || "";
    $("cleIgn").value = etat.cleIgn;
    etat.renouvellementJours = reglages.renouvellement_jours ?? 30;
    $("renouvellementJours").value = etat.renouvellementJours;
    await verifierBrouter();
  } catch (e) {
    afficherStatut(() => t("serveur.injoignable", { message: e.message }), true);
  }
  restaurerCalques();     // avant le contrôle des fonds, pour que ses cases soient cochées
  construireFonds();
  chargerFonds();         // le fond hors ligne s'y ajoute s'il y en a
  // Le catalogue du serveur, lu dès l'ouverture : un calcul ou un calque peut
  // alors faire venir de lui-même le lot de sa zone (_lot_automatique).
  api("catalogue_lots").then((r) => { lotsServeur = r.lots || []; }).catch(() => {});
  rafraichirCalques();
  restaurerCases();       // lots installés, et fabrication en cours si la page a été rechargée
  api("partage").then(afficherPartage).catch(() => {});   // un partage resté ouvert, page rechargée
}

demarrer();
setInterval(verifierBrouter, 60 * 60 * 1000);
