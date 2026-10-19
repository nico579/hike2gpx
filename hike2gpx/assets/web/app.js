"use strict";

// Page de tracé de hike2gpx : points posés sur la carte, itinéraire calculé
// par le serveur local (BRouter et les coupes des franchissements), export
// GPX. Les textes venus d'OpenStreetMap passent toujours par textContent.

const DELAI_CALCUL_MS = 250;
const CLE_VUE = "hike2gpx.vue";
const COULEURS = { blocked: "#d32f2f", uncertain: "#ef6c00" };

const etat = { points: [], sequence: 0, minuterie: null, dernier: null, cleIgn: "", version: "", sequenceDenivele: 0,
  suivi: null, statut: ["", false] };
const $ = (id) => document.getElementById(id);

// ------------------------------------------------------------ langue

// Textes de la page en français et en anglais, comme dans les autres
// applications : le choix FR / EN est celui du commun (/nico579-langue.js),
// qui l'enregistre et l'annonce par l'événement « nico579-langue » ; la page
// applique alors ce dictionnaire. Les éléments fixes portent data-i18n.
const TEXTES = {
  fr: {
    "aide": "Cliquez sur la carte pour poser le départ, puis les étapes et l'arrivée. Faites glisser un point pour le déplacer ; « Revenir au départ » ferme une boucle.",
    "bouton.retirerDernier": "Retirer le dernier point",
    "bouton.toutEffacer": "Tout effacer",
    "bouton.boucler": "Revenir au départ",
    "bouton.exporter": "Exporter le GPX",
    "option.strict": "Mode strict : éviter aussi les passages à vérifier",
    "option.ign": "Emprunter aussi les chemins IGN absents d'OSM (à vérifier sur place)",
    "option.comparer": "Montrer le tracé qui ignore les barrières",
    "resultat.distance": "Distance",
    "resultat.denivele": "Dénivelé",
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
    "legende.note": "Les calques de chemins se cochent sur la carte, en haut à droite, et s'affichent à partir du zoom 14.",
    "reglages.titre": "Réglages",
    "reglages.cle": "Clé IGN pour le SCAN 25",
    "reglages.enregistrer": "Enregistrer",
    "reglages.note": "Le SCAN 25 n'est pas une donnée libre. Sans clé, la carte utilise le Plan IGN, sous Licence Ouverte.",
    "journal.titre": "Journal des calculs",
    "journal.note": "Erreurs, blocages et lenteurs, du plus ancien au plus récent :",
    "journal.vide": "Journal vide pour l'instant.",
    "journal.illisible": "Journal illisible : {message}",
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
    "moteur.installer": "Installer le moteur BRouter (7 Mo)",
    "moteur.installation": "Installation de BRouter…",
    "moteur.installe": "BRouter installé.",
    "moteur.absent": "Le moteur BRouter n'est pas encore installé.",
    "segment.telecharger": "Télécharger les données BRouter {nom} (70 à 250 Mo)",
    "segment.telechargement": "Téléchargement de {nom}…",
    "serveur.injoignable": "Serveur injoignable : {message}",
    "denivele.estimation": "Estimation de BRouter ; calcul de gpx2elev en cours…",
    "denivele.indisponible": "Estimation de BRouter ; gpx2elev indisponible : {erreur}",
    "denivele.source": "gpx2elev, {modele} : échantillonnage 5 m, lissage 20 m, hystérésis 2 m ; altitude de {min} à {max} m.",
    "calque.osm": "Chemins OSM",
    "calque.bdtopo": "Chemins BD TOPO (IGN)",
    "calque.chargement": "Chargement des {nom}… (la première fois, jusqu'à une minute)",
    "calque.zoom": "Zoomez davantage (niveau {niveau}) pour voir les chemins.",
    "bdtopo.troncon": "Tronçon",
    "bdtopo.acces": "accès piéton : {valeur}",
    "bdtopo.prive": "privé",
    "fond.scan25": "SCAN 25 (IGN)",
    "fond.plan": "Plan IGN",
    "fond.photos": "Photos aériennes (IGN)",
    "fond.osm": "OpenStreetMap",
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
    "gpx.estimation": "D+ {montee} m (estimation BRouter)",
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
    "bouton.retirerDernier": "Remove last point",
    "bouton.toutEffacer": "Clear all",
    "bouton.boucler": "Back to start",
    "bouton.exporter": "Export GPX",
    "option.strict": "Strict mode: also avoid crossings to check",
    "option.ign": "Also use IGN paths missing from OSM (to check on site)",
    "option.comparer": "Show the route that ignores barriers",
    "resultat.distance": "Distance",
    "resultat.denivele": "Elevation",
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
    "legende.note": "Path layers are ticked on the map, top right, and show from zoom level 14.",
    "reglages.titre": "Settings",
    "reglages.cle": "IGN key for SCAN 25",
    "reglages.enregistrer": "Save",
    "reglages.note": "SCAN 25 is not open data. Without a key, the map uses Plan IGN, under the Open Licence.",
    "journal.titre": "Calculation log",
    "journal.note": "Errors, blockages and slowness, oldest first:",
    "journal.vide": "The log is empty for now.",
    "journal.illisible": "Log unreadable: {message}",
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
    "moteur.installer": "Install the BRouter engine (7 MB)",
    "moteur.installation": "Installing BRouter…",
    "moteur.installe": "BRouter installed.",
    "moteur.absent": "The BRouter engine is not installed yet.",
    "segment.telecharger": "Download BRouter data {nom} (70 to 250 MB)",
    "segment.telechargement": "Downloading {nom}…",
    "serveur.injoignable": "Server unreachable: {message}",
    "denivele.estimation": "BRouter estimate; gpx2elev calculation in progress…",
    "denivele.indisponible": "BRouter estimate; gpx2elev unavailable: {erreur}",
    "denivele.source": "gpx2elev, {modele}: 5 m sampling, 20 m smoothing, 2 m hysteresis; elevation from {min} to {max} m.",
    "calque.osm": "OSM paths",
    "calque.bdtopo": "BD TOPO paths (IGN)",
    "calque.chargement": "Loading the {nom}… (the first time, up to a minute)",
    "calque.zoom": "Zoom in further (level {niveau}) to see the paths.",
    "bdtopo.troncon": "Section",
    "bdtopo.acces": "pedestrian access: {valeur}",
    "bdtopo.prive": "private",
    "fond.scan25": "SCAN 25 (IGN)",
    "fond.plan": "Plan IGN",
    "fond.photos": "Aerial photos (IGN)",
    "fond.osm": "OpenStreetMap",
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
    "gpx.estimation": "D+ {montee} m (BRouter estimate)",
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
  if ($("pleinEcran")) {
    $("pleinEcran").title = t(document.body.classList.contains("plein-ecran") ? "pleinEcran.quitter" : "pleinEcran.entrer");
  }
  rafraichirPoints();
  construireFonds();
  rafraichirCalques();
  afficherStatut(...etat.statut);
  if (etat.dernier) ecrireResultat(etat.dernier);
}

document.addEventListener("nico579-langue", (e) => appliquerLangue(e.detail.code));

async function api(route, corps) {
  const options = corps === undefined ? {} : {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(corps),
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
const carte = L.map("carte").setView([vueInitiale.lat, vueInitiale.lon], vueInitiale.zoom);
carte.on("moveend", () => {
  const c = carte.getCenter();
  try {
    localStorage.setItem(CLE_VUE, JSON.stringify({ lat: c.lat, lon: c.lng, zoom: carte.getZoom() }));
  } catch (e) { /* sans importance */ }
});

function tuileIgn(couche, format, cle) {
  const base = cle ? "https://data.geopf.fr/private/wmts" : "https://data.geopf.fr/wmts";
  return `${base}?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=${couche}&STYLE=normal`
    + `&TILEMATRIXSET=PM&FORMAT=${format}&TILEMATRIX={z}&TILECOL={x}&TILEROW={y}`
    + (cle ? `&apikey=${encodeURIComponent(cle)}` : "");
}

const IGN = '© <a href="https://www.ign.fr/">IGN</a>';
let controleFonds = null;
let fondActif = null;
let couchesFonds = {};      // clé -> fond de carte Leaflet
carte.on("baselayerchange", (e) => { fondActif = e.layer; });

// ------------------------------------------------------------ calques de chemins

// Le tracé et ses franchissements passent au-dessus des chemins dessinés.
carte.createPane("trace").style.zIndex = 450;
const rendu = L.canvas({ padding: 0.2 });
const ZOOM_CALQUES = 14;
const CLE_CALQUES = "hike2gpx.calques";
const CALQUES = {
  osm: { groupe: L.layerGroup(), charge: null, sequence: 0 },
  bdtopo: { groupe: L.layerGroup(), charge: null, sequence: 0 },
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

function noteCalques(message) {
  $("noteCalques").textContent = message || "";
  $("noteCalques").hidden = !message;
}

function zoneVue(marge) {
  const b = carte.getBounds().pad(marge);
  return { s: b.getSouth(), w: b.getWest(), n: b.getNorth(), e: b.getEast() };
}

function couvre(zone, vue) {
  return Boolean(zone) && zone.s <= vue.s && zone.w <= vue.w && zone.n >= vue.n && zone.e >= vue.e;
}

async function chargerCalque(cle, zone) {
  const calque = CALQUES[cle];
  const numero = ++calque.sequence;
  const nom = t(`calque.${cle}`);
  const parametres = new URLSearchParams(Object.entries(zone).map(([k, v]) => [k, v.toFixed(5)]));
  noteCalques(t("calque.chargement", { nom: `${nom.charAt(0).toLowerCase()}${nom.slice(1)}` }));
  let donnees;
  try {
    donnees = await api(`${cle}?${parametres}`);
  } catch (e) {
    if (numero === calque.sequence) noteCalques(`${nom} : ${e.message}`);
    return;
  }
  if (numero !== calque.sequence || !carte.hasLayer(calque.groupe)) return;
  if (donnees.erreur) {
    noteCalques(`${nom} : ${ts(donnees.erreur)}`);
    return;
  }
  calque.groupe.clearLayers();
  DESSINS[cle](calque.groupe, donnees);
  calque.charge = zone;
  noteCalques("");
}

async function rafraichirCalques() {
  const actifs = Object.keys(CALQUES).filter((cle) => carte.hasLayer(CALQUES[cle].groupe));
  if (!actifs.length) { noteCalques(""); return; }
  if (carte.getZoom() < ZOOM_CALQUES) {
    // Vider plutôt que garder un morceau de réseau : de loin, il ferait
    // croire que le reste de la carte n'a pas de chemins.
    for (const cle of actifs) {
      CALQUES[cle].groupe.clearLayers();
      CALQUES[cle].charge = null;
      CALQUES[cle].sequence += 1;
    }
    noteCalques(t("calque.zoom", { niveau: ZOOM_CALQUES }));
    return;
  }
  const vue = zoneVue(0);
  await Promise.all(actifs.filter((cle) => !couvre(CALQUES[cle].charge, vue))
    .map((cle) => chargerCalque(cle, zoneVue(0.15))));
}

let minuterieCalques = null;
carte.on("moveend", () => {
  clearTimeout(minuterieCalques);
  minuterieCalques = setTimeout(rafraichirCalques, 400);
});
carte.on("overlayadd overlayremove", (e) => {
  const calque = Object.values(CALQUES).find((c) => c.groupe === e.layer);
  if (!calque) return;
  if (e.type === "overlayremove") {
    calque.groupe.clearLayers();
    calque.charge = null;
    calque.sequence += 1;    // une réponse encore en route ne redessine rien
  }
  try {
    localStorage.setItem(CLE_CALQUES, JSON.stringify(Object.keys(CALQUES).filter((cle) => carte.hasLayer(CALQUES[cle].groupe))));
  } catch (erreur) { /* sans importance */ }
  rafraichirCalques();
});

function restaurerCalques() {
  try {
    for (const cle of JSON.parse(localStorage.getItem(CLE_CALQUES) || "[]")) {
      if (CALQUES[cle]) CALQUES[cle].groupe.addTo(carte);
    }
  } catch (e) { /* stockage indisponible : calques éteints */ }
}

// Fonds de carte et contrôle des calques, refaits quand la clé IGN ou la
// langue change ; le fond affiché reste le même.
function construireFonds() {
  const cleActive = Object.keys(couchesFonds).find((cle) => couchesFonds[cle] === fondActif);
  couchesFonds = {};
  if (etat.cleIgn) {
    couchesFonds.scan25 = L.tileLayer(tuileIgn("GEOGRAPHICALGRIDSYSTEMS.MAPS", "image/jpeg", etat.cleIgn),
      { maxNativeZoom: 16, maxZoom: 19, attribution: IGN });
  }
  couchesFonds.plan = L.tileLayer(tuileIgn("GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2", "image/png"),
    { maxNativeZoom: 18, maxZoom: 19, attribution: IGN });
  couchesFonds.photos = L.tileLayer(tuileIgn("ORTHOIMAGERY.ORTHOPHOTOS", "image/jpeg"),
    { maxNativeZoom: 19, maxZoom: 19, attribution: IGN });
  couchesFonds.osm = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    { maxNativeZoom: 19, maxZoom: 19,
      attribution: `© <a href="https://www.openstreetmap.org/copyright">${t("attribution.osm")}</a>` });
  if (controleFonds) controleFonds.remove();
  if (fondActif) fondActif.remove();
  fondActif = (couchesFonds[cleActive] || Object.values(couchesFonds)[0]).addTo(carte);
  const fonds = Object.fromEntries(Object.entries(couchesFonds).map(([cle, couche]) => [t(`fond.${cle}`), couche]));
  const calques = Object.fromEntries(Object.entries(CALQUES).map(([cle, c]) => [t(`calque.${cle}`), c.groupe]));
  controleFonds = L.control.layers(fonds, calques, { collapsed: false, position: "topright" }).addTo(carte);
}

// ------------------------------------------------------------ points

const couches = L.layerGroup().addTo(carte);

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

function ajouterPoint(latlng) {
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
  planifierCalcul();
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
  etat.sequence++;
  etat.dernier = null;
  $("exporter").disabled = true;
  etat.minuterie = setTimeout(calculer, DELAI_CALCUL_MS);
}

function effacerResultat() {
  couches.clearLayers();
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
  const ign = $("ign").checked;
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
  else afficher(reponse);
  chargerJournal();
}

// ------------------------------------------------------------ journal

// Les dernières lignes du journal des calculs (erreurs, blocages, lenteurs),
// relues à l'ouverture de la section et après chaque calcul.
async function chargerJournal() {
  if (!$("journal").open) return;
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

function proposerInstallation() {
  $("actions").append(boutonAction(t("moteur.installer"), async () => {
    afficherStatut(() => t("moteur.installation"));
    const r = await api("moteur", {});
    if (r.erreur) afficherStatut(() => ts(r.erreur), true);
    else { $("actions").replaceChildren(); afficherStatut(() => t("moteur.installe")); planifierCalcul(); }
  }));
}

function afficherErreur(reponse) {
  effacerResultat();
  afficherStatut(() => texteErreur(reponse), true);
  for (const nom of reponse.segments_manquants || []) {
    $("actions").append(boutonAction(t("segment.telecharger", { nom }), async () => {
      afficherStatut(() => t("segment.telechargement", { nom }));
      const r = await api("segment", { nom });
      if (r.erreur) afficherStatut(() => ts(r.erreur), true);
      else planifierCalcul();
    }));
  }
  if (reponse.moteur_absent) proposerInstallation();
}

function lignes(feature) {
  return feature.geometry.coordinates.map((c) => [c[1], c[0]]);
}

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
  couches.clearLayers();
  if (r.naif && $("comparer").checked) {
    L.polyline(lignes(r.naif), { color: "#555", weight: 4, opacity: 0.7, dashArray: "6 8", interactive: false, pane: "trace" })
      .addTo(couches);
  }
  L.polyline(lignes(r.itineraire), { color: "#1565c0", weight: 5, opacity: 0.85, interactive: false, pane: "trace" })
    .addTo(couches);
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
    $("denivele").textContent = r.denivele_m == null ? "?" : `+${Math.round(r.denivele_m)} m`;
    $("sourceDenivele").textContent = r.erreurDenivele ? t("denivele.indisponible", { erreur: r.erreurDenivele })
      : t("denivele.estimation");
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
    r.erreurDenivele = ts(d.erreur);
    $("sourceDenivele").textContent = t("denivele.indisponible", { erreur: r.erreurDenivele });
    return;
  }
  r.denivele = d;
  ecrireDenivele(d);
  chargerJournal();
}

function ecrireDenivele(d) {
  $("denivele").textContent = `+${d.montee_m} m, −${d.descente_m} m`;
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
    : t("gpx.estimation", { montee: Math.round(r.denivele_m ?? 0) });
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
$("journal").addEventListener("toggle", chargerJournal);
new PleinEcran().addTo(carte);
// Échap quitte le plein écran du navigateur : la page revient avec lui.
document.addEventListener("fullscreenchange", () => {
  if (!document.fullscreenElement && document.body.classList.contains("plein-ecran")) appliquerPleinEcran(false);
});
$("strict").addEventListener("change", planifierCalcul);
$("ign").addEventListener("change", planifierCalcul);
$("comparer").addEventListener("change", planifierCalcul);
$("enregistrerCle").addEventListener("click", async () => {
  try {
    const r = await api("reglages", { cle_ign: $("cleIgn").value });
    if (r.erreur) { afficherStatut(() => ts(r.erreur), true); return; }
    etat.cleIgn = r.cle_ign;
    construireFonds();
    afficherStatut(() => t(etat.cleIgn ? "cle.enregistree" : "cle.retiree"));
  } catch (e) {
    afficherStatut(() => t("statut.erreur", { message: e.message }), true);
  }
});

async function demarrer() {
  try {
    const [infos, reglages] = await Promise.all([api("etat"), api("reglages")]);
    etat.version = infos.version;
    $("version").textContent = `${infos.version}, BRouter ${infos.brouter}`;
    etat.cleIgn = reglages.cle_ign || "";
    $("cleIgn").value = etat.cleIgn;
    if (!infos.moteur_installe) {
      afficherStatut(() => t("moteur.absent"), true);
      proposerInstallation();
    }
  } catch (e) {
    afficherStatut(() => t("serveur.injoignable", { message: e.message }), true);
  }
  restaurerCalques();     // avant le contrôle des fonds, pour que ses cases soient cochées
  construireFonds();
  rafraichirCalques();
}

demarrer();
