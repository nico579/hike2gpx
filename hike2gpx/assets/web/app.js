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
    "aide": "Cliquez sur la carte pour poser le départ, puis les étapes et l'arrivée. Faites glisser un point pour le déplacer ; « Revenir au départ » ferme une boucle.",
    "bouton.retirerDernier": "Retirer",
    "bouton.retirerDernierInfo": "Retire le dernier point ajouté au parcours.",
    "bouton.toutEffacer": "Effacer",
    "bouton.toutEffacerInfo": "Efface tous les points et le tracé du parcours en cours.",
    "bouton.boucler": "Revenir",
    "bouton.bouclerInfo": "Ajoute le point de départ à la fin du parcours pour fermer la boucle.",
    "bouton.exporter": "Exporter le GPX",
    "option.strict": "Mode strict : éviter aussi les passages à vérifier",
    "option.ign": "Emprunter aussi les chemins IGN absents d'OSM (à vérifier sur place)",
    "option.comparer": "Montrer le tracé qui ignore les barrières",
    "resultat.distance": "Distance",
"resultat.duree": "Durée estimée",
"resultat.altitudeMaxMin": "Altitude max/min",
    "resultat.denivele": "Dénivelé",
    "resume.parcours": "Votre parcours",
"resume.dureeInfo": "Modèle de Tobler sur le profil gpx2elev lissé : v = 6 × exp(−3,5 × |pente + 0,05|) km/h. La pente est calculée tous les 20 m dans le sens du parcours ; les durées sont additionnées sans pauses. Le facteur 0,6 ne s'applique qu'aux portions identifiées hors sentier ; les chemins IGN restent des chemins.",
"recherche.label": "Rechercher une ville",
"recherche.placeholder": "Rechercher une ville…",
"recherche.bouton": "Chercher",
"recherche.attente": "Recherche en cours…",
"recherche.aucun": "Aucune ville trouvée.",
"recherche.erreur": "Recherche indisponible : {message}",
    "resume.deniveleInfo": "gpx2elev relève l'altitude tous les 5 m. Il choisit le meilleur modèle couvrant tout le parcours : IGN LiDAR HD en priorité, puis Mapterhorn, FABDEM, Copernicus GLO-30 ou SRTM. Il lisse le profil sur 20 m et calcule D+/D− avec un seuil de 2 m. Le modèle utilisé est indiqué sur le profil. Sans modèle disponible, le dénivelé reste indisponible ; la valeur BRouter ne le remplace pas.",
    "profil.titre": "Le relief du parcours",
    "profil.depart": "Départ",
    "profil.attente": "Calcul gpx2elev en cours…",
    "profil.indisponible": "Profil gpx2elev indisponible : {erreur}",
    "resultat.aVerifier": "Points à vérifier sur le tracé",
    "resultat.aucun": "Aucun franchissement connu sur ce tracé.",
    "legende.titre": "Légende",
    "legende.itineraire": "itinéraire hike2gpx",
    "legende.ign": "portion sur un chemin IGN absent d'OSM, à vérifier",
    "legende.naif": "tracé standard, qui ignore les barrières",
    "legende.bloque": "franchissement bloquant",
    "legende.verifier": "franchissement à vérifier",
    "legende.osm": "chemins OSM (tirets : sentiers)",
    "legende.barriere": "clôtures et murs connus d'OSM",
    "legende.bdtopo": "chemins BD TOPO de l'IGN",
    "reglages.titre": "Réglages",
    "reglages.cle": "Clé IGN pour le SCAN 25",
    "reglages.enregistrer": "Enregistrer",
    "reglages.note": "Le SCAN 25 n'est pas une donnée libre. Sans clé, la carte utilise le Plan IGN, sous Licence Ouverte.",
    "reglages.renouvellement": "Renouveler les données locales après",
    "reglages.jours": "jours",
    "reglages.masquerCartes": "Masquer le bandeau des cartes",
    "reglages.masquerDenivele": "Masquer le bandeau du dénivelé",
    "reglages.transparence": "Transparence des bandeaux",
    "disponibilite.oui": "Tracé disponible",
    "disponibilite.non": "Tracé indisponible",
    "statut.donneesIndisponibles": "Données OSM indisponibles pour ce tracé. Nouvelle tentative automatique après téléchargement.",
    "donnees.titre": "Données téléchargées",
    "donnees.note": "Tout se retélécharge de soi-même au besoin : vider ou supprimer libère de la place, actualiser donne des données fraîches.",
    "donnees.osm": "Chemins OSM lus sur Overpass : {n} tuiles, {taille}",
    "donnees.bdtopo": "Chemins BD TOPO : {n} tuiles, {taille}",
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
    "donnees.detailCache": "Ce bouton efface les réponses Overpass et les franchissements OSM, les chemins BD TOPO de l'IGN, les extraits OSM téléchargés (départements et régions), les données BRouter (moteur et tuiles de routage) et les modèles d'altitude gpx2elev. Ils seront retéléchargés au besoin. Les tuiles des fonds de carte IGN et OSM, conservées dans le cache du navigateur, ne sont pas effacées.",
    "donnees.confirmerTout": "Vider les données locales OSM, IGN, gpx2elev et BRouter ? Elles seront retéléchargées au besoin. Les tuiles de fond de carte restent dans le cache du navigateur.",
    "donnees.vide": "Cache local vidé. Les tuiles du fond de carte restent gérées par le navigateur.",
    "donnees.infoCache": "Les tuiles IGN et OSM du fond de carte restent dans le cache du navigateur.",
    "unite.mo": "Mo",
    "journal.titre": "Journal des calculs",
    "journal.note": "Erreurs, blocages et lenteurs, du plus ancien au plus récent :",
    "journal.vide": "Journal vide pour l'instant.",
    "journal.illisible": "Journal illisible : {message}",
    "journal.ouvrir": "Ouvrir le fichier de log",
    "pied": "Barrières et chemins © contributeurs OpenStreetMap (ODbL), chemins BD TOPO et cartes © IGN, calcul BRouter. Une barrière absente d'OpenStreetMap ne peut pas être évitée : le terrain a toujours le dernier mot.",
    "statut.deuxiemePoint": "Posez un deuxième point.",
    "statut.calcul": "Calcul en cours… La première fois dans une zone, la lecture des barrières OSM prend jusqu'à une minute",
    "statut.calculIgn": ", puis la fusion avec les chemins IGN quelques secondes.",
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
    "denivele.source": "gpx2elev, {modele} : échantillonnage 5 m, lissage 20 m, hystérésis 2 m ; altitude de {min} à {max} m.",
    "calque.osm": "Chemins OSM",
    "calque.bdtopo": "Chemins BD TOPO (IGN)",
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
    "bdtopo.troncon": "Tronçon",
    "bdtopo.acces": "accès piéton : {valeur}",
    "bdtopo.prive": "privé",
    "fond.scan25": "SCAN 25 (IGN)",
    "fond.plan": "Plan IGN",
    "fond.photos": "Photos aériennes (IGN)",
    "fond.osmRando": "OSM rando",
    "fond.osm": "OSM",
    "fond.osmVelo": "OSM vélo",
    "fond.satellite": "Satellite",
    "fond.reliefLidar": "Relief LiDAR HD (IGN)",
    "attribution.osm": "contributeurs OpenStreetMap",
    "cle.enregistree": "Clé enregistrée : SCAN 25 disponible.",
    "cle.retiree": "Clé retirée : Plan IGN par défaut.",
    "pleinEcran.entrer": "Plein écran",
    "pleinEcran.quitter": "Quitter le plein écran",
    "etape.debut": "Préparation du calcul",
    "etape.donnees": "Lecture des données de la zone : {faites} / {total} tuiles",
    "etape.fusion": "Fusion avec les chemins IGN",
    "etape.tuiles": "Fabrication de la tuile BRouter",
    "etape.analyse": "Analyse des franchissements",
    "etape.itineraire": "Calcul de l'itinéraire",
    "etape.comparaison": "Tracé standard, pour comparaison",
    "etape.elargie": " (zone élargie)",
    "icone.depart": "D",
    "icone.arrivee": "A",
    "ign.nature": "Chemin IGN de {m} m",
    "gpx.deniveleIndisponible": "dénivelé gpx2elev indisponible",
    "gpx.description": "Distance {km}, {denivele}, passages à vérifier : {n}. ",
    "gpx.barrieres": "Barrières © contributeurs OpenStreetMap",
    "gpx.bdtopo": ", chemins BD TOPO © IGN",
    "gpx.trace": " ; tracé hike2gpx.",
    "gpx.aVerifier": "À vérifier : {nature}",
    "erreur.zone_trop_etendue": "Zone trop étendue : {nombre} tuiles de 0,05° à examiner, au plus {max}. Découpez le parcours en étapes plus courtes.",
    "erreur.itineraire_refuse": "Itinéraire refusé : le tracé passe un franchissement {mot} ({nature}, à {distance} du départ).",
    "mot.bloquant": "bloquant",
    "mot.strict": "à vérifier, en mode strict",
    "avertissement.ign": "Chemins IGN indisponibles, calcul sur OSM seul : {detail}",
  },
  en: {
    "aide": "Click the map to place the start, then the waypoints and the finish. Drag a point to move it; “Back to start” closes a loop.",
    "bouton.retirerDernier": "Remove",
    "bouton.retirerDernierInfo": "Removes the last point added to the route.",
    "bouton.toutEffacer": "Clear",
    "bouton.toutEffacerInfo": "Clears all points and the current route.",
    "bouton.boucler": "Return",
    "bouton.bouclerInfo": "Adds the starting point to the end of the route to close the loop.",
    "bouton.exporter": "Export GPX",
    "option.strict": "Strict mode: also avoid crossings to check",
    "option.ign": "Also use IGN paths missing from OSM (to check on site)",
    "option.comparer": "Show the route that ignores barriers",
    "resultat.distance": "Distance",
"resultat.duree": "Estimated time",
"resultat.altitudeMaxMin": "Max/min altitude",
    "resultat.denivele": "Elevation",
    "resume.parcours": "Your route",
"resume.dureeInfo": "Tobler's model on the smoothed gpx2elev profile: v = 6 × exp(−3.5 × |slope + 0.05|) km/h. Slope is measured every 20 m in travel direction; segment times are added without breaks. The 0.6 factor applies only to identified off-path sections; IGN paths remain paths.",
"recherche.label": "Search for a town",
"recherche.placeholder": "Search for a town…",
"recherche.bouton": "Search",
"recherche.attente": "Searching…",
"recherche.aucun": "No town found.",
"recherche.erreur": "Search unavailable: {message}",
    "resume.deniveleInfo": "gpx2elev samples elevation every 5 m. It selects the best model covering the whole route: IGN LiDAR HD first, then Mapterhorn, FABDEM, Copernicus GLO-30 or SRTM. It smooths the profile over 20 m and calculates ascent/descent with a 2 m threshold. The selected model appears on the profile. If none is available, elevation remains unavailable; the BRouter estimate is not substituted.",
    "profil.titre": "Route elevation",
    "profil.depart": "Start",
    "profil.attente": "Calculating with gpx2elev…",
    "profil.indisponible": "gpx2elev profile unavailable: {erreur}",
    "resultat.aVerifier": "Points to check along the route",
    "resultat.aucun": "No known crossing on this route.",
    "legende.titre": "Legend",
    "legende.itineraire": "hike2gpx route",
    "legende.ign": "section on an IGN path missing from OSM, to check",
    "legende.naif": "standard route, ignoring barriers",
    "legende.bloque": "blocking crossing",
    "legende.verifier": "crossing to check",
    "legende.osm": "OSM paths (dashed: footpaths)",
    "legende.barriere": "fences and walls known to OSM",
    "legende.bdtopo": "IGN BD TOPO paths",
    "reglages.titre": "Settings",
    "reglages.cle": "IGN key for SCAN 25",
    "reglages.enregistrer": "Save",
    "reglages.note": "SCAN 25 is not open data. Without a key, the map uses Plan IGN, under the Open Licence.",
    "reglages.renouvellement": "Refresh local data after",
    "reglages.jours": "days",
    "reglages.masquerCartes": "Hide the map layers panel",
    "reglages.masquerDenivele": "Hide the elevation panel",
    "reglages.transparence": "Panel transparency",
    "disponibilite.oui": "Routing available",
    "disponibilite.non": "Routing unavailable",
    "statut.donneesIndisponibles": "OSM data unavailable for this route. Automatic retry after download.",
    "donnees.titre": "Downloaded data",
    "donnees.note": "Everything downloads again by itself when needed: clearing or deleting frees space, refreshing brings fresh data.",
    "donnees.osm": "OSM paths read from Overpass: {n} tiles, {taille}",
    "donnees.bdtopo": "BD TOPO paths: {n} tiles, {taille}",
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
    "donnees.detailCache": "This clears Overpass responses and OSM crossings, IGN BD TOPO paths, downloaded OSM extracts (departments and regions), BRouter data (engine and routing tiles), and gpx2elev elevation models. They are downloaded again when needed. IGN and OSM background map tiles held in the browser cache are not cleared.",
    "donnees.confirmerTout": "Clear local OSM, IGN, gpx2elev and BRouter data? It will download again when needed. Background map tiles remain in the browser cache.",
    "donnees.vide": "Local cache cleared. Background map tiles remain managed by the browser.",
    "donnees.infoCache": "IGN and OSM background map tiles remain in the browser cache.",
    "unite.mo": "MB",
    "journal.titre": "Calculation log",
    "journal.note": "Errors, blockages and slowness, oldest first:",
    "journal.vide": "The log is empty for now.",
    "journal.illisible": "Log unreadable: {message}",
    "journal.ouvrir": "Open log file",
    "pied": "Barriers and paths © OpenStreetMap contributors (ODbL), BD TOPO paths and maps © IGN, routing by BRouter. A barrier missing from OpenStreetMap cannot be avoided: the ground always has the last word.",
    "statut.deuxiemePoint": "Place a second point.",
    "statut.calcul": "Calculating… The first time in an area, reading the OSM barriers takes up to a minute",
    "statut.calculIgn": ", then merging the IGN paths a few seconds.",
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
    "denivele.source": "gpx2elev, {modele}: 5 m sampling, 20 m smoothing, 2 m hysteresis; elevation from {min} to {max} m.",
    "calque.osm": "OSM paths",
    "calque.bdtopo": "BD TOPO paths (IGN)",
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
    "bdtopo.troncon": "Section",
    "bdtopo.acces": "pedestrian access: {valeur}",
    "bdtopo.prive": "private",
    "fond.scan25": "SCAN 25 (IGN)",
    "fond.plan": "Plan IGN",
    "fond.photos": "Aerial photos (IGN)",
    "fond.osmRando": "OSM hiking",
    "fond.osm": "OSM",
    "fond.osmVelo": "OSM cycling",
    "fond.satellite": "Satellite",
    "fond.reliefLidar": "LiDAR HD terrain relief (IGN)",
    "attribution.osm": "OpenStreetMap contributors",
    "cle.enregistree": "Key saved: SCAN 25 available.",
    "cle.retiree": "Key removed: Plan IGN by default.",
    "pleinEcran.entrer": "Full screen",
    "pleinEcran.quitter": "Exit full screen",
    "etape.debut": "Preparing the calculation",
    "etape.donnees": "Reading the area's data: {faites} / {total} tiles",
    "etape.fusion": "Merging the IGN paths",
    "etape.tuiles": "Building the BRouter tile",
    "etape.analyse": "Analysing the crossings",
    "etape.itineraire": "Calculating the route",
    "etape.comparaison": "Standard route, for comparison",
    "etape.elargie": " (area enlarged)",
    "icone.depart": "S",
    "icone.arrivee": "F",
    "ign.nature": "IGN path, {m} m",
    "gpx.deniveleIndisponible": "gpx2elev elevation unavailable",
    "gpx.description": "Distance {km}, {denivele}, crossings to check: {n}. ",
    "gpx.barrieres": "Barriers © OpenStreetMap contributors",
    "gpx.bdtopo": ", BD TOPO paths © IGN",
    "gpx.trace": "; route by hike2gpx.",
    "gpx.aVerifier": "To check: {nature}",
    "erreur.zone_trop_etendue": "Area too large: {nombre} tiles of 0.05° to examine, {max} at most. Split the route into shorter stages.",
    "erreur.itineraire_refuse": "Route refused: it passes a {mot} crossing ({nature}, {distance} from the start).",
    "mot.bloquant": "blocking",
    "mot.strict": "to-check (strict mode)",
    "avertissement.ign": "IGN paths unavailable, routing on OSM only: {detail}",
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
  "Chemin de la BD TOPO absent d'OpenStreetMap : existence et accès à vérifier": "BD TOPO path missing from OpenStreetMap: existence and access to check",
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
  "Données OSM ou BD TOPO de la zone indisponibles.": "OSM or BD TOPO data for this area unavailable.",
  "Hors connexion : les barrières de cette zone n'ont jamais été chargées.": "Offline: the barriers of this area were never loaded.",
  "Hors connexion : chemins BD TOPO de cette zone jamais chargés.": "Offline: the BD TOPO paths of this area were never loaded.",
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
  let s = TEXTES[langue][cle] ?? TEXTES.fr[cle] ?? cle;
  for (const [k, v] of Object.entries(valeurs)) s = s.split(`{${k}}`).join(v);
  return s;
}

function ts(texte) {
  return langue === "en" && texte in SERVEUR_EN ? SERVEUR_EN[texte] : texte;
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
  return String(f.cle || "").startsWith("ign-") ? t("ign.nature", { m: f.longueur_m }) : ts(f.nature);
}

function appliquerLangue(code) {
  langue = code === "en" ? "en" : "fr";
  document.documentElement.lang = langue;
  for (const el of document.querySelectorAll("[data-i18n]")) el.textContent = t(el.dataset.i18n);
  $("cityQuery").placeholder = t("recherche.placeholder");
  if ($("pleinEcran")) {
    $("pleinEcran").title = t(document.body.classList.contains("plein-ecran") ? "pleinEcran.quitter" : "pleinEcran.entrer");
  }
  rafraichirPoints();
  construireFonds();
  rafraichirCalques();
  afficherExtrait(etat.extrait);
  afficherDonnees();
  afficherStatut(...etat.statut);
  if (etat.dernier) ecrireResultat(etat.dernier);
  actualiserDisponibilite();
}

document.addEventListener("nico579-langue", (e) => appliquerLangue(e.detail.code));

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
let horsFrance = vueInitiale.hors_france === true;
const carte = L.map("carte").setView([vueInitiale.lat, vueInitiale.lon], vueInitiale.zoom);
let sequenceRecherche = 0;
const resultatsVilles = $("cityResults");
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
        choisirZone(ville.code_pays !== "fr");
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
    localStorage.setItem(CLE_VUE, JSON.stringify({ lat, lon, zoom, hors_france: horsFrance }));
  } catch (e) { /* sans importance */ }
}
carte.on("moveend", () => {
  const c = carte.getCenter();
  memoriserVue(c.lat, c.lng, carte.getZoom());
  actualiserDisponibilite();
});

let sequenceDisponibilite = 0;
function afficherDisponibilite(d) {
  const pret = Boolean(d?.pret);
  $("readiness").classList.toggle("available", pret);
  $("readiness").classList.toggle("unavailable", !pret);
  $("readinessText").textContent = t(pret ? "disponibilite.oui" : "disponibilite.non");
  $("readiness").title = pret ? `OSM : ${d.source === "extrait" ? d.nom : "Overpass"}`
    : d?.verification ? "Vérification d'Overpass…" : "Aucune source OSM disponible dans cette zone";
}

async function actualiserDisponibilite() {
  const numero = ++sequenceDisponibilite;
  const parametres = new URLSearchParams(Object.entries(zoneVue()).map(([k, v]) => [k, v.toFixed(5)]));
  try {
    const d = await api(`disponibilite?${parametres}`);
    if (numero === sequenceDisponibilite) afficherDisponibilite(d);
  } catch (e) {
    if (numero === sequenceDisponibilite) afficherDisponibilite(null);
  }
}
setInterval(actualiserDisponibilite, 10000);

function tuileIgn(couche, format, cle, matrices = "PM") {
  const base = cle ? "https://data.geopf.fr/private/wmts" : "https://data.geopf.fr/wmts";
  return `${base}?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=${couche}&STYLE=normal`
    + `&TILEMATRIXSET=${matrices}&FORMAT=${format}&TILEMATRIX={z}&TILECOL={x}&TILEROW={y}`
    + (cle ? `&apikey=${encodeURIComponent(cle)}` : "");
}

const IGN = '© <a href="https://www.ign.fr/">IGN</a>';
const CLE_FOND = "hike2gpx.fond";
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
    try { localStorage.setItem(CLE_FOND, cle); } catch (erreur) { /* stockage indisponible */ }
  }
});

// ------------------------------------------------------------ calques de chemins

// Le tracé et ses franchissements passent au-dessus des chemins dessinés.
carte.createPane("trace").style.zIndex = 450;
carte.createPane("sensTrace").style.zIndex = 451;
const rendu = L.canvas({ padding: 0.2 });
const ZOOM_CALQUES = 14;
const CLE_CALQUES = "hike2gpx.calques";
// charge : bornes des tuiles déjà dessinées ; annulation : la requête en cours.
const CALQUES = {
  osm: { groupe: L.layerGroup(), charge: null, sequence: 0, annulation: null },
  bdtopo: { groupe: L.layerGroup(), charge: null, sequence: 0, annulation: null },
};
const STYLES_OSM = {
  sentier: { color: "#7b1fa2", weight: 3, dashArray: "6 4" },
  piste: { color: "#7b1fa2", weight: 3 },
  route: { color: "#7b1fa2", weight: 2, opacity: 0.45 },
};

function styleBdtopo(nature) {
  if (["Sentier", "Chemin", "Escalier"].includes(nature)) return { color: "#00897b", weight: 3, dashArray: "4 4" };
  if (nature === "Route empierrée") return { color: "#00897b", weight: 3 };
  return { color: "#00897b", weight: 2, opacity: 0.45 };
}

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
  },
  bdtopo(groupe, donnees) {
    for (const t2 of donnees.troncons) {
      const details = [t2.nature || t("bdtopo.troncon")];
      if (t2.acces_pieton) details.push(t("bdtopo.acces", { valeur: t2.acces_pieton }));
      if (t2.prive) details.push(t("bdtopo.prive"));
      L.polyline(t2.pts, { ...styleBdtopo(t2.nature), renderer: rendu })
        .bindTooltip(texte(`${details.join(", ")} (BD TOPO)`), { sticky: true }).addTo(groupe);
    }
  },
};

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
  const nom = t(`calque.${cle}`);
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
carte.on("moveend", () => {
  clearTimeout(minuterieCalques);
  minuterieCalques = setTimeout(rafraichirCalques, 400);
});
carte.on("overlayadd overlayremove", (e) => {
  const cle = Object.keys(CALQUES).find((c) => CALQUES[c].groupe === e.layer);
  if (!cle) return;
  const calque = CALQUES[cle];
  if (e.type === "overlayremove") {
    if (abandonner(calque)) arreterAuServeur([cle]);
    calque.groupe.clearLayers();
    calque.charge = null;
  }
  try {
    localStorage.setItem(CLE_CALQUES, JSON.stringify(Object.keys(CALQUES).filter((cle) => carte.hasLayer(CALQUES[cle].groupe))));
  } catch (erreur) { /* sans importance */ }
  rafraichirCalques();
});

function restaurerCalques() {
  let coches = Object.keys(CALQUES);
  try {
    const choix = localStorage.getItem(CLE_CALQUES);
    if (choix !== null) {
      const sauves = JSON.parse(choix);
      if (Array.isArray(sauves)) coches = sauves;
    }
  } catch (e) { /* préférence illisible : conserver les deux calques par défaut */ }
  for (const cle of coches) {
    if (CALQUES[cle] && (!horsFrance || cle === "osm")) CALQUES[cle].groupe.addTo(carte);
  }
}

function choisirZone(estHorsFrance) {
  if (horsFrance === estHorsFrance) return;
  horsFrance = estHorsFrance;
  afficherOptionsIgn();
  // Retirer le contrôle avant BD TOPO : Leaflet interpréterait sinon ce retrait
  // automatique comme un choix de l'utilisateur et écraserait sa préférence.
  if (controleFonds) {
    controleFonds.remove();
    controleFonds = null;
  }
  if (horsFrance) {
    const bdtopo = CALQUES.bdtopo;
    bdtopo.groupe.remove();
    if (abandonner(bdtopo)) arreterAuServeur(["bdtopo"]);
    bdtopo.groupe.clearLayers();
    bdtopo.charge = null;
  } else {
    restaurerCalques();
  }
  construireFonds();
}

function afficherOptionsIgn() {
  for (const id of ["ignOption", "legendIgn", "legendBdtopo"]) $(id).hidden = horsFrance;
}

// ------------------------------------------------------------ données OSM hors ligne

// L'extrait OSM du centre de la carte (le département d'OSM France, osmfr.py,
// sinon une région de Geofabrik, geofabrik.py), en cours de téléchargement ou
// installé. Le serveur le télécharge de lui-même
// dès qu'un calcul ou le calque des chemins OSM sert dans la région ; une fois
// installé, il y remplace Overpass.
const ZOOM_EXTRAIT = 10;
let minuterieExtrait = null;

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
  const enCours = extraitActif(etat.extrait) || brouterActif(etat.extrait) || etat.donneesAttendues;
  if (carte.getZoom() < ZOOM_EXTRAIT && !enCours && !forcer) { afficherExtrait(null); return; }
  const parametres = new URLSearchParams(Object.entries(zoneVue()).map(([k, v]) => [k, v.toFixed(5)]));
  try {
    afficherExtrait(await api(`extrait?${parametres}`));
  } catch (e) { /* serveur momentanément injoignable : la ligne reste telle quelle */ }
}

function afficherExtrait(r) {
  const avant = extraitActif(etat.extrait) ? etat.extrait.en_cours.id : null;
  etat.extrait = r;
  if (r?.installe) afficherDisponibilite({ pret: true, source: "extrait", nom: r.installe.nom });
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
  clearTimeout(minuterieExtrait);
  minuterieExtrait = setTimeout(majExtrait, 600);
});

// Fonds de carte et contrôle des calques, refaits quand la clé IGN ou la
// langue change ; le fond affiché reste le même.
function construireFonds() {
  const cleActive = Object.keys(couchesFonds).find((cle) => couchesFonds[cle] === fondActif);
  let clePreferee = null;
  try { clePreferee = localStorage.getItem(CLE_FOND); } catch (erreur) { /* fond par défaut */ }
  couchesFonds = {};
  if (!horsFrance && etat.cleIgn) {
    couchesFonds.scan25 = L.tileLayer(tuileIgn("GEOGRAPHICALGRIDSYSTEMS.MAPS", "image/jpeg", etat.cleIgn),
      { maxNativeZoom: 16, maxZoom: 19, attribution: IGN });
  }
  if (!horsFrance) {
    couchesFonds.plan = L.tileLayer(tuileIgn("GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2", "image/png"),
      { maxNativeZoom: 18, maxZoom: 19, attribution: IGN });
    couchesFonds.photos = L.tileLayer(tuileIgn("ORTHOIMAGERY.ORTHOPHOTOS", "image/jpeg"),
      { maxNativeZoom: 19, maxZoom: 19, attribution: IGN });
    couchesFonds.reliefLidar = L.tileLayer(
      tuileIgn("IGNF_LIDAR-HD_MNT_ELEVATION.ELEVATIONGRIDCOVERAGE.SHADOW", "image/png", null, "PM_0_18"),
      { maxNativeZoom: 18, maxZoom: 19, attribution: IGN },
    );
  }
  couchesFonds.osmRando = L.tileLayer("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    { maxNativeZoom: 17, maxZoom: 19,
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>, SRTM '
        + '| © <a href="https://opentopomap.org/">OpenTopoMap</a> (CC-BY-SA)' });
  couchesFonds.osm = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    { maxNativeZoom: 19, maxZoom: 19,
      attribution: `© <a href="https://www.openstreetmap.org/copyright">${t("attribution.osm")}</a>` });
  couchesFonds.osmVelo = L.tileLayer("https://{s}.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png",
    { maxNativeZoom: 18, maxZoom: 19,
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> '
        + '· <a href="https://www.cyclosm.org/">CyclOSM</a>' });
  couchesFonds.satellite = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    { maxNativeZoom: 19, maxZoom: 19,
      attribution: 'Esri, Vantor, Earthstar Geographics, and the GIS User Community' });
  if (controleFonds) controleFonds.remove();
  if (fondActif) fondActif.remove();
  const choix = horsFrance
    ? ((clePreferee && couchesFonds[clePreferee]) ? clePreferee : "osm")
    : (clePreferee || (cleActive === "osm" ? "plan" : cleActive));
  fondActif = (couchesFonds[choix] || couchesFonds.plan || couchesFonds.osm).addTo(carte);
  ajusterRecouvrementTuiles();
  const fonds = Object.fromEntries(Object.entries(couchesFonds).map(([cle, couche]) => [t(`fond.${cle}`), couche]));
  const calques = Object.fromEntries(Object.entries(CALQUES)
    .filter(([cle]) => !horsFrance || cle === "osm")
    .map(([cle, c]) => [t(`calque.${cle}`), c.groupe]));
  controleFonds = L.control.layers(fonds, calques, { collapsed: false, position: "topright" }).addTo(carte);
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
  const ign = !horsFrance && $("ign").checked;
  afficherStatut(() => t("statut.calcul") + (ign ? t("statut.calculIgn") : "."));
  occupe(true);
  let reponse;
  try {
    reponse = await api("itineraire", {
      points: etat.points.map((p) => [p.lat, p.lon]),
      strict: $("strict").checked,
      ign,
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
  chargerJournal();
}

// ------------------------------------------------------------ journal

// Les dernières lignes du journal des calculs (erreurs, blocages, lenteurs),
// relues à l'ouverture de la section et après chaque calcul.
async function chargerJournal() {
  if ($("pane-journal").hidden) return;
  try {
    const j = await api("journal");
    $("cheminJournal").textContent = j.chemin;
    $("lignesJournal").textContent = j.lignes.length ? j.lignes.join("\n") : t("journal.vide");
    $("lignesJournal").scrollTop = $("lignesJournal").scrollHeight;
  } catch (e) {
    $("lignesJournal").textContent = t("journal.illisible", { message: e.message });
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
  $("resultat").hidden = false;
  $("exporter").disabled = false;
  actualiserDisponibilite();
  // Repli sur OSM seul : les chemins IGN demandés n'ont pas pu servir, il faut le voir.
  afficherStatut(() => {
    const bilan = t("statut.bilan", { duree: decimal(r.duree_s, 2), total: r.franchissements.length });
    if (!r.avertissement) return bilan;
    const avertissement = langue === "en" ? t("avertissement.ign", { detail: r.avertissement_detail }) : r.avertissement;
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
  chargerJournal();
}

function ecrireDenivele(d) {
  $("denivele").textContent = `D+ ${d.montee_m} m\nD− ${d.descente_m} m`;
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
    + t("gpx.barrieres") + ((r.portions_ign || []).length ? t("gpx.bdtopo") : "") + t("gpx.trace");
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
new PleinEcran().addTo(carte);
// Échap quitte le plein écran du navigateur : la page revient avec lui.
document.addEventListener("fullscreenchange", () => {
  if (!document.fullscreenElement && document.body.classList.contains("plein-ecran")) appliquerPleinEcran(false);
});
const CLE_OPTIONS = "hike2gpx.options";
function restaurerOptions() {
  try {
    const options = JSON.parse(localStorage.getItem(CLE_OPTIONS) || "null");
    if (!options || typeof options !== "object") return;
    for (const id of ["strict", "ign", "comparer"]) {
      if (typeof options[id] === "boolean") $(id).checked = options[id];
    }
  } catch (erreur) { /* conserver les valeurs par défaut */ }
}
function memoriserOptions() {
  const options = Object.fromEntries(["strict", "ign", "comparer"].map((id) => [id, $(id).checked]));
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
  $(id).addEventListener("change", () => { memoriserOptions(); planifierCalcul(); });
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
    if (action === "vider_cache") $("cacheStatus").textContent = t("donnees.vide");
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
  rafraichirCalques();
}

demarrer();
setInterval(verifierBrouter, 60 * 60 * 1000);
