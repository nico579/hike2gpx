"use strict";

// Page de tracé de hike2gpx : points posés sur la carte, itinéraire calculé
// par le serveur local (BRouter et les coupes des franchissements), export
// GPX. Les textes venus d'OpenStreetMap passent toujours par textContent.

const DELAI_CALCUL_MS = 250;
const CLE_VUE = "hike2gpx.vue";
const CLE_POINTS = "hike2gpx.points";
const COULEURS = { blocked: "#d32f2f", uncertain: "#ef6c00" };
// DEBUT LEGENDE couleur : généré par tools/generer_legende.py depuis hike2gpx/assets/legende.json : ne pas modifier à la main
const COULEUR_CHEMINS_OFFICIELS = "#00897b";   // chemins de toutes les cartographies nationales
// FIN LEGENDE couleur
const LEGENDE_STATUT = { blocked: "bloque", uncertain: "verifier" };   // statut d'un franchissement -> ligne de légende

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
    "menu.titre": "Menu",
    "menu.recherche": "Recherche",
    "menu.cartes": "Gestion des cartes",
    "menu.itineraires": "Gestion des itinéraires",
    "menu.trace": "Planifier un itinéraire",
    "menu.reglages": "Réglages",
    "menu.aide": "Aide",
    "menu.fermer": "Fermer",
    "panneau.poignee": "Glisser pour changer la largeur du panneau (double-clic : largeur d’origine)",
    "cartes.fondTitre": "En ligne",
    "cartes.fondNote": "Les cartes servies par Internet : celles du pays affiché, puis celles du monde. La carte nationale suit le pays du centre de la carte. Le SCAN 25 demande la clé IGN des réglages.",
    "cartes.calquesTitre": "Superposition des chemins",
    "cartes.horsLigneTitre": "Téléchargement pour usage hors ligne",
    "cartes.horsLigneNote": "Ce PC fabrique les fonds de carte par cases de 1° pour les partager au téléphone, qui s'en sert sans réseau. Ils ne s'affichent pas sur le PC, qui reste en ligne.",
    "itineraires.calculTitre": "Mode de calcul",
    "itineraires.zonesTitre": "Zones stockées localement",
    "itineraires.zonesNote": "Les zones de routage, par cases de 5°, se téléchargent depuis le serveur ; celles qu'il ne publie pas se fabriquent sur ce PC.",
    "horsLigne.quoi": "À télécharger",
    "horsLigne.modeRoutage": "Données de routage (cases de 5°)",
    "horsLigne.modeFond": "Fond de carte (cases de 1°)",
    "horsLigne.fondAucun": "Le fond affiché ne se garde pas hors ligne. Choisissez dans la liste du haut : {liste}.",
    "reglages.afficherLegende": "Afficher la légende",
    "reglages.zonesAuto": "Télécharger automatiquement les zones de routage (une question par zone)",
    "reglages.dossierDonnees": "Dossier des données",
    "reglages.deplacer": "Déplacer",
    "reglages.dossierNote": "Les cartes, les zones et les extraits OSM pèsent des Go : un autre disque peut les recevoir. Indiquez le dossier, puis « Déplacer » ; hike2gpx redémarre sur la copie.",
    "reglages.confirmerDeplacement": "Déplacer toutes les données de hike2gpx dans {dossier} ?\n\nLa copie peut durer quelques minutes ; hike2gpx redémarre ensuite sur elle et efface l'ancien dossier.",
    "horsLigne.titreDeplacement": "Dossier des données",
    "horsLigne.deplacement": "Copie des données{compte}, depuis {duree}",
    "horsLigne.deplace": "Données copiées dans {dossier} : hike2gpx redémarre, rechargez la page dans quelques secondes.",
    "zones.question": "Pour calculer sans réseau, avec les chemins de la carte nationale, hike2gpx peut télécharger la zone de routage de cette région (case {nom}, {taille}). La télécharger maintenant ?",
    "zones.refusee": "Zone {nom} non téléchargée. Vous pourrez la télécharger à tout moment depuis « Gestion des itinéraires ».",
    "horsLigne.legendeInstalle": "sur ce PC",
    "horsLigne.legendeSelection": "sélectionné",
    "horsLigne.legendeEnCours": "en cours",
    "horsLigne.legendeServeur": "sur le serveur",
    "horsLigne.aideRoutage": "Cliquez les cases de 5° à télécharger, partager ou exporter ; un second clic les désélectionne.",
    "horsLigne.aideFond": "Cliquez les cases de 1° à télécharger, partager ou exporter ; un second clic les désélectionne.",
    "horsLigne.aideZoom": "Rapprochez-vous pour voir les cases de 1° du fond de carte.",
    "horsLigne.infoInstalle": "sur ce PC, {taille}",
    "horsLigne.infoServeur": "sur le serveur, {taille}",
    "horsLigne.infoFabriquer": "pas sur le serveur : à fabriquer sur ce PC, environ une heure",
    "horsLigne.infoCarre": "pas de fond sur ce PC",
    "horsLigne.selVide": "Aucune case sélectionnée.",
    "horsLigne.selRien": "Déjà à jour sur ce PC.",
    "horsLigne.selTelecharger": "{n} à télécharger : {taille}.",
    "horsLigne.selFabriquer": "{n} à fabriquer sur ce PC : environ {duree}.",
    "horsLigne.selFonds": "{n} case(s) : environ {taille} et {duree}.",
    "horsLigne.selInstallees": "{n} déjà sur ce PC ({taille}).",
    "horsLigne.telecharger": "Télécharger",
    "horsLigne.partager": "Partager",
    "horsLigne.exporter": "Exporter",
    "horsLigne.infoExporter": "Enregistre dans une archive zip ce que la sélection a sur ce PC, à copier sur un autre PC qui l'importe.",
    "horsLigne.importer": "Importer",
    "horsLigne.infoImporter": "Installe sur ce PC les cartes et les zones d'une archive zip exportée par un autre hike2gpx.",
    "horsLigne.importEnCours": "Import de {nom} ({taille}) en cours…",
    "horsLigne.importFini": "{nom} importée : {n} carte(s) et {z} zone(s) de routage.",
    "horsLigne.importErreur": "{nom} non importée : {erreur}",
    "horsLigne.exportEnCours": "Export de {nom} : {fait}{total}",
    "horsLigne.exportFini": "{nom} enregistrée ({taille}).",
    "horsLigne.exportErreur": "{nom} non enregistrée : {erreur}",
    "horsLigne.infoTelechargerFond": "Télécharge sur ce PC le fond choisi en haut, pour les cases sélectionnées, afin de le partager au téléphone.",
    "horsLigne.infoTelechargerRoutage": "Télécharge du serveur les zones sélectionnées, ou les fabrique sur ce PC quand le serveur ne les publie pas.",
    "horsLigne.infoPartager": "Partage au téléphone ce que la sélection a sur ce PC : un QR code s'affiche, à scanner avec hike2gpx sur le téléphone, qui récupère tout d'un coup.",
    "horsLigne.enAttente": "({n} en attente)",
    "aide": "Cliquez sur la carte pour poser le départ, puis les étapes et l'arrivée. Faites glisser un point pour le déplacer ; « Revenir au départ » ferme une boucle.",
    "bouton.retirerDernier": "Retirer",
    "bouton.retirerDernierInfo": "Retire le dernier point ajouté au parcours.",
    "bouton.toutEffacer": "Effacer",
    "bouton.toutEffacerInfo": "Efface tous les points et le tracé du parcours en cours.",
    "bouton.boucler": "Revenir",
    "bouton.bouclerInfo": "Ajoute le point de départ à la fin du parcours pour fermer la boucle.",
    "bouton.exporter": "Exporter le GPX",
    "bouton.chargerGpx": "Importer un GPX ou un KML",
    "bouton.supprimerGpx": "Retirer l'import",
    "gpx.erreur": "Impossible de charger ce fichier : {message}",
    "gpx.invalide": "fichier GPX ou KML invalide, ou sans tracé.",
    "trace.date": "Date : {date}",
    "trace.distance": "Distance : {km}",
    "trace.denivele": "Dénivelé : + {plus} m / − {moins} m ({modele})",
    "trace.deniveleNom": "Dénivelé : + {plus} m",
    "trace.duree": "Durée : {duree}",
    "gpx.tropGrand": "fichier trop volumineux (20 Mo maximum).",
    "option.strict": "Inclure les blocages à vérifier",
    "option.cheminsRoutables": "Inclure les chemins {nom}",
    "option.cheminsAffichage": "{nom} : affichage seul, calcul sur les chemins OSM",
    "option.comparer": "Comparer avec le tracé standard (qui ignore les barrières)",
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
    // DEBUT LEGENDE fr : généré par tools/generer_legende.py depuis hike2gpx/assets/legende.json : ne pas modifier à la main
    "legende.titre": "Légende",
    "legende.fermer": "Masquer la légende",
    "legende.osm": "chemin OSM",
    "legende.chemins_officiels": "chemin {reseau}",
    "legende.itineraire": "tracé itinéraire",
    "legende.gpx": "import GPX",
    "legende.barriere": "clôture et mur",
    "legende.bloque": "franchissement bloquant",
    "legende.verifier": "franchissement à vérifier",
    "legende.jonction": "chemin non raccordé (à vérifier)",
    // FIN LEGENDE fr
    "jonction.titre": "Chemin non raccordé",
    "jonction.detail": "Ce chemin s'arrête à {distance} m d'un autre sans le toucher dans OpenStreetMap : le calcul ne peut pas passer de l'un à l'autre. À vérifier sur place ou sur l'imagerie : il peut aussi s'agir d'un vrai cul-de-sac.",
    "jonction.isole": "Ce chemin n'est relié à aucun autre dans OpenStreetMap, et passe à {distance} m de l'un d'eux : le calcul ne peut pas l'emprunter. À vérifier sur place ou sur l'imagerie : il manque sans doute un raccord.",
    "jonction.corriger": "Corriger dans OpenStreetMap",
    "reglages.titre": "Réglages",
    "reglages.cle": "Clé IGN pour le SCAN 25",
    "reglages.note": "Le SCAN 25 n'est pas une donnée libre. Sans clé, la carte utilise le Plan IGN, sous Licence Ouverte.",
    "reglages.renouvellement": "Renouveler les données locales après",
    "reglages.jours": "jours",
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
    "disponibilite.attente.segments": "Cases BRouter en cours de téléchargement",
    "disponibilite.attente.osm": "Données OSM ou Overpass en attente",
    "disponibilite.attente.source": "Chemins officiels indisponibles dans cette zone",
    "disponibilite.attente.zone": "Zone du parcours à préciser",
    "disponibilite.info.titre": "Sources du prochain calcul",
    "disponibilite.info.verification": "Vérification des données en cours…",
    "disponibilite.info.overpass": "Overpass",
    "disponibilite.info.lot": "Zone de routage hors ligne",
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
    "donnees.brouter": "Cases BRouter {noms} : {taille}",
    "donnees.restes": "Fichiers inutiles : {taille}",
    "donnees.vider": "Vider",
    "donnees.actualiser": "Actualiser",
    "donnees.supprimer": "Supprimer",
    "zones.aucune": "Aucune zone de routage installée.",
    "zones.enrichi": "enrichi {sources}",
    "zones.confirmer": "Supprimer de ce PC la zone {nom} ({taille}) ? Celle du serveur se retéléchargera si un parcours y passe.",
    "zones.supprimee": "Zone {nom} supprimée, {taille} libérés.",
    "zones.aucuneCarte": "Aucune zone de carte sur ce PC.",
    "zones.montrer": "Centrer la carte sur cette zone",
    "zones.confirmerCarte": "Supprimer de ce PC la zone {nom} de la carte {carte} ({taille}) ? Elle serait à retélécharger pour la partager au téléphone.",
    "donnees.nettoyer": "Nettoyer",
    "donnees.confirmer": "Supprimer l'extrait {nom} ? Il se retéléchargera de lui-même s'il resert.",
    "donnees.viderTout": "Vider le cache",
    "donnees.aideCache": "Détail des caches vidés",
    "donnees.detailCache": "Ce bouton efface les réponses Overpass et les franchissements OSM, les chemins officiels, les extraits OSM téléchargés, les données BRouter et les modèles d'altitude gpx2elev. Ils seront retéléchargés au besoin. Les tuiles des fonds de carte, conservées dans le cache du navigateur, ne sont pas effacées.",
    "donnees.confirmerTout": "Vider les données locales OSM, IGN, gpx2elev et BRouter, ainsi que les zones de routage et les fonds hors ligne ? Les données en ligne et les zones de routage du serveur seront retéléchargées au besoin ; les zones de routage et les fonds préparés sur cet ordinateur seront à refaire. Les tuiles de fond de carte affichées restent dans le cache du navigateur.",
    "donnees.vide": "Cache local vidé, zones de routage et fonds hors ligne compris. Les tuiles du fond de carte affiché restent gérées par le navigateur.",
    "donnees.infoCache": "Les tuiles IGN et OSM du fond de carte restent dans le cache du navigateur.",
    "unite.mo": "Mo",
    "unite.go": "Go",
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
    "reglages.zoomCalques": "Zoom minimal des calques",
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
    "attribution.osm": "contributeurs OpenStreetMap",
    "cle.enregistree": "Clé enregistrée : SCAN 25 disponible.",
    "cle.retiree": "Clé retirée : Plan IGN par défaut.",
    "aide.titre": "Aide : le mode d'emploi (README)",
    "horsLigne.mettreAJour": "Mettre à jour",
    "horsLigne.arreter": "Arrêter",
    "horsLigne.avancement": "Préparation de la case {nom} : {etape}{compte}, depuis {duree}",
    "horsLigne.titreCarte": "Carte hors ligne « {fond} »",
    "horsLigne.titreZone": "Zone de routage",
    "horsLigne.attenteCalques": "Chemins de la carte : en attente de la zone de routage hors ligne, qui se télécharge.",
    "horsLigne.attenteCalcul": "La zone de routage hors ligne se télécharge : le calcul reprendra dès son arrivée.",
    "horsLigne.automatique": "Zone de routage de la case {nom}, téléchargée d'elle-même depuis le serveur :{compte}, depuis {duree}. Elle prendra le relais du mode à la volée.",
    "horsLigne.fini": "Case {nom} prête hors ligne.",
    "horsLigne.perime": "La zone de routage hors ligne de {nom} date du {date}, au-delà du délai de renouvellement. La mettre à jour ?",
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
    "horsLigne.etape.fond": "téléchargement des tuiles",
    "horsLigne.etape.outils": "installation des outils de carte",
    "horsLigne.etape.carte": "carte OpenStreetMap",
    "horsLigne.fondFini": "Fond de carte {nom} prêt hors ligne.",
    "partage.fermer": "Arrêter le partage",
    "partage.ouvert": "Partagé : {quoi}, {taille}. Dans hike2gpx sur le téléphone, sur le même Wi-Fi : « {page} », puis « Scanner le QR code de l’ordinateur » ; le téléphone demande une confirmation et récupère tout. Le code change à chaque partage.",
    "partage.rien": "Rien à partager : ce PC n’a ni zone de carte ni zone de routage.",
    "partage.etat": "Partage ouvert : {quoi}, {taille}.",
    "partage.zonesCarte1": "1 zone de carte",
    "partage.zonesCarte": "{n} zones de carte",
    "partage.zonesRoutage1": "1 zone de routage",
    "partage.zonesRoutage": "{n} zones de routage",
    "partage.et": " et ",
    "partage.titre": "Partager au téléphone",
    "partage.pareFeu": "Attention : le pare-feu de Windows n’autorise pas encore hike2gpx, le téléphone ne pourra pas joindre le PC. Rouvrez le partage et acceptez la demande d’autorisation de Windows.",
    "partage.revoir": "Afficher le QR code",
    "partage.fermerFenetre": "Fermer",
    "partage.erreur": "Partage impossible : {erreur}",
    "pleinEcran.entrer": "Plein écran",
    "pleinEcran.quitter": "Quitter le plein écran",
    "etape.debut": "Préparation du calcul",
    "etape.donnees": "Lecture des données de la zone : {faites} / {total} tuiles",
    "etape.fusion": "Fusion avec les chemins officiels",
    "etape.tuiles": "Fabrication de la case BRouter",
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
    "menu.titre": "Menu",
    "menu.recherche": "Search",
    "menu.cartes": "Map management",
    "menu.itineraires": "Route management",
    "menu.trace": "Plan a route",
    "menu.reglages": "Settings",
    "menu.aide": "Help",
    "menu.fermer": "Close",
    "panneau.poignee": "Drag to resize the panel (double-click: default width)",
    "cartes.fondTitre": "Online",
    "cartes.fondNote": "Maps served over the Internet: those of the country shown, then those of the world. The national map follows the country at the map centre. SCAN 25 needs the IGN key from the settings.",
    "cartes.calquesTitre": "Path overlays",
    "cartes.horsLigneTitre": "Download for offline use",
    "cartes.horsLigneNote": "This PC builds base maps in 1° cells to share them with the phone, which uses them without a network. They are not shown on the PC, which stays online.",
    "itineraires.calculTitre": "Calculation mode",
    "itineraires.zonesTitre": "Zones stored locally",
    "itineraires.zonesNote": "Routing areas, in 5° cells, are downloaded from the server; those it does not publish are built on this PC.",
    "horsLigne.quoi": "To download",
    "horsLigne.modeRoutage": "Routing data (5° cells)",
    "horsLigne.modeFond": "Base map (1° cells)",
    "horsLigne.fondAucun": "The base map shown cannot be kept offline. Choose in the list above: {liste}.",
    "reglages.afficherLegende": "Show the legend",
    "reglages.zonesAuto": "Download routing areas automatically (one question per area)",
    "reglages.dossierDonnees": "Data folder",
    "reglages.deplacer": "Move",
    "reglages.dossierNote": "Maps, areas and OSM extracts weigh GBs: another disk can take them. Enter the folder, then \"Move\"; hike2gpx restarts on the copy.",
    "reglages.confirmerDeplacement": "Move all hike2gpx data to {dossier}?\n\nThe copy may take a few minutes; hike2gpx then restarts on it and deletes the old folder.",
    "horsLigne.titreDeplacement": "Data folder",
    "horsLigne.deplacement": "Copying the data{compte}, for {duree}",
    "horsLigne.deplace": "Data copied to {dossier}: hike2gpx is restarting, reload the page in a few seconds.",
    "zones.question": "To compute with no network, with the paths of the national map, hike2gpx can download the routing area of this region (cell {nom}, {taille}). Download it now?",
    "zones.refusee": "Area {nom} not downloaded. You can download it at any time from “Route management”.",
    "horsLigne.legendeInstalle": "on this PC",
    "horsLigne.legendeSelection": "selected",
    "horsLigne.legendeEnCours": "in progress",
    "horsLigne.legendeServeur": "on the server",
    "horsLigne.aideRoutage": "Click the 5° cells to download, share or export; a second click deselects them.",
    "horsLigne.aideFond": "Click the 1° cells to download, share or export; a second click deselects them.",
    "horsLigne.aideZoom": "Zoom in to see the 1° cells of the base map.",
    "horsLigne.infoInstalle": "on this PC, {taille}",
    "horsLigne.infoServeur": "on the server, {taille}",
    "horsLigne.infoFabriquer": "not on the server: to build on this PC, about an hour",
    "horsLigne.infoCarre": "no base map on this PC",
    "horsLigne.selVide": "No cell selected.",
    "horsLigne.selRien": "Already up to date on this PC.",
    "horsLigne.selTelecharger": "{n} to download: {taille}.",
    "horsLigne.selFabriquer": "{n} to build on this PC: about {duree}.",
    "horsLigne.selFonds": "{n} cell(s): about {taille} and {duree}.",
    "horsLigne.selInstallees": "{n} already on this PC ({taille}).",
    "horsLigne.telecharger": "Download",
    "horsLigne.partager": "Share",
    "horsLigne.exporter": "Export",
    "horsLigne.infoExporter": "Saves what the selection has on this PC to a zip archive, to copy to another PC that imports it.",
    "horsLigne.importer": "Import",
    "horsLigne.infoImporter": "Installs on this PC the maps and areas of a zip archive exported by another hike2gpx.",
    "horsLigne.importEnCours": "Importing {nom} ({taille})…",
    "horsLigne.importFini": "{nom} imported: {n} map(s) and {z} routing area(s).",
    "horsLigne.importErreur": "{nom} not imported: {erreur}",
    "horsLigne.exportEnCours": "Exporting {nom}: {fait}{total}",
    "horsLigne.exportFini": "{nom} saved ({taille}).",
    "horsLigne.exportErreur": "{nom} not saved: {erreur}",
    "horsLigne.infoTelechargerFond": "Downloads to this PC the base map chosen above, for the selected cells, to share it with the phone.",
    "horsLigne.infoTelechargerRoutage": "Downloads the selected zones from the server, or builds them on this PC when the server does not publish them.",
    "horsLigne.infoPartager": "Shares with the phone what the selection has on this PC: a QR code shows, to scan with hike2gpx on the phone, which gets everything at once.",
    "horsLigne.enAttente": "({n} waiting)",
    "aide": "Click the map to place the start, then the waypoints and the finish. Drag a point to move it; “Back to start” closes a loop.",
    "bouton.retirerDernier": "Remove",
    "bouton.retirerDernierInfo": "Removes the last point added to the route.",
    "bouton.toutEffacer": "Clear",
    "bouton.toutEffacerInfo": "Clears all points and the current route.",
    "bouton.boucler": "Return",
    "bouton.bouclerInfo": "Adds the starting point to the end of the route to close the loop.",
    "bouton.exporter": "Export GPX",
    "bouton.chargerGpx": "Import a GPX or KML",
    "bouton.supprimerGpx": "Remove the import",
    "gpx.erreur": "Unable to load this file: {message}",
    "gpx.invalide": "invalid GPX or KML file, or no track found.",
    "trace.date": "Date: {date}",
    "trace.distance": "Distance: {km}",
    "trace.denivele": "Elevation: + {plus} m / − {moins} m ({modele})",
    "trace.deniveleNom": "Elevation gain: + {plus} m",
    "trace.duree": "Time: {duree}",
    "gpx.tropGrand": "file too large (20 MB maximum).",
    "option.strict": "Include crossings to check",
    "option.cheminsRoutables": "Include {nom} paths",
    "option.cheminsAffichage": "{nom}: map display only; routing uses OSM paths",
    "option.comparer": "Compare with the standard route (which ignores barriers)",
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
    // DEBUT LEGENDE en : généré par tools/generer_legende.py depuis hike2gpx/assets/legende.json : ne pas modifier à la main
    "legende.titre": "Legend",
    "legende.fermer": "Hide the legend",
    "legende.osm": "OSM path",
    "legende.chemins_officiels": "{reseau} path",
    "legende.itineraire": "route",
    "legende.gpx": "GPX import",
    "legende.barriere": "fence and wall",
    "legende.bloque": "blocking crossing",
    "legende.verifier": "crossing to check",
    "legende.jonction": "unconnected path (to check)",
    // FIN LEGENDE en
    "jonction.titre": "Unconnected path",
    "jonction.detail": "This path ends {distance} m from another one without touching it in OpenStreetMap: routing cannot go from one to the other. Check on site or on imagery: it may also be a real dead end.",
    "jonction.isole": "This path is connected to no other in OpenStreetMap, and passes {distance} m from one of them: routing cannot use it. Check on site or on imagery: a junction is probably missing.",
    "jonction.corriger": "Fix in OpenStreetMap",
    "reglages.titre": "Settings",
    "reglages.cle": "IGN key for SCAN 25",
    "reglages.note": "SCAN 25 is not open data. Without a key, the map uses Plan IGN, under the Open Licence.",
    "reglages.renouvellement": "Refresh local data after",
    "reglages.jours": "days",
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
    "disponibilite.attente.segments": "BRouter cells downloading",
    "disponibilite.attente.osm": "Waiting for OSM data or Overpass",
    "disponibilite.attente.source": "Official paths unavailable in this area",
    "disponibilite.attente.zone": "Route area needs to be specified",
    "disponibilite.info.titre": "Sources for the next route",
    "disponibilite.info.verification": "Checking data…",
    "disponibilite.info.overpass": "Overpass",
    "disponibilite.info.lot": "Offline routing area",
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
    "donnees.brouter": "BRouter cells {noms}: {taille}",
    "donnees.restes": "Leftover files: {taille}",
    "donnees.vider": "Clear",
    "donnees.actualiser": "Refresh",
    "donnees.supprimer": "Delete",
    "zones.aucune": "No routing area installed.",
    "zones.enrichi": "enriched {sources}",
    "zones.confirmer": "Delete the {nom} zone ({taille}) from this PC? The server's will download again if a route goes there.",
    "zones.supprimee": "Zone {nom} deleted, {taille} freed.",
    "zones.aucuneCarte": "No map zone on this PC.",
    "zones.montrer": "Centre the map on this zone",
    "zones.confirmerCarte": "Delete the {nom} zone of the {carte} map ({taille}) from this PC? It would have to be downloaded again to share it with the phone.",
    "donnees.nettoyer": "Clean up",
    "donnees.confirmer": "Delete the {nom} extract? It will download again by itself if needed.",
    "donnees.viderTout": "Clear cache",
    "donnees.aideCache": "Details of cleared caches",
    "donnees.detailCache": "This clears Overpass responses and OSM crossings, official paths, downloaded OSM extracts, BRouter data and gpx2elev elevation models. They are downloaded again when needed. Background map tiles held in the browser cache are not cleared.",
    "donnees.confirmerTout": "Clear local OSM, IGN, gpx2elev and BRouter data, and the offline routing areas and maps? Online data and the server's routing areas will download again when needed; routing areas and maps prepared on this computer will have to be made again. Displayed background map tiles remain in the browser cache.",
    "donnees.vide": "Local cache cleared, offline routing areas and maps included. Displayed background map tiles remain managed by the browser.",
    "donnees.infoCache": "IGN and OSM background map tiles remain in the browser cache.",
    "unite.mo": "MB",
    "unite.go": "GB",
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
    "reglages.zoomCalques": "Minimum zoom for layers",
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
    "attribution.osm": "OpenStreetMap contributors",
    "cle.enregistree": "Key saved: SCAN 25 available.",
    "cle.retiree": "Key removed: Plan IGN by default.",
    "aide.titre": "Help: the user guide (README)",
    "horsLigne.mettreAJour": "Update",
    "horsLigne.arreter": "Stop",
    "horsLigne.avancement": "Preparing cell {nom}: {etape}{compte}, for {duree}",
    "horsLigne.titreCarte": "Offline map “{fond}”",
    "horsLigne.titreZone": "Routing area",
    "horsLigne.attenteCalques": "Map paths: waiting for the offline routing area, which is downloading.",
    "horsLigne.attenteCalcul": "The offline routing area is downloading: the route will be computed as soon as it arrives.",
    "horsLigne.automatique": "Routing area of the {nom} cell, downloading by itself from the server:{compte}, for {duree}. It will take over from on-the-fly mode.",
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
    "horsLigne.etape.fond": "downloading tiles",
    "horsLigne.etape.outils": "installing the map tools",
    "horsLigne.etape.carte": "OpenStreetMap map",
    "horsLigne.fondFini": "Base map {nom} ready offline.",
    "partage.fermer": "Stop sharing",
    "partage.ouvert": "Shared: {quoi}, {taille}. In hike2gpx on the phone, on the same Wi-Fi: “{page}”, then “Scan the computer’s QR code”; the phone asks for one confirmation and gets everything. The code changes with every share.",
    "partage.rien": "Nothing to share: this PC has no map zone and no routing zone.",
    "partage.etat": "Sharing open: {quoi}, {taille}.",
    "partage.zonesCarte1": "1 map zone",
    "partage.zonesCarte": "{n} map zones",
    "partage.zonesRoutage1": "1 routing zone",
    "partage.zonesRoutage": "{n} routing zones",
    "partage.et": " and ",
    "partage.titre": "Share with the phone",
    "partage.pareFeu": "Warning: the Windows firewall does not allow hike2gpx yet, so the phone cannot reach the PC. Share again and accept the Windows authorisation request.",
    "partage.revoir": "Show the QR code",
    "partage.fermerFenetre": "Close",
    "partage.erreur": "Sharing failed: {erreur}",
    "pleinEcran.entrer": "Full screen",
    "pleinEcran.quitter": "Exit full screen",
    "etape.debut": "Preparing the calculation",
    "etape.donnees": "Reading the area's data: {faites} / {total} tiles",
    "etape.fusion": "Merging official paths",
    "etape.tuiles": "Building the BRouter cell",
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
  if (traduit ?? SERVEUR_EN[texte]) return traduit ?? SERVEUR_EN[texte];
  // « Chemin IGN absent d'OpenStreetMap : ... » : le nom du réseau change selon le pays.
  const officiel = /^Chemin (.+) absent d'OpenStreetMap : existence et accès à vérifier$/.exec(texte);
  return officiel ? `${officiel[1]} path missing from OpenStreetMap: existence and access to check` : texte;
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
  for (const id of ["menuPrincipal", "menuButton"]) $(id).setAttribute("aria-label", t("menu.titre"));
  $("menuButton").title = t("menu.titre");
  $("pageFermer").title = t("menu.fermer");
  $("legendFermer").title = t("legende.fermer");
  $("legendFermer").setAttribute("aria-label", t("legende.fermer"));
  $("poigneePanneau").title = t("panneau.poignee");
  $("poigneePanneau").setAttribute("aria-label", t("panneau.poignee"));
  $("pageFermer").setAttribute("aria-label", t("menu.fermer"));
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
  // Une zone que le serveur téléchargerait de lui-même : la page demande d'abord, une fois par case.
  if (donnees.zone_a_proposer) proposerZone(donnees.zone_a_proposer);
  return donnees;
}

// Une zone de routage pèse plusieurs centaines de Mo : la première fois qu'un
// calcul ou un calque en a besoin, la page demande (le serveur retient la
// réponse). Un refus rappelle où la télécharger à la main.
const zonesDemandees = new Set();
async function proposerZone(zone) {
  if (!zone?.case || zonesDemandees.has(zone.case)) return;
  zonesDemandees.add(zone.case);
  const accepter = confirm(t("zones.question", { nom: zone.case, taille: tailleTexte(zone.octets) }));
  try {
    const r = await api("zone_reponse", { case: zone.case, accepter });
    if (accepter && r.lot_en_cours?.actif && !minuterieLot) suivreLot();
  } catch (e) {
    zonesDemandees.delete(zone.case);     // la question reviendra au prochain calcul
    return;
  }
  if (!accepter) afficherStatut(() => t("zones.refusee", { nom: zone.case }));
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
// L'échelle de la carte, en haut à droite de la recherche de ville (demande
// de Nico du 2026-10-28) : elle reste là quand la recherche est repliée ;
// Leaflet la tient à jour où qu'elle soit.
const echelle = L.control.scale({ imperial: false, maxWidth: 120 }).addTo(carte).getContainer();
echelle.classList.add("echelle-entete");
$("citySearch").after(echelle);
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
// Comme sur le téléphone, le champ de recherche se referme dès que le lieu
// est sur la carte : presentation.js, qui l'ouvre depuis le menu, l'écoute.
function rechercheAboutie() {
  if (typeof CustomEvent !== "undefined") document.dispatchEvent(new CustomEvent("hike2gpx:recherche-aboutie"));
}
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
    rechercheAboutie();
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
        rechercheAboutie();
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
// Le nom d'une coche de « Superposition des chemins » : la source seule
// (« OSM », « IGN », « ATKIS »…), le titre de la section disant le reste.
// Les autres calques (sentiers balisés d'un pays) gardent leur nom.
function nomCoche(cle) {
  if (cle === "osm") return "OSM";
  return CHEMINS_OFFICIELS[cle]?.label || nomCalque(cle);
}
function nomFond(cle) {
  return FOURNISSEURS_CARTES[paysCarte]?.baseNames?.[cle]?.[langue] || t(`fond.${cle}`);
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
let fondVoulu = null;      // la carte d'une zone cliquée, en attente du pays de la zone
let cleFondActif = null;    // sa clé (providers/<pays>.js), celle d'un fond à garder hors ligne
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
    cleFondActif = cle;
    // Le volet des fonds hors ligne suit le fond choisi : ses cases et son bilan en dépendent.
    if (horsLigne.actif) dessinerCases();
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
// Un KML porte souvent des centaines de traces : un seul canevas, une marge de clic de 6 px.
const renduImport = L.canvas({ pane: "gpxImporte", tolerance: 6 });
let nomGpxImporte = null;
let sequenceImportGpx = 0;
const rendu = L.canvas({ padding: 0.2 });
const renduObstacles = L.canvas({ padding: 0.2, pane: "obstaclesOsm" });
// Le zoom à partir duquel les calques se dessinent : réglable (Réglages), de 14, où
// le lot et le serveur n'ont plus de tuile plus large, à 19. 14 par défaut au grand
// écran du PC ; le téléphone, plus lent, en demande 16.
const ZOOM_CALQUES_MIN = 14, ZOOM_CALQUES_MAX = 19, ZOOM_CALQUES_DEFAUT = 14;
const CLE_ZOOM_CALQUES = "hike2gpx.zoomCalques";
function borneZoomCalques(valeur) {
  const n = Math.round(Number(valeur));
  return Number.isFinite(n) ? Math.max(ZOOM_CALQUES_MIN, Math.min(ZOOM_CALQUES_MAX, n)) : ZOOM_CALQUES_DEFAUT;
}
let zoomCalques = ZOOM_CALQUES_DEFAUT;
try { zoomCalques = borneZoomCalques(localStorage.getItem(CLE_ZOOM_CALQUES) ?? ZOOM_CALQUES_DEFAUT); } catch (erreur) {}
function reglerZoomCalques(valeur) {
  zoomCalques = borneZoomCalques(valeur);
  try { localStorage.setItem(CLE_ZOOM_CALQUES, String(zoomCalques)); } catch (erreur) {}
  rafraichirCalques();
}
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
      L.polyline(v.pts, { ...STYLES_OSM[v.genre], renderer: rendu, interactive: false, leg: "osm" }).addTo(groupe);
    }
    for (const b of donnees.barrieres) {
      L.polyline(b.pts, { color: "#e53935", weight: 3, renderer: rendu, leg: "barriere" })
        .bindTooltip(texte(`${ts(b.nature)} (OSM)`), { sticky: true }).addTo(groupe);
    }
    for (const f of donnees.franchissements || []) {
      L.circleMarker([f.lat, f.lon], { radius: 6, weight: 2, color: "#fff", fillOpacity: 1,
        fillColor: COULEURS[f.statut], renderer: renduObstacles, pane: "obstaclesOsm", leg: LEGENDE_STATUT[f.statut] })
        .bindPopup(() => bulleFranchissement(f)).addTo(groupe);
    }
    // Un chemin qui finit tout près d'un autre sans le toucher : le calcul n'y
    // passe pas. Jaune cerclé de brun, à part du rouge et de l'orange des
    // franchissements. Un lot fabriqué avant cette couche n'en a pas.
    for (const j of donnees.jonctions || []) {
      L.circleMarker([j.lat, j.lon], { radius: 6, weight: 2, color: "#4e342e", fillOpacity: 1,
        fillColor: "#fdd835", renderer: renduObstacles, pane: "obstaclesOsm", leg: "jonction" })
        .bindPopup(() => bulleJonction(j)).addTo(groupe);
    }
  },
};
for (const [cle, chemins] of Object.entries(CHEMINS_OFFICIELS)) {
  DESSINS[cle] = (groupe, donnees) => chemins.draw({ couleur: COULEUR_CHEMINS_OFFICIELS, L, groupe, donnees, rendu, texte, t });
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

// Une lecture brève (un lot installé, une vue déjà lue) ne montre rien : la
// note ne paraît que si la lecture dure encore au bout d'une seconde.
const DELAI_NOTE_LECTURE = 1000;
function debutLecture(cle, numero, nom) {
  lectures.set(cle, { numero, nom });
  if (!minuterieLectures) minuterieLectures = setTimeout(suivreLectures, DELAI_NOTE_LECTURE);
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
    // Un lot installé couvre la vue : la page lit et décode ses tuiles elle-même
    // (tuiles.js), comme le téléphone, au lieu de les attendre décodées en Python.
    if (donnees.tuiles) donnees = await lireCalqueDuLot(donnees);
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
  if (carte.getZoom() < zoomCalques) {
    // Vider plutôt que garder un morceau de réseau : de loin, il ferait
    // croire que le reste de la carte n'a pas de chemins.
    const interrompus = actifs.filter((cle) => abandonner(CALQUES[cle]));
    for (const cle of actifs) {
      CALQUES[cle].groupe.clearLayers();
      CALQUES[cle].charge = null;
    }
    arreterAuServeur(interrompus);
    noteCalques(t("calque.zoom", { niveau: zoomCalques }));
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
  afficherOptionChemins();
  majLegende();
}

// Les réseaux nationaux dont un calque est coché, une fois chacun : « IGN », « IGN / swissTLM3D »...
function reseauxCoches() {
  const noms = [];
  // Seuls les chemins qui ont des lots (paths : France, Suisse, Tchéquie, Allemagne, Pologne) ;
  // les couches d'affichage seul (sentiers espagnols, américains, suisses) gardent leur rendu.
  for (const f of Object.values(FOURNISSEURS_CARTES)) {
    const nom = f.paths?.label;
    if (!nom || noms.includes(nom)) continue;
    const couche = coucheCalque(f.paths.overlay);
    if (carte.hasLayer(couche) && couche.getLayers?.().length) noms.push(nom);
  }
  return noms;
}

// La légende ne montre que ce qui est sur la carte : les lignes des calques cochés, et
// celles dont un objet est dessiné (chaque objet porte son identifiant de ligne dans
// options.leg). Replanifiée à chaque ajout ou retrait de couche, une fois par image.
function majLegende() {
  const presentes = new Set();
  carte.eachLayer((couche) => { if (couche.options?.leg) presentes.add(couche.options.leg); });
  const reseaux = reseauxCoches();
  let visibles = 0;
  for (const ligne of $("legendRows").children) {
    const cle = ligne.dataset.legende;
    const visible = cle === "chemins_officiels" ? reseaux.length > 0 : presentes.has(cle);
    ligne.hidden = !visible;
    if (visible) visibles++;
    if (cle === "chemins_officiels" && visible)
      $("legendOfficielTexte").textContent = t("legende.chemins_officiels", { reseau: reseaux.join(" / ") });
  }
  $("mapLegend").classList.toggle("vide", visibles === 0);
}
let legendePlanifiee = false;
function planifierLegende() {
  if (legendePlanifiee) return;
  legendePlanifiee = true;
  requestAnimationFrame(() => { legendePlanifiee = false; majLegende(); });
}
carte.on("layeradd layerremove", planifierLegende);

function afficherOptionChemins() {
  const fournisseur = FOURNISSEURS_CARTES[paysCarte];
  const disponible = cheminsDisponibles(fournisseur?.paths);
  const couche = (disponible && fournisseur?.paths?.overlay) || fournisseur?.overlays?.[0];
  $("ignOption").hidden = !couche;
  const routable = Boolean(disponible && fournisseur?.paths?.source);
  $("ign").disabled = !routable;
  $("ign").checked = routable && choixIgn;
  if (couche) $("ignOptionTexte").textContent = t(routable ? "option.cheminsRoutables" : "option.cheminsAffichage",
    { nom: routable ? fournisseur.paths.label : nomCalque(couche) });
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
  if (controleFonds) controleFonds.remove();
  if (fondActif) fondActif.remove();
  const defaut = FOURNISSEURS_CARTES[paysCarte].defaultBase;
  // Une zone de carte cliquée dans la liste demande sa carte (fondVoulu) : elle
  // passe avant la préférence du pays, une fois ce pays reconnu.
  const voulu = fondVoulu && couchesFonds[fondVoulu] ? fondVoulu : null;
  fondVoulu = null;
  const choix = voulu || ((clePreferee && couchesFonds[clePreferee]) ? clePreferee : defaut);
  cleFondActif = [choix, "plan", "osm"].find((cle) => couchesFonds[cle]);
  fondActif = couchesFonds[cleFondActif].addTo(carte);
  ajusterRecouvrementTuiles();
  const fonds = Object.fromEntries(Object.entries(couchesFonds).map(([cle, couche]) => [nomFond(cle), couche]));
  const calques = Object.fromEntries(Object.entries(CALQUES)
    .filter(([cle]) => cle === "osm" || calquesDuPays().includes(cle))
    .map(([cle, c]) => [nomCoche(cle), c.groupe]));
  for (const cle of calquesDuPays()) {
    if (CALQUES_PAYS[cle]) calques[nomCoche(cle)] = CALQUES_PAYS[cle];
  }
  if (nomGpxImporte) calques[echapper(nomGpxImporte)] = traceGpxImporte;
  controleFonds = L.control.layers(fonds, calques, { collapsed: false, position: "topright" }).addTo(carte);
}

// ------------------------------------------------------------ hors ligne
// Le volet « Hors ligne » (proposition de Nico du 2026-11-05) : on choisit le
// routage (cases BRouter de 5°, lots du serveur ou fabriqués ici) ou le fond
// de carte (cases de 1°, fonds.py) ; la grille change en fonction. On
// sélectionne les cases sur la carte (elles changent de couleur), on
// télécharge ; elles partent l'une après l'autre (le serveur ne mène qu'une
// préparation à la fois), suivies dans le volet. Le partage au téléphone suit.
const CASE_DEG = 5;
const ZOOM_CARRES = 7;      // en deçà, trop de cases à l'écran pour être lisibles
const CARRES_MAX_ECRAN = 400;
// Mesures du 2026-11-05 (fonds.py) : une case de fond, environ 1 Go et 35 min ;
// un lot fabriqué sur ce PC, environ une heure.
const FOND_CARRE_OCTETS = 1e9;
const FOND_CARRE_S = 2100;
// OpenStreetMap se garde en carte vectorielle Mapsforge (mapsforge.py), fabriquée
// sur ce PC depuis l'extrait de la région : bien plus légère que des images.
// Ordres de grandeur, pas encore mesurés jusqu'au bout : l'essai du 2026-11-10
// sur N43E006 (Var) a été arrêté après 17 min, la carte en cours d'écriture.
const CARTE_OSM_OCTETS = 60e6;
const CARTE_OSM_S = 1800;
// Ce qu'une case de la source engage : le poids et la durée.
function coutCarre(source) {
  return source === "osm" ? [CARTE_OSM_OCTETS, CARTE_OSM_S] : [FOND_CARRE_OCTETS, FOND_CARRE_S];
}
const LOT_FABRIQUE_S = 3600;
// Au-dessus des calques (400) et des panneaux du tracé et des franchissements
// (449 à 452), dont les canevas couvrent la carte et prendraient les clics,
// mais sous les points du parcours (600).
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
// Le volet : ouvert ou non, le mode, la source du fond, la sélection, la file.
const horsLigne = { actif: false, mode: "routage", selection: new Set(), file: [], message: "" };

// Relus au démarrage et après chaque préparation : un fond de plus ou de
// moins refait le contrôle des fonds et la grille.
async function chargerFonds() {
  try {
    const avant = JSON.stringify(fondsInstalles.map((f) => f.nom));
    fondsInstalles = (await api("hors_ligne")).fonds || [];
    if (JSON.stringify(fondsInstalles.map((f) => f.nom)) !== avant) { construireFonds(); dessinerCases(); }
  } catch (_) { /* serveur injoignable : pas de fond hors ligne */ }
  afficherZonesCartes();
}

// « Zones stockées localement » de « Gestion des cartes » : une carte (le
// SCAN 25, OpenStreetMap…) est globale, ce que le PC en garde n'en est qu'un
// morceau, une zone de 1°. Toutes les cartes y sont, pas seulement celle
// qu'affiche la grille : une ligne par zone, sa carte et sa taille, et
// « Supprimer » après confirmation, pour cette carte seule.
function afficherZonesCartes() {
  const titres = etat.fondsHorsLigne || {};
  const lignes = [...fondsInstalles].sort((a, b) => a.nom.localeCompare(b.nom)).map((f) => {
    const [carre, source] = [f.nom.split("-", 1)[0], f.nom.slice(f.nom.indexOf("-") + 1)];
    const li = document.createElement("li");
    const texte = boutonZone(`${carre} · ${titres[source] || source} · ${tailleTexte(f.octets)}`,
      () => montrerZoneCarte(f.zone, source));
    li.append(texte);
    // Un ancien fond nommé par sa case de 5° ne se supprime pas d'ici.
    if (/^[NS]\d{2}[EW]\d{3}$/.test(carre)) {
      li.append(boutonSupprimerZone(() => supprimerZoneCarte(carre, source, f.octets)));
    }
    return li;
  });
  if (!lignes.length) {
    const vide = document.createElement("li");
    vide.className = "note";
    vide.textContent = t("zones.aucuneCarte");
    lignes.push(vide);
  }
  $("zonesCartes").replaceChildren(...lignes);
}

// Les pictogrammes des boutons que la page crée : le même trait que ceux d'index.html.
const PICTOS = {
  corbeille: '<path d="M4 7h16M9 7V4h6v3m3 0-1 13H7L6 7M10 11v6m4-6v6"/>',
  charger: '<path d="M12 16V5m-5 5 5-5 5 5M5 20h14"/>',
};
function pictogramme(nom) {
  const boite = document.createElement("span");
  boite.className = "pictogramme";
  boite.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${PICTOS[nom]}</svg>`;
  return boite;
}

// « Supprimer » d'une ligne des zones stockées localement : le bouton rouge à
// icône du volet de la grille.
function boutonSupprimerZone(action) {
  const bouton = document.createElement("button");
  bouton.type = "button";
  bouton.className = "avec-icone zone-supprimer";
  const texte = document.createElement("span");
  texte.textContent = t("donnees.supprimer");
  bouton.append(pictogramme("corbeille"), texte);
  bouton.addEventListener("click", action);
  return bouton;
}

// Le libellé d'une zone de la liste : un clic recentre la carte sur elle.
function boutonZone(texte, action) {
  const bouton = document.createElement("button");
  bouton.type = "button";
  bouton.className = "zone-lien";
  bouton.textContent = texte;
  bouton.title = t("zones.montrer");
  bouton.addEventListener("click", action);
  return bouton;
}

function montrerZone([s, o, n, e]) {
  carte.fitBounds([[s, o], [n, e]]);
}

// Une zone de carte : la carte recentrée sur elle, et sa carte affichée
// (le SCAN 25 d'un carré de SCAN 25). Disponible dans le pays courant, elle
// s'affiche aussitôt ; sinon, construireFonds la prendra quand le pays de
// la zone sera reconnu, après le déplacement.
function montrerZoneCarte(zone, source) {
  if (couchesFonds[source]) {
    if (cleFondActif !== source) {
      fondActif.remove();
      fondActif = couchesFonds[source].addTo(carte);
      carte.fire("baselayerchange", { layer: fondActif });
    }
  } else {
    fondVoulu = source;
  }
  montrerZone(zone);
}

async function supprimerZoneCarte(carre, source, octets) {
  const carte = (etat.fondsHorsLigne || {})[source] || source;
  if (!confirm(t("zones.confirmerCarte", { nom: carre, carte, taille: tailleTexte(octets) }))) return;
  let r;
  try { r = await api("supprimer_fond", { carre, source }); } catch (e) { r = { erreur: e.message }; }
  if (r.erreur) afficherLot({ case: carre, erreur: r.erreur });
  else afficherFile(t("zones.supprimee", { nom: carre, taille: tailleTexte(r.octets || 0) }));
  await chargerFonds();
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

// Les fonds de carte se fabriquent par cases de 1° (fonds.py), nommés comme
// les tuiles SRTM : N43E006 va de 43° à 44° nord et de 6° à 7° est.
function nomCarre(lat, lon) {
  const la = Math.floor(lat), lo = Math.floor(lon);
  return `${la < 0 ? "S" : "N"}${String(Math.abs(la)).padStart(2, "0")}${lo < 0 ? "W" : "E"}${String(Math.abs(lo)).padStart(3, "0")}`;
}

function boiteCarre(nom) {
  const [, ns, la, eo, lo] = nom.match(/^([NS])(\d{2})([EW])(\d{3})$/);
  const s = Number(la) * (ns === "N" ? 1 : -1), o = Number(lo) * (eo === "E" ? 1 : -1);
  return [s, o, s + 1, o + 1];
}

// Les cases que touche une zone [sud, ouest, nord, est].
function carresZone([s, o, n, e]) {
  const noms = [];
  for (let la = Math.floor(s); la < Math.ceil(n); la++) {
    for (let lo = Math.floor(o); lo < Math.ceil(e); lo++) noms.push(nomCarre(la + 0.5, lo + 0.5));
  }
  return noms;
}

// Le fond à garder hors ligne est celui qu'affiche la page, choisi dans la
// liste de « Gestion des cartes » : pas de second choix à tenir d'accord
// avec le premier. null s'il ne se garde pas hors ligne (OSM, satellite…),
// ou pour le SCAN 25 sans clé IGN.
function sourceAGarder() {
  const titres = etat.fondsHorsLigne || {};
  return titres[cleFondActif] && (cleFondActif !== "scan25" || etat.cleIgn) ? cleFondActif : null;
}

function sourceFond() {
  return sourceAGarder();
}

function fondDuCarre(carre, source = sourceFond()) {
  return fondsInstalles.find((f) => f.nom === `${carre}-${source}`);
}

function enFile(nom) {
  return horsLigne.file.some((x) => x.nom === nom) || (lotEnCours.actif && lotEnCours.case === nom);
}

function etatCase(nom) {
  if (enFile(nom)) return "encours";
  if (horsLigne.selection.has(nom)) return "selection";
  if (lotsInstalles.some((l) => l.case === nom)) return "prete";
  return lotsServeur.some((l) => l.case === nom) ? "serveur" : "absente";
}

function etatCarre(carre) {
  if (enFile(carre)) return "encours";
  if (horsLigne.selection.has(carre)) return "selection";
  return fondDuCarre(carre) ? "prete" : "absente";
}

// Sur un fond chargé (SCAN 25, relief), un voile de 5 à 8 % ne se voyait
// pas : traits pleins et épais, fonds francs ; seule la case vide reste
// discrète. Les mêmes couleurs que la légende du volet.
const STYLES_CASE = {
  prete: { color: "#1b7a3e", weight: 3, fillColor: "#23a04f", fillOpacity: 0.3 },
  encours: { color: "#e07b00", weight: 3, dashArray: "8 5", fillColor: "#e07b00", fillOpacity: 0.25 },
  selection: { color: "#1565c0", weight: 3, fillColor: "#1e88e5", fillOpacity: 0.45 },
  serveur: { color: "#1565c0", weight: 2.5, fillColor: "#1e88e5", fillOpacity: 0.04 },
  absente: { color: "#37474f", weight: 1.5, dashArray: "5 5", fillColor: "#37474f", fillOpacity: 0.03 },
};

// 412 Mo, et au-delà d'un milliard d'octets 2,5 Go (le séparateur de la langue).
function tailleTexte(octets) {
  if ((octets || 0) >= 1e9) return `${(octets / 1e9).toLocaleString(langue, { maximumFractionDigits: 1 })} ${t("unite.go")}`;
  return `${Math.round((octets || 0) / 1e6)} ${t("unite.mo")}`;
}

function dureeTexte(secondes) {
  return secondes < 60 ? `${secondes} s` : `${Math.round(secondes / 60)} min`;
}

// Une durée d'estimation : 45 min, 2 h 30, 12 h.
function dureeLongue(secondes) {
  const minutes = Math.round(secondes / 60);
  if (minutes < 60) return `${minutes} min`;
  const h = Math.floor(minutes / 60), m = minutes % 60;
  return m ? `${h} h ${String(m).padStart(2, "0")}` : `${h} h`;
}

function bouton(texteBouton, action) {
  const b = document.createElement("button");
  b.type = "button";
  b.textContent = texteBouton;
  b.addEventListener("click", action);
  return b;
}

// Ce que dit une case au survol : son nom et son état.
function infoCase(nom) {
  const lot = lotsInstalles.find((l) => l.case === nom);
  const serveur = lotsServeur.find((l) => l.case === nom);
  const etatLot = lot ? t("horsLigne.infoInstalle", { taille: tailleTexte(lot.octets) })
    : serveur ? t("horsLigne.infoServeur", { taille: tailleTexte(serveur.octets) }) : t("horsLigne.infoFabriquer");
  return `${nom} · ${etatLot}`;
}

function infoCarre(carre) {
  const titres = etat.fondsHorsLigne || {};
  const ici = fondsInstalles.filter((f) => f.nom.startsWith(`${carre}-`));
  return `${carre} · ${ici.length ? ici.map((f) => `${titres[f.source] || f.source} ${tailleTexte(f.octets)}`).join(", ")
    : t("horsLigne.infoCarre")}`;
}

function tuileGrille(nom, [s, o, n, e], style, info) {
  L.rectangle([[s, o], [n, e]], { pane: "casesHorsLigne", bubblingMouseEvents: false, ...style })
    .bindTooltip(echapper(info), { sticky: true })
    .on("click", () => basculerSelection(nom))
    .addTo(grilleCases);
}

// La grille du mode choisi : les cases de 5° du routage, ou les cases de 1°
// du fond, ceux-ci à partir du zoom ZOOM_CARRES.
function dessinerCases() {
  grilleCases.clearLayers();
  if (horsLigne.actif && horsLigne.mode === "routage") {
    for (const nom of casesVisibles()) tuileGrille(nom, boiteCase(nom), STYLES_CASE[etatCase(nom)], infoCase(nom));
  } else if (horsLigne.actif && carte.getZoom() >= ZOOM_CARRES) {
    const b = carte.getBounds();
    for (const carre of carresZone([b.getSouth(), b.getWest(), b.getNorth(), b.getEast()]).slice(0, CARRES_MAX_ECRAN)) {
      tuileGrille(carre, boiteCarre(carre), STYLES_CASE[etatCarre(carre)], infoCarre(carre));
    }
  }
  afficherSelection();
}

function basculerSelection(nom) {
  if (enFile(nom)) return;
  if (horsLigne.selection.has(nom)) horsLigne.selection.delete(nom); else horsLigne.selection.add(nom);
  dessinerCases();
}

// Ce que la sélection engage, dit avant de cliquer : combien télécharger ou
// fabriquer, le poids et la durée ; et ce qui, déjà là, peut se supprimer.
function bilanSelection() {
  const noms = [...horsLigne.selection].sort();
  if (horsLigne.mode === "routage") {
    const installee = (nom) => lotsInstalles.find((l) => l.case === nom);
    const serveur = (nom) => lotsServeur.find((l) => l.case === nom);
    const aTelecharger = noms.filter((nom) => serveur(nom) && serveur(nom).etat !== "a_jour");
    const aFabriquer = noms.filter((nom) => !serveur(nom) && !installee(nom));
    const installees = noms.filter(installee);
    return { noms, aFaire: [...aTelecharger, ...aFabriquer], installees, aTelecharger, aFabriquer,
      octets: aTelecharger.reduce((somme, nom) => somme + (serveur(nom).octets || 0), 0),
      octetsInstalles: installees.reduce((somme, nom) => somme + (installee(nom).octets || 0), 0) };
  }
  // Seul compte le fond choisi dans la liste : une case qui a un SCAN 25 mais
  // pas de Plan IGN est à télécharger en Plan IGN, pas « déjà là ».
  const aFaire = noms.filter((carre) => !fondDuCarre(carre));
  const installees = noms.filter((carre) => fondDuCarre(carre));
  return { noms, aFaire, installees, octets: aFaire.length * coutCarre(sourceFond())[0],
    octetsInstalles: installees.reduce((somme, carre) => somme + (fondDuCarre(carre).octets || 0), 0) };
}

function afficherSelection() {
  const routage = horsLigne.mode === "routage";
  const aide = !horsLigne.actif ? "" : routage ? t("horsLigne.aideRoutage")
    : carte.getZoom() < ZOOM_CARRES ? t("horsLigne.aideZoom") : t("horsLigne.aideFond");
  $("hlAide").textContent = aide;
  $("offlineHint").textContent = aide;
  $("offlineHint").hidden = !aide;
  // En mode fond, le volet nomme le fond qui sera téléchargé : celui de la
  // liste du haut ; s'il ne se garde pas hors ligne, il dit lesquels choisir.
  const titres = etat.fondsHorsLigne || {};
  const source = sourceFond();
  $("hlFondChoisi").hidden = routage || Boolean(source);
  $("hlFondChoisi").textContent = routage || source ? "" : t("horsLigne.fondAucun", { liste: Object.entries(titres)
      .filter(([cle]) => couchesFonds[cle] && (cle !== "scan25" || etat.cleIgn)).map(([, titre]) => titre).join(", ") });
  $("hlLegendeServeur").hidden = !routage;
  const b = bilanSelection();
  const parties = [];
  if (routage) {
    if (b.aTelecharger.length) parties.push(t("horsLigne.selTelecharger", { n: b.aTelecharger.length, taille: tailleTexte(b.octets) }));
    if (b.aFabriquer.length) parties.push(t("horsLigne.selFabriquer", { n: b.aFabriquer.length, duree: dureeLongue(b.aFabriquer.length * LOT_FABRIQUE_S) }));
  } else if (b.aFaire.length) {
    parties.push(t("horsLigne.selFonds", { n: b.aFaire.length, taille: tailleTexte(b.octets), duree: dureeLongue(b.aFaire.length * coutCarre(sourceFond())[1]) }));
  }
  if (b.installees.length) parties.push(t("horsLigne.selInstallees", { n: b.installees.length, taille: tailleTexte(b.octetsInstalles) }));
  $("hlSelection").textContent = b.noms.length ? parties.join(" ") || t("horsLigne.selRien") : t("horsLigne.selVide");
  $("hlTelecharger").disabled = !b.aFaire.length || (!routage && !sourceFond());
  // La bulle de « Télécharger » dit ce qu'il fait ici : un fond, ou des zones.
  $("hlTelechargerInfo").textContent = t(routage ? "horsLigne.infoTelechargerRoutage" : "horsLigne.infoTelechargerFond");
  // Ce qui est sur ce PC dans la sélection se partage au téléphone, seul.
  $("hlPartager").hidden = !b.installees.length;
  $("hlExporter").hidden = !b.installees.length;
}

// Télécharger : la sélection rejoint la file, qui part tout de suite si rien ne se prépare.
function telechargerSelection() {
  const b = bilanSelection();
  const source = sourceFond();
  for (const nom of b.aFaire) {
    horsLigne.file.push(horsLigne.mode === "routage"
      ? { genre: "lot", nom, action: b.aTelecharger.includes(nom) ? "telecharger" : "fabriquer" }
      : { genre: "fond", nom, source });
  }
  horsLigne.selection.clear();
  if (!lotEnCours.actif) lancerSuivant();
  else { dessinerCases(); afficherFile(); }
}

async function lancerSuivant() {
  const tache = horsLigne.file.shift();
  dessinerCases();
  if (!tache) { afficherFile(); return; }
  const [route, corps] = tache.genre === "fond" ? ["preparer_fond", { carres: [tache.nom], source: tache.source }]
    : tache.action === "telecharger" ? ["telecharger_lot", { case: tache.nom }] : ["preparer_lot", { case: tache.nom }];
  let reponse;
  try {
    reponse = await api(route, corps);
  } catch (e) {
    reponse = { erreur: e.message };
  }
  if (reponse.erreur) {
    afficherLot({ case: tache.nom, erreur: reponse.erreur });
    lancerSuivant();        // une tuile en échec n'arrête pas les suivantes
    return;
  }
  if (minuterieLot) clearTimeout(minuterieLot);
  suivreLot();
}

// La file dans le volet : le dernier message de tâche (afficherLot) et ce qui attend.
function afficherFile(message) {
  if (message !== undefined) horsLigne.message = message;
  const attente = horsLigne.file.length ? t("horsLigne.enAttente", { n: horsLigne.file.length }) : "";
  $("hlEnCours").textContent = [horsLigne.message, attente].filter(Boolean).join(" ");
  $("hlFile").hidden = !$("hlEnCours").textContent;
  $("hlArreter").hidden = !(lotEnCours.actif || horsLigne.file.length);
}

function changerMode(mode) {
  horsLigne.mode = mode;
  horsLigne.selection.clear();
  dessinerCases();
}

// Le volet ouvert, la grille paraît, sans toucher au zoom : ouvrir la page pour
// cocher une option ne fait pas perdre la vue ; quitté, la carte revient au tracé.
function activerHorsLigne(actif) {
  if (horsLigne.actif === actif) return;
  horsLigne.actif = actif;
  if (actif) {
    grilleCases.addTo(carte);
    chargerLots();
  } else {
    grilleCases.remove();
    dessinerCases();
  }
}

async function chargerLots() {
  // Rien à lire tant que ni la grille ni la page « Gestion des itinéraires »
  // (sa liste des zones stockées localement) ne sont affichées.
  if (horsLigne.actif || !$("pane-itineraires").hidden) {
    try {
      lotsInstalles = (await api("hors_ligne")).lots || [];
    } catch (_) { /* serveur injoignable : la grille reste vide */ }
    // Le catalogue du dépôt vient de GitHub, parfois en quelques secondes : la
    // grille n'attend pas, elle se redessine à son arrivée.
    api("catalogue_lots").then((r) => { lotsServeur = r.lots || []; dessinerCases(); afficherZonesLocales(); })
      .catch(() => { lotsServeur = []; });
  }
  dessinerCases();
  afficherZonesLocales();
}

// « Zones stockées localement », comme la page du téléphone : une ligne par
// lot installé, sa source et sa taille, « Mettre à jour » quand le serveur en
// publie un plus récent, et « Supprimer » après confirmation.
function afficherZonesLocales() {
  const liste = $("zonesLocales");
  const lignes = [...lotsInstalles].sort((a, b) => a.case.localeCompare(b.case)).map((l) => {
    const li = document.createElement("li");
    // Les sources du manifeste : OSM et le relief sont dans tous les lots ; les
    // chemins nationaux, nommés par leur calque (bdtopo) ou leur source (ign),
    // prennent le nom court du pays, comme sur le téléphone (« enrichi IGN »).
    const sources = Object.keys(l.sources || {}).filter((cle) => !["osm", "relief"].includes(cle))
      .map((cle) => Object.values(FOURNISSEURS_CARTES)
        .find((p) => p.paths?.source === cle || p.paths?.overlay === cle)?.paths.label || cle);
    const origine = l.type === "osm" || !sources.length ? "OSM" : t("zones.enrichi", { sources: sources.join(" + ") });
    const texte = boutonZone(`${l.case} · ${origine} · ${tailleTexte(l.octets)}`, () => montrerZone(boiteCase(l.case)));
    li.append(texte);
    if (lotsServeur.find((s) => s.case === l.case)?.etat === "ancien") {
      const maj = document.createElement("button");
      maj.type = "button";
      maj.textContent = t("horsLigne.mettreAJour");
      maj.addEventListener("click", () => {
        horsLigne.file.push({ genre: "lot", nom: l.case, action: "telecharger" });
        if (!lotEnCours.actif) lancerSuivant(); else afficherFile();
      });
      li.append(maj);
    }
    li.append(boutonSupprimerZone(() => supprimerZone(l)));
    return li;
  });
  if (!lignes.length) {
    const vide = document.createElement("li");
    vide.className = "note";
    vide.textContent = t("zones.aucune");
    lignes.push(vide);
  }
  liste.replaceChildren(...lignes);
}

async function supprimerZone(l) {
  if (!confirm(t("zones.confirmer", { nom: l.case, taille: tailleTexte(l.octets) }))) return;
  let r;
  try { r = await api("supprimer_case", { case: l.case, fonds: false }); } catch (e) { r = { erreur: e.message }; }
  zonesDemandees.delete(l.case);      // supprimée : un calcul pourra la redemander
  if (r.erreur) afficherLot({ case: l.case, erreur: r.erreur });
  else afficherFile(t("zones.supprimee", { nom: l.case, taille: tailleTexte(r.octets || 0) }));
  await chargerLots();
}

// La langue a changé : les textes du volet suivent.
function afficherEntreeHorsLigne() {
  afficherSelection();
  afficherZonesLocales();
  afficherZonesCartes();
}

$("hlRoutage").addEventListener("change", () => changerMode("routage"));
$("hlFond").addEventListener("change", () => changerMode("fond"));
$("hlTelecharger").addEventListener("click", telechargerSelection);
$("hlArreter").addEventListener("click", () => { horsLigne.file = []; arreterLot(); });
carte.on("moveend", dessinerCases);
// La grille suit le volet « Hors ligne », que presentation.js ouvre depuis
// « Gestion des cartes » (fonds) ou « Gestion des itinéraires » (routage).
if (typeof MutationObserver !== "undefined") {
  new MutationObserver(() => activerHorsLigne(!$("horsLigne").hidden))
    .observe($("horsLigne"), { attributes: true, attributeFilter: ["hidden"] });
}

// ------------------------------------------------------------ partage au téléphone
// Le PC sert ses lots et ses fonds sur le Wi-Fi (partage.py), fermé par
// défaut. Le QR code porte l'adresse du catalogue et un jeton tiré à chaque
// ouverture ; il est dessiné par le serveur (SVG).
// Le QR code s'affiche dans sa fenêtre, comme lidar2map, à l'ouverture du
// partage ; « Afficher le QR code », dans le volet de la grille, la rouvre.
// Le partage s'ouvre depuis « Gestion des cartes » ou « Gestion des itinéraires » :
// le volet de la grille garde son état et de quoi l'arrêter. Une page rechargée
// ne rouvre pas la fenêtre.
function afficherPartage(r, montrer = false) {
  etat.partage = r;
  $("partageQr").innerHTML = r.ouvert ? r.qr : "";
  // Le pare-feu de Windows (pare_feu.py) : sans sa règle, le téléphone ne joindra pas le PC.
  const pareFeu = ["refuse", "erreur"].includes(r.pare_feu) ? ` ${t("partage.pareFeu")}` : "";
  const erreur = r.erreur ? t("partage.erreur", { erreur: ts(r.erreur) }) : "";
  $("partageFenetreTexte").textContent = erreur || (r.ouvert ? texteDuPartage(r) + pareFeu : "");
  const contenu = r.ouvert ? contenuDuPartage(r) : "";
  $("hlPartage").hidden = !r.ouvert;
  $("hlPartageTexte").textContent = !r.ouvert ? ""
    : contenu ? t("partage.etat", { quoi: contenu, taille: tailleTexte(r.octets) }) : t("partage.rien");
  $("arreterPartageFenetre").hidden = !r.ouvert;
  $("partageFenetre").hidden = !((r.ouvert || erreur) && montrer);
}

// Ce qui est partagé, et seulement cela : « 2 zones de carte », « 1 zone de
// routage », ou les deux.
function contenuDuPartage(r) {
  const compte = (n, cle) => n === 1 ? t(`${cle}1`) : t(cle, { n });
  return [
    ...(r.fonds.length ? [compte(r.fonds.length, "partage.zonesCarte")] : []),
    ...(r.lots.length ? [compte(r.lots.length, "partage.zonesRoutage")] : []),
  ].join(t("partage.et"));
}

// Le téléphone scanne depuis « Gestion des cartes », ou « Gestion des
// itinéraires » quand seul du routage est partagé.
function texteDuPartage(r) {
  const contenu = contenuDuPartage(r);
  if (!contenu) return t("partage.rien");
  return t("partage.ouvert", { quoi: contenu, taille: tailleTexte(r.octets),
    page: t(r.fonds.length ? "menu.cartes" : "menu.itineraires") });
}

// selection : {lots, carres, source}, ce que le volet de la grille a choisi.
async function basculerPartage(ouvrir, selection = null) {
  try {
    afficherPartage(await api("partage", { ouvrir, ...(selection || {}) }), ouvrir);
  } catch (e) {
    afficherPartage({ ouvert: false, erreur: e.message });
  }
}
// Ce que la sélection a sur ce PC, tel que le prennent le partage et l'archive.
function selectionGrille() {
  const b = bilanSelection();
  return horsLigne.mode === "routage" ? { lots: b.installees, carres: [] }
    : { lots: [], carres: b.installees, source: sourceFond() };
}
$("hlPartager").addEventListener("click", () => basculerPartage(true, selectionGrille()));
// Exporter : le navigateur enregistre l'archive, que le serveur écrit au fil de l'envoi.
function adresseArchive(s) {
  const parametres = { lots: s.lots.join(","), carres: s.carres.join(",") };
  if (s.source) parametres.source = s.source;
  return `/archive.zip?${new URLSearchParams(parametres)}`;
}
// Le nom que le serveur donne à l'archive (web.envoyer_archive) : hike2gpx-N43E006-scan25-et-2.zip.
function nomArchive(s) {
  const noms = [...s.lots, ...s.carres.map((c) => (s.source ? `${c}-${s.source}` : c))];
  return `hike2gpx-${noms[0]}${noms.length > 1 ? `-et-${noms.length - 1}` : ""}.zip`;
}
// Où l'enregistrer : la fenêtre « Enregistrer sous » du système (showSaveFilePicker,
// Chrome et Edge), pour ne pas remplir Téléchargements de plusieurs Go ; la page
// y écrit l'archive au fil de sa réception. Sans elle (Firefox), le téléchargement
// habituel, qui suit le réglage « Toujours demander où enregistrer » du navigateur.
$("hlExporter").addEventListener("click", async () => {
  const selection = selectionGrille();
  const adresse = adresseArchive(selection);
  if (!globalThis.showSaveFilePicker) {
    const lien = document.createElement("a");
    lien.href = adresse;
    lien.download = "";
    lien.click();
    return;
  }
  let fichier;
  try {
    fichier = await globalThis.showSaveFilePicker({ suggestedName: nomArchive(selection),
      types: [{ description: "Archive zip", accept: { "application/zip": [".zip"] } }] });
  } catch (e) {
    return;                         // « Annuler » dans la fenêtre
  }
  const nom = fichier.name;
  try {
    const sortie = await fichier.createWritable();
    const reponse = await fetch(adresse);
    if (!reponse.ok) throw new Error(`HTTP ${reponse.status}`);
    const total = Number(reponse.headers.get("Content-Length")) || 0;
    let fait = 0;
    const suivi = new TransformStream({
      transform(morceau, controleur) {
        fait += morceau.byteLength;
        afficherFile(t("horsLigne.exportEnCours", { nom, fait: tailleTexte(fait),
          total: total ? ` / ${tailleTexte(total)}` : "" }));
        controleur.enqueue(morceau);
      },
    });
    afficherFile(t("horsLigne.exportEnCours", { nom, fait: tailleTexte(0), total: total ? ` / ${tailleTexte(total)}` : "" }));
    await reponse.body.pipeThrough(suivi).pipeTo(sortie);
    afficherFile(t("horsLigne.exportFini", { nom, taille: tailleTexte(fait) }));
  } catch (e) {
    afficherFile(t("horsLigne.exportErreur", { nom, erreur: e.message }));
  }
});
// Importer : le zip part tel quel au serveur, qui vérifie chaque fichier avant de l'installer.
$("hlImporter").addEventListener("click", () => $("fichierArchive").click());
$("fichierArchive").addEventListener("change", async (e) => {
  const fichier = e.target.files?.[0];
  e.target.value = "";
  if (!fichier) return;
  afficherFile(t("horsLigne.importEnCours", { nom: fichier.name, taille: tailleTexte(fichier.size) }));
  let r;
  try {
    const reponse = await fetch("/api/importer_archive",
      { method: "POST", headers: { "Content-Type": "application/zip" }, body: fichier });
    r = await reponse.json().catch(() => ({}));
    if (!reponse.ok) r = { erreur: r.error || `HTTP ${reponse.status}` };
  } catch (err) {
    r = { erreur: err.message };
  }
  afficherFile(r.erreur ? t("horsLigne.importErreur", { nom: fichier.name, erreur: r.erreur })
    : t("horsLigne.importFini", { nom: fichier.name, n: r.importe.fonds.length, z: r.importe.lots.length }));
  await chargerLots();
  chargerFonds();
});
$("hlPartageArreter").addEventListener("click", () => basculerPartage(false));
$("hlPartageQr").addEventListener("click", () => { if (etat.partage?.ouvert) $("partageFenetre").hidden = false; });
$("fermerFenetrePartage").addEventListener("click", () => { $("partageFenetre").hidden = true; });
$("arreterPartageFenetre").addEventListener("click", () => basculerPartage(false));
$("partageFenetre").addEventListener("click", (e) => { if (e.target === $("partageFenetre")) $("partageFenetre").hidden = true; });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("partageFenetre").hidden = true; });

function afficherLot(r) {
  const nom = r.case || "";
  let message = "";
  if (r.actif) {
    // Un téléchargement compte en octets, une fabrication en tuiles ou mailles.
    const compte = !r.total ? "" : r.etape === "telechargement" || r.etape === "deplacement"
      ? ` ${tailleTexte(r.faites)} / ${tailleTexte(r.total)}` : ` ${r.faites}/${r.total}`;
    const duree = dureeTexte(r.duree_s || 0);
    message = r.etape === "deplacement" ? t("horsLigne.deplacement", { compte, duree })
      : r.auto && r.etape === "telechargement" ? t("horsLigne.automatique", { nom, compte, duree })
      : t("horsLigne.avancement", { nom, etape: t(`horsLigne.etape.${r.etape}`), compte, duree });
  } else if (r.erreur) {
    message = t("horsLigne.erreur", { nom, erreur: ts(r.erreur) });
  } else if (r.etape === "fini" && r.deplace) {
    message = t("horsLigne.deplace", { dossier: r.deplace });
    etat.dossierDonnees = $("dossierDonnees").value = r.deplace;
  } else if (r.etape === "fini") {
    message = r.fond ? t("horsLigne.fondFini", { nom: r.fond }) : t("horsLigne.fini", { nom });
  }
  $("lotHorsLigneTexte").textContent = message;
  // Le titre de la ligne d'activité sur la carte : la carte en cours ou la zone de routage.
  $("lotHorsLigne").dataset.titre = r.etape === "deplacement" || r.deplace ? t("horsLigne.titreDeplacement") : r.source
    ? t("horsLigne.titreCarte", { fond: (etat.fondsHorsLigne || {})[r.source] || r.source })
    : t("horsLigne.titreZone");
  $("lotHorsLigne").hidden = !message;
  afficherFile(message);    // le même message dans le volet « Hors ligne », avec la file
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
    if (horsLigne.file.length) lancerSuivant();     // la tuile suivante du volet « Hors ligne »
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
  chargerLots();         // lots installés, et fabrication en cours si la page a été rechargée
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
  etat.points.push(point);
  armerPoint(point);
  rafraichirPoints();
  if (recalculer) planifierCalcul();
}

// Un point se déplace et se retire seulement en planification : le tracé reste
// affiché quand on la quitte, mais ne se modifie plus (ni glissement, ni bulle
// « Retirer ce point »).
function armerPoint(point) {
  if (planification) {
    point.marqueur.dragging.enable();
    point.marqueur.bindPopup(() => bullePoint(point));
  } else {
    point.marqueur.closePopup();
    point.marqueur.unbindPopup();
    point.marqueur.dragging.disable();
  }
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

function bulleJonction(j) {
  const div = document.createElement("div");
  div.className = "bulle";
  const lien = document.createElement("a");
  // L'éditeur d'OpenStreetMap, ouvert sur la voie à raccorder.
  lien.href = `https://www.openstreetmap.org/edit?${j.osm.replace("/", "=")}#map=19/${j.lat}/${j.lon}`;
  lien.target = "_blank";
  lien.rel = "noopener";
  lien.textContent = t("jonction.corriger");
  // Un chemin relié à rien est inaccessible au calcul ; un chemin relié qui
  // s'arrête presque contre un autre coupe seulement ce passage-là.
  div.append(paragraphe(t("jonction.titre"), true),
             paragraphe(t(j.isole ? "jonction.isole" : "jonction.detail", { distance: decimal(j.distance_m, 1) })),
             lien);
  return div;
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
  L.polyline(lignes(r.itineraire), { color: "#1565c0", weight: 5, opacity: 0.85, interactive: false, pane: "trace", leg: "itineraire" })
    .addTo(couches);
  flechesTrace = preparerFleches(r.itineraire.geometry.coordinates);
  afficherFleches();
  for (const p of r.portions_ign || []) {
    L.polyline(p.coords, { color: COULEURS.uncertain, weight: 5, opacity: 0.95, dashArray: "8 6", interactive: false, pane: "trace" })
      .addTo(couches);
  }
  for (const f of r.franchissements) {
    L.circleMarker([f.lat, f.lon], { radius: 6, weight: 2, color: "#fff", fillOpacity: 1, fillColor: COULEURS[f.statut], pane: "trace", leg: LEGENDE_STATUT[f.statut] })
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

// KML (Google Earth, Géoportail, gpx2dash…) : une trace par Placemark, avec la
// couleur et l'épaisseur de son style, et ses données (ExtendedData, en JSON
// quand elles viennent de gpx2elev).
function couleurKml(texte) {
  // KML écrit aabbggrr : alpha, puis bleu, vert, rouge.
  const m = /^([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec((texte || "").trim());
  return m ? { couleur: `#${m[4]}${m[3]}${m[2]}`, opacite: parseInt(m[1], 16) / 255 } : {};
}

function enfant(element, nom) {
  return Array.from(element.children).find((e) => e.localName === nom);
}

function lireTracesKml(source) {
  const xml = new DOMParser().parseFromString(source, "application/xml");
  if (xml.documentElement?.localName !== "kml" || xml.getElementsByTagName("parsererror").length) {
    throw new Error(t("gpx.invalide"));
  }
  const styles = new Map();
  for (const style of xml.getElementsByTagNameNS("*", "Style")) {
    const ligne = style.getElementsByTagNameNS("*", "LineStyle")[0];
    if (!style.getAttribute("id") || !ligne) continue;
    const valeur = (nom) => ligne.getElementsByTagNameNS("*", nom)[0]?.textContent;
    styles.set(style.getAttribute("id"), { ...couleurKml(valeur("color")), epaisseur: Number(valeur("width")) || null });
  }
  const traces = [];
  for (const repere of xml.getElementsByTagNameNS("*", "Placemark")) {
    const segments = [];
    for (const ligne of repere.getElementsByTagNameNS("*", "LineString")) {
      const points = [];
      const brut = ligne.getElementsByTagNameNS("*", "coordinates")[0]?.textContent || "";
      for (const triplet of brut.trim().split(/\s+/)) {
        const [lon, lat] = triplet.split(",").map(Number);
        if (Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180) points.push([lat, lon]);
      }
      if (points.length > 1) segments.push(points);
    }
    if (!segments.length) continue;
    const infos = {};
    for (const donnee of repere.getElementsByTagNameNS("*", "Data")) {
      const valeur = donnee.getElementsByTagNameNS("*", "value")[0]?.textContent ?? "";
      try { infos[donnee.getAttribute("name")] = JSON.parse(valeur); } catch { infos[donnee.getAttribute("name")] = valeur; }
    }
    const lien = (enfant(repere, "styleUrl")?.textContent || "").trim().replace(/^#/, "");
    traces.push({ nom: (enfant(repere, "name")?.textContent || "").trim(), segments, style: styles.get(lien) || {}, infos });
  }
  if (!traces.length) throw new Error(t("gpx.invalide"));
  return traces;
}

// gpx2dash nomme ses traces « 2020-12-13_LA ROQUEBRUSSANNE_8.7KM_D+350M_2H18 » :
// la date, le lieu, la distance, le D+ et la durée ; les plus récentes ajoutent
// l'heure de départ devant le lieu (« 2026-04-27_12-14 La Roquebrussanne_… »).
// Un autre nom reste tel quel.
function lireNomTrace(nom) {
  const m = /^(\d{4})-(\d{2})-(\d{2})_(?:(\d{1,2})-(\d{2})\s+)?(.+?)(?:_([\d.]+)km)?(?:_D\+(\d+)m)?(?:_(\d+)h(\d+))?$/i.exec(nom);
  if (!m) return { titre: nom };
  return { titre: m[6].replace(/_/g, " "), date: new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])),
    heure: m[4] ? `${Number(m[4])} h ${m[5]}` : null,
    km: m[7] ? Number(m[7]) : null, dplus: m[8] ? Number(m[8]) : null, minutes: m[9] ? Number(m[9]) * 60 + Number(m[10]) : null };
}

function longueurTrace(segments) {
  let metres = 0;
  for (const points of segments) {
    for (let i = 1; i < points.length; i++) metres += L.latLng(points[i - 1]).distanceTo(L.latLng(points[i]));
  }
  return metres;
}

// La bulle d'une trace importée : son nom, sa date, sa distance, son dénivelé, sa durée.
function bulleTraceImportee(trace) {
  const div = document.createElement("div");
  div.className = "bulle";
  const lu = lireNomTrace(trace.nom);
  const lignes = [];
  if (lu.date) {
    const jour = lu.date.toLocaleDateString(langue === "en" ? "en-GB" : "fr-FR",
      { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
    lignes.push(t("trace.date", { date: lu.heure ? `${jour}, ${lu.heure}` : jour }));
  }
  // La distance du nom vient du GPX complet ; la géométrie d'un KML est souvent simplifiée.
  lignes.push(t("trace.distance", { km: km(lu.km != null ? lu.km * 1000 : longueurTrace(trace.segments)) }));
  const d = trace.infos.denivele_exact;
  if (d && Number.isFinite(d.Dplus_m) && Number.isFinite(d.Dmoins_m)) {
    const modele = typeof trace.infos.modele === "string" ? trace.infos.modele : "gpx2elev";
    lignes.push(t("trace.denivele", { plus: Math.round(d.Dplus_m), moins: Math.round(d.Dmoins_m), modele }));
  } else if (lu.dplus != null) {
    lignes.push(t("trace.deniveleNom", { plus: lu.dplus }));
  }
  if (lu.minutes != null) lignes.push(t("trace.duree", { duree: dureeLongue(lu.minutes * 60) }));
  div.append(paragraphe(lu.titre || trace.nom, true), ...lignes.map((l) => paragraphe(l)));
  // Le retrait là où l'on regarde la trace, pas seulement dans le menu.
  const retirer = document.createElement("button");
  retirer.type = "button";
  retirer.className = "page-action";
  retirer.textContent = t("bouton.supprimerGpx");
  retirer.addEventListener("click", () => { carte.closePopup(); supprimerGpx(); });
  div.append(retirer);
  return div;
}

async function chargerGpx(fichier) {
  const sequence = ++sequenceImportGpx;
  $("erreurGpx").hidden = true;
  try {
    if (fichier.size > 20_000_000) throw new Error(t("gpx.tropGrand"));
    const texte = await fichier.text();
    const kml = /\.kml$/i.test(fichier.name) || /<kml[\s>]/.test(texte.slice(0, 1000));
    const traces = kml ? lireTracesKml(texte) : [{ segments: lireTracesGpx(texte) }];
    if (sequence !== sequenceImportGpx) return;
    traceGpxImporte.clearLayers();
    let minLat = 90, minLon = 180, maxLat = -90, maxLon = -180;
    for (const trace of traces) {
      for (const points of trace.segments) {
        if (kml) {
          // Le rendu du fichier, comme Géoportail : sa couleur et son épaisseur ; un clic ouvre la bulle de la trace.
          L.polyline(points, { pane: "gpxImporte", renderer: renduImport, color: trace.style.couleur || "#ffe14a",
            opacity: trace.style.opacite ?? 1, weight: trace.style.epaisseur || 4, bubblingMouseEvents: false })
            .bindPopup(() => bulleTraceImportee(trace)).addTo(traceGpxImporte);
        } else {
          L.polyline(points, { pane: "gpxImporte", color: "#344132", weight: 7, opacity: 0.9,
            dashArray: "9 6", interactive: false }).addTo(traceGpxImporte);
          L.polyline(points, { pane: "gpxImporte", color: "#ffe14a", weight: 4, opacity: 1,
            dashArray: "9 6", interactive: false, leg: "gpx" }).addTo(traceGpxImporte);
        }
        for (const [lat, lon] of points) {
          minLat = Math.min(minLat, lat); minLon = Math.min(minLon, lon);
          maxLat = Math.max(maxLat, lat); maxLon = Math.max(maxLon, lon);
        }
      }
    }
    nomGpxImporte = fichier.name.replace(/\.(gpx|kml)$/i, "") || fichier.name;
    traceGpxImporte.addTo(carte);
    if (controleFonds) controleFonds.addOverlay(traceGpxImporte, echapper(nomGpxImporte));
    else construireFonds();
    $("chargerGpxTexte").dataset.i18n = "bouton.supprimerGpx";
    $("chargerGpxTexte").textContent = t("bouton.supprimerGpx");
    $("chargerGpxIcone").replaceChildren(pictogramme("corbeille").firstChild);
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
  $("chargerGpxTexte").dataset.i18n = "bouton.chargerGpx";
  $("chargerGpxTexte").textContent = t("bouton.chargerGpx");
  $("chargerGpxIcone").replaceChildren(pictogramme("charger").firstChild);
  $("erreurGpx").hidden = true;
}

// ------------------------------------------------------------ démarrage

// Comme sur le téléphone, un clic sur la carte ne pose un point qu'en
// planification : la page « Planifier un itinéraire » ouverte, que
// presentation.js annonce par planifier(). Ailleurs, la carte se consulte
// sans rien y poser ; les points déjà posés et le tracé restent.
let planification = false;
function planifier(actif) {
  planification = actif;
  document.body.classList.toggle("planification", actif);
  etat.points.forEach(armerPoint);
}
carte.on("click", (e) => {
  // Comme sur le téléphone, un clic sur la carte referme la recherche : presentation.js l'écoute.
  if (typeof CustomEvent !== "undefined") document.dispatchEvent(new CustomEvent("hike2gpx:carte-cliquee"));
  if (planification) ajouterPoint(e.latlng);
});
{
  const champ = $("zoomCalques");
  champ.value = String(zoomCalques);
  // Chaque saisie valide s'applique ; un nombre hors bornes revient dans les bornes à la sortie du champ.
  champ.addEventListener("input", () => { if (champ.value !== "") reglerZoomCalques(champ.value); });
  champ.addEventListener("change", () => { champ.value = String(zoomCalques); });
}
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
// Les champs reviennent aux valeurs enregistrées (un refus, une valeur impossible).
function restaurerChampsReglages() {
  $("cleIgn").value = etat.cleIgn;
  $("renouvellementJours").value = etat.renouvellementJours;
  $("zonesAuto").checked = etat.zonesAuto;
}

// Les réglages s'enregistrent à la fermeture de leur page (presentation.js),
// quand l'un d'eux a changé : plus de bouton « Enregistrer ». Un délai hors de
// 1 à 365 jours est abandonné, comme un refus du serveur, sans rien enregistrer.
async function enregistrerReglages() {
  const cle = $("cleIgn").value;
  const saisie = Math.round(Number($("renouvellementJours").value));
  const jours = saisie >= 1 && saisie <= 365 ? saisie : etat.renouvellementJours;
  const zonesAuto = $("zonesAuto").checked;
  if (cle === etat.cleIgn && jours === etat.renouvellementJours && zonesAuto === etat.zonesAuto) {
    restaurerChampsReglages(); return;
  }
  const cleChangee = cle !== etat.cleIgn;
  try {
    const r = await api("reglages", { cle_ign: cle, renouvellement_jours: jours, zones_auto: zonesAuto });
    if (r.erreur) { afficherStatut(() => ts(r.erreur), true); restaurerChampsReglages(); return; }
    etat.cleIgn = r.cle_ign;
    etat.renouvellementJours = r.renouvellement_jours;
    etat.zonesAuto = r.zones_auto !== false;
    restaurerChampsReglages();
    afficherExtrait(etat.extrait);
    construireFonds();
    if (cleChangee) afficherStatut(() => t(etat.cleIgn ? "cle.enregistree" : "cle.retiree"));
    verifierBrouter();
  } catch (e) {
    afficherStatut(() => t("statut.erreur", { message: e.message }), true);
    restaurerChampsReglages();
  }
}
document.addEventListener("hike2gpx:reglages-fermes", enregistrerReglages);
// Le dossier des cartes et des zones hors ligne : le serveur les déplace en tâche
// de fond, et la ligne d'activité suit le déplacement comme une préparation.
$("deplacerDonnees").addEventListener("click", async () => {
  const dossier = $("dossierDonnees").value.trim();
  if (!dossier || dossier === etat.dossierDonnees) return;
  if (!confirm(t("reglages.confirmerDeplacement", { dossier }))) return;
  try {
    const r = await api("deplacer_donnees", { dossier });
    if (r.erreur) { afficherStatut(() => ts(r.erreur), true); return; }
    suivreLot();
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
  bouton.className = "avec-icone";
  const libelle = document.createElement("span");
  libelle.textContent = t("donnees.viderTout");
  bouton.append(pictogramme("corbeille"), libelle);
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
    etat.fondsHorsLigne = infos.fonds_hors_ligne || {};
    etat.cleIgn = reglages.cle_ign || "";
    $("cleIgn").value = etat.cleIgn;
    etat.renouvellementJours = reglages.renouvellement_jours ?? 30;
    $("renouvellementJours").value = etat.renouvellementJours;
    etat.zonesAuto = reglages.zones_auto !== false;
    $("zonesAuto").checked = etat.zonesAuto;
    etat.dossierDonnees = $("dossierDonnees").value = reglages.dossier_donnees || "";
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
