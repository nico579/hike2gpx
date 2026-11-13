// Comportement de la page (app.js) sous Node : un DOM et un Leaflet réduits au
// nécessaire, le réseau et les minuteries tenus à la main. Repris du banc de
// l'audit du 18 octobre (B06). Lancé par test_page.py, ou : node --test tests

"use strict";
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");
const assert = require("node:assert/strict");
const { couvertureCartographique, lienCouverturePays } = require("../hike2gpx/assets/web/presentation.js");
const { sectionGeneree, documentEnglish } = require("../tools/generer_couverture_pays.cjs");

function charger(preferences = {}, documentGpx = null) {
  const elements = new Map();
  const stockage = new Map(Object.entries(preferences));
  const minuteurs = [];
  const element = () => {
    const classes = new Set();
    return { disabled: true, hidden: false, checked: false, textContent: "", value: "", dataset: {},
      style: { setProperty(name, value) { this[name] = value; } },
      classList: { toggle(c, oui) { (oui ?? !classes.has(c)) ? classes.add(c) : classes.delete(c); },
        add: (c) => classes.add(c), contains: (c) => classes.has(c) },
      enfants: [], ecouteurs: {},
      get children() { return this.enfants; },
      querySelector(selecteur) {
        const id = /data-legende="(\w+)"/.exec(selecteur)?.[1];
        const cible = this.enfants.find((e) => e.dataset.legende === id);
        return { before: (e) => { const i = this.enfants.indexOf(cible); this.enfants.splice(i < 0 ? this.enfants.length : i, 0, e); } };
      },
      append(...e) { this.enfants.push(...e); }, replaceChildren(...e) { this.enfants = e; },
      after(...e) { this.suivants = e; },
      setAttribute(name, value) { this[name] = value; },
      addEventListener(type, f) { (this.ecouteurs[type] ??= []).push(f); }, remove() { this.removed = true; },
      click() { for (const action of this.ecouteurs.click || []) action(); } };
  };
  const couche = () => ({ handlers: {}, layers: [], addTo(parent) { this.addedTo = parent; parent.layers?.push(this); return this; },
    // Un marqueur se déplace et ouvre sa bulle seulement en planification : ces deux états se lisent ici.
    bindPopup() { this.popupLie = true; return this; }, unbindPopup() { this.popupLie = false; return this; },
    dragging: { actif: true, enable() { this.actif = true; }, disable() { this.actif = false; } },
    bindTooltip() { return this; },
    on(name, handler) { this.handlers[name] = handler; return this; }, setIcon() { return this; }, clearLayers() { this.layers = []; }, remove() { this.removed = true; if (this.addedTo?.layers) this.addedTo.layers = this.addedTo.layers.filter((c) => c !== this); }, closePopup() {} });
  const carte = { handlers: {}, layers: [], zoom: 14,
    eachLayer(f) { const voir = (c) => { f(c); (c.layers || []).forEach(voir); }; this.layers.forEach(voir); }, setView(center, zoom) { this.center = center; this.viewZoom = zoom; return this; },
    fitBounds(bounds, options) { this.fit = { bounds, options }; return this; },
    on(name, handler) { const precedent = this.handlers[name]; this.handlers[name] = precedent
      ? (...args) => { precedent(...args); handler(...args); } : handler; }, createPane() { return { style: {} }; },
    hasLayer(c) { return this.layers.includes(c); }, getZoom() { return this.zoom; }, setZoom(zoom) { this.zoom = zoom; return this; },
    invalidateSize() {},
    fire(name, e) { this.handlers[name]?.(e); },
    closePopup() { this.popup = null; },
    getCenter() { return { lat: (this.vue.s + this.vue.n) / 2, lng: (this.vue.w + this.vue.e) / 2 }; },
    vue: { s: 43.31, w: 6.01, n: 43.33, e: 6.04 },
    getBounds() { const v = this.vue; return { getSouth: () => v.s, getWest: () => v.w, getNorth: () => v.n,
      getEast: () => v.e }; } };
  const requetes = [];
  const pressePapiers = [];
  const confirmations = Object.assign([], { reponse: false });
  const evenements = [];
  const corps = element();
  for (const [id, cle] of [["entree-trace", "menu.trace"], ["entree-reglages", "menu.reglages"]]) {
    const tab = element();
    tab.dataset.i18n = cle;
    elements.set(id, tab);
  }
  const lignesLegende = elements.get("legendRows") || element();
  elements.set("legendRows", lignesLegende);
  const html = fs.readFileSync(path.join(__dirname, "..", "hike2gpx", "assets", "web", "index.html"), "utf8");
  for (const [, id] of html.matchAll(/<li data-legende="(\w+)" hidden>/g)) {
    const ligne = element();
    ligne.dataset.legende = id;
    ligne.hidden = true;
    lignesLegende.enfants.push(ligne);
  }
  // Le DOM initial reproduit la valeur cochée dans index.html.
  const strict = element();
  strict.checked = true;
  elements.set("strict", strict);
  // Les pages du menu démarrent masquées, comme dans index.html.
  const itineraires = element();
  itineraires.hidden = true;
  elements.set("pane-itineraires", itineraires);
  const contexte = vm.createContext({
    console, URL, URLSearchParams, Blob, Date, Number, String, AbortController, performance, TextDecoder,
    CustomEvent: class { constructor(type, init) { this.type = type; this.detail = init?.detail; } },
    DOMParser: class { parseFromString() { return documentGpx; } },
    document: { getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
      createElement: element, createTextNode: String, body: corps, documentElement: element(),
       addEventListener() {}, dispatchEvent(e) { evenements.push(e.type); }, querySelectorAll(selector) {
         if (selector === "[data-i18n]") return [...elements.values()].filter((el) => el.dataset.i18n);
         if (selector === "[data-map-overlay]")
           return elements.get("legendRows")?.enfants.filter((ligne) => ligne.dataset.mapOverlay) || [];
         return [];
       } },
    localStorage: { getItem(key) { return stockage.get(key) ?? null; }, setItem(key, value) { stockage.set(key, value); } },
    confirm: (texte) => { confirmations.push(texte); return confirmations.reponse; },
    navigator: { clipboard: { async writeText(texte) { pressePapiers.push(texte); } } },
    setTimeout(callback, ms) { minuteurs.push({ callback, ms }); return minuteurs.length; },
    clearTimeout(id) { if (minuteurs[id - 1]) minuteurs[id - 1].annule = true; },
    setInterval() { return 1; }, clearInterval() {}, requestAnimationFrame(f) { f(); },
     L: { map() { return carte; }, layerGroup: couche, canvas: couche,
       popup: (options) => ({ options, setLatLng(latlng) { this.latlng = latlng; return this; },
         setContent(content) { this.content = content; return this; },
         openOn(map) { map.popup = this; return this; } }),
       vectorGrid: { protobuf: (url, options) => Object.assign(couche(), { url, options }) },
      polyline: (points, options) => Object.assign(couche(), { points, options }),
      rectangle: (bounds, options) => Object.assign(couche(), { bounds, options }),
      circleMarker: (points, options) => Object.assign(couche(), { points, options }),
      marker: (latlng, options) => Object.assign(couche(), { position: latlng, options, getLatLng() { return this.position; } }),
      tileLayer: Object.assign((url, options) => Object.assign(couche(), { url, options }),
        { wms: (url, options) => Object.assign(couche(), { url, options }) }),
      CRS: { EPSG4326: { code: "EPSG:4326" } }, divIcon: (options) => ({ options }),
      control: { scale: (options) => Object.assign(couche(), { options, conteneur: element(),
        getContainer() { return this.conteneur; } }),
        layers: (fonds, calques) => Object.assign(couche(), { fonds, calques,
        addOverlay(layer, name) { this.calques[name] = layer; return this; },
        removeLayer(layer) {
          for (const [name, value] of Object.entries(this.calques)) {
            if (value === layer) delete this.calques[name];
          }
          return this;
        } }) },
      latLng: (lat, lng) => ({ lat: Array.isArray(lat) ? lat[0] : lat,
        lng: Array.isArray(lat) ? lat[1] : lng, distanceTo() { return 1000; } }),
      Control: { extend: () => class { addTo() { return this; } } }, DomUtil: { create: element },
      DomEvent: { on() {}, disableClickPropagation() {} } },
    // Comme le vrai fetch, une requête coupée par son signal est rejetée.
    fetch(url, options) {
      return new Promise((resolve, reject) => {
        requetes.push({ url, options, resolve, reject });
        options?.signal?.addEventListener("abort", () => reject(new Error("abandonnée")));
      });
    },
  });
  contexte.window = contexte;
  const providers = path.join(__dirname, "..", "hike2gpx", "assets", "web", "providers");
  vm.runInContext("window.HIKE2GPX_MAP_PROVIDERS = {};", contexte);
  for (const fichier of fs.readdirSync(providers).filter((nom) => /^[a-z]{2}\.js$/.test(nom)).sort()) {
    vm.runInContext(fs.readFileSync(path.join(providers, fichier), "utf8"), contexte);
  }
  vm.runInContext('window.HIKE2GPX_MAP_PROVIDERS.autre = '
    + '{ defaultBase: "osm", overlays: [], bases: () => ({}) };', contexte);
  // tuiles.js avant app.js, comme dans la page : le décodeur des tuiles d'un lot.
  vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "hike2gpx", "assets", "web", "tuiles.js"), "utf8"), contexte);
  const source = path.join(__dirname, "..", "hike2gpx", "assets", "web", "app.js");
  vm.runInContext(fs.readFileSync(source, "utf8")
    + "\nglobalThis.page = { etat, calculer, planifierCalcul, planifier, ajouterPoint, boucler, basculerPleinEcran,"
    + " appliquerLangue, texteErreur, ts, rafraichirCalques, reglerZoomCalques, borneZoomCalques, CALQUES, afficherExtrait, afficherErreur,"
    + " afficherDisponibilite,"
     + " debutLecture, finLecture, afficherLectures, afficherDonnees, construireFonds, choisirPays,"
    + " fond: () => fondActif, fonds: () => couchesFonds, controle: () => controleFonds, restaurerCalques,"
    + " preparerFleches, afficherFleches, fleches, traceGpxImporte, bulleTraceImportee, TEXTES, providers: window.HIKE2GPX_MAP_PROVIDERS,"
    + " grilleCases, chargerLots, chargerFonds, preparerCase, suivreLot, casesVisibles, nomCase, nomCarre, boiteCase,"
    + " horsLigne, activerHorsLigne, dessinerCases, lancerSuivant, sourceAGarder,"
    + " bornesTuile, basculerPartage, selectionGrille, adresseArchive, nomArchive, enregistrerReglages, lireNomTrace, couleurKml, verifierZonePlanification, majLegende, coucheCalque,"
    + " setFleches: (valeur) => { flechesTrace = valeur; } };", contexte);
  const derniere = () => requetes.filter((r) => r.url === "/api/itineraire").at(-1);
  return { page: contexte.page, elements, document: contexte.document, derniere, corps, requetes, carte,
    confirmations, stockage, minuteurs, pressePapiers, evenements };
}

function resultat(lonArrivee) {
  return { itineraire: { type: "Feature", properties: {},
    geometry: { type: "LineString", coordinates: [[6, 43.3, 0], [lonArrivee, 43.3, 0]] } },
    franchissements: [], sur_le_trace: [], portions_ign: [], longueur_m: 809, denivele_m: 0, duree_s: 0.1 };
}

const ligneLegende = (elements, id) => elements.get("legendRows").enfants.find((l) => l.dataset.legende === id);
const legendeVisible = (elements) => elements.get("legendRows").enfants.filter((l) => !l.hidden)
  .map((l) => l.dataset.legende || l.dataset.mapOverlay);

const repondre = (requete, corps) => requete.resolve({ ok: true, json: async () => corps });

const tic = () => new Promise((fin) => setImmediate(fin));

// Le volet des tuiles hors ligne ouvert : la page relit les lots du PC, puis le catalogue du serveur.
async function ouvrirHorsLigne(page, requetes, lots = [], catalogue = [], fonds = []) {
  page.activerHorsLigne(true);
  repondre(requetes.findLast((r) => r.url === "/api/hors_ligne"), { lots, fonds });
  await tic();
  repondre(requetes.findLast((r) => r.url === "/api/catalogue_lots"), { lots: catalogue });
  await tic();
}

const changer = (el) => { for (const f of el.ecouteurs.change || []) f(); };

test("l'onglet « Hors ligne » : la grille du routage, la sélection, le bilan et la file", async () => {
  const { page, elements, requetes, carte } = charger();
  // Les tableaux de la page viennent d'un autre contexte : on compare leur JSON.
  const json = (v) => JSON.parse(JSON.stringify(v));
  assert.deepEqual(json(page.casesVisibles()), ["E5_N40"], "la vue de Garéoult tombe dans la case E5_N40");
  assert.deepEqual(json(page.boiteCase("W5_N45")), [45, -5, 50, 0]);
  assert.equal(page.nomCase(-0.5, -0.5), "W5_S5");
  assert.equal(page.grilleCases.layers.length, 0, "onglet fermé : pas de grille");
  await ouvrirHorsLigne(page, requetes, [{ case: "E5_N40", octets: 135e6 }],
    [{ case: "E5_N40", octets: 247e6, etat: "ancien" }]);
  assert.equal(carte.zoom, 14, "la grille paraît sans toucher au zoom");
  let [cadre] = page.grilleCases.layers;
  assert.deepEqual(json(cadre.bounds), [[40, 5], [45, 10]]);
  assert.equal(cadre.options.color, "#1b7a3e", "vert : sur ce PC");
  assert.match(elements.get("hlAide").textContent, /^Cliquez les cases de 5°/);
  assert.equal(elements.get("offlineHint").hidden, false, "l'aide aussi sur la carte");
  assert.equal(elements.get("hlSelection").textContent, "Aucune case sélectionnée.");
  assert.equal(elements.get("hlTelecharger").disabled, true);
  // Un clic sélectionne : la case vire au bleu, le bilan dit ce qu'elle engage.
  cadre.handlers.click();
  [cadre] = page.grilleCases.layers;
  assert.equal(cadre.options.color, "#1565c0", "bleu : sélectionnée");
  assert.equal(elements.get("hlSelection").textContent, "1 à télécharger : 247 Mo. 1 déjà sur ce PC (135 Mo).");
  assert.equal(elements.get("hlTelecharger").disabled, false);
  // Une case que le serveur ne publie pas se fabrique sur le PC.
  carte.vue = { s: 42.5, w: 2.5, n: 42.7, e: 2.8 };
  page.dessinerCases();
  page.grilleCases.layers[0].handlers.click();
  assert.equal(elements.get("hlSelection").textContent,
    "1 à télécharger : 247 Mo. 1 à fabriquer sur ce PC : environ 1 h. 1 déjà sur ce PC (135 Mo).");
  // Télécharger : les tuiles partent l'une après l'autre.
  elements.get("hlTelecharger").click();
  await tic();
  assert.deepEqual(JSON.parse(requetes.findLast((r) => r.url === "/api/telecharger_lot").options.body), { case: "E5_N40" });
  repondre(requetes.findLast((r) => r.url === "/api/telecharger_lot"), { lot_en_cours: { actif: true } });
  await tic();
  repondre(requetes.findLast((r) => r.url === "/api/lot_en_cours"),
    { actif: true, case: "E5_N40", etape: "telechargement", faites: 0, total: 247e6, duree_s: 3 });
  await tic();
  assert.match(elements.get("hlEnCours").textContent, /E5_N40.*\(1 en attente\)$/);
  assert.equal(elements.get("hlFile").hidden, false);
  assert.equal(page.grilleCases.layers[0].options.color, "#e07b00", "orange : E0_N40 attend son tour");
  // La première finie, la suivante part d'elle-même.
  page.suivreLot();
  await tic();
  repondre(requetes.findLast((r) => r.url === "/api/lot_en_cours"), { actif: false, etape: "fini", case: "E5_N40" });
  await tic();
  repondre(requetes.findLast((r) => r.url === "/api/hors_ligne"), { lots: [{ case: "E5_N40", octets: 247e6 }], fonds: [] });
  await tic();
  await tic();
  assert.deepEqual(JSON.parse(requetes.findLast((r) => r.url === "/api/preparer_lot").options.body), { case: "E0_N40" });
  // L'onglet quitté, la grille et l'aide s'en vont.
  page.activerHorsLigne(false);
  assert.equal(page.grilleCases.layers.length, 0);
  assert.equal(elements.get("offlineHint").hidden, true);
});

test("l'onglet « Hors ligne » en mode fond : les cases de 1°, la source et la vue", async () => {
  const { page, elements, requetes, carte } = charger();
  page.etat.fondsHorsLigne = { scan25: "SCAN 25 (IGN)", plan: "Plan IGN" };
  await ouvrirHorsLigne(page, requetes);
  elements.get("hlFond").checked = true;
  changer(elements.get("hlFond"));
  // La page ne touche plus au zoom ; de loin, trop de cases : il faut se rapprocher.
  carte.zoom = 6;
  page.dessinerCases();
  assert.equal(page.grilleCases.layers.length, 0, "au zoom 6, trop de cases : il faut se rapprocher");
  assert.match(elements.get("hlAide").textContent, /^Rapprochez-vous/);
  assert.equal(elements.get("hlLegendeServeur").hidden, true, "pas de serveur pour les fonds");
  // Le fond téléchargé est celui de la liste du haut : ici le Plan IGN affiché.
  page.construireFonds();
  page.dessinerCases();
  assert.equal(page.sourceAGarder(), "plan");
  assert.equal(elements.get("hlFondChoisi").hidden, true, "le fond choisi se garde : rien à dire");
  // Un fond qui ne se garde pas hors ligne : le volet dit lequel choisir (pas le SCAN 25, sans clé IGN).
  carte.handlers.baselayerchange({ layer: page.fonds().osm });
  assert.equal(page.sourceAGarder(), null);
  assert.equal(elements.get("hlFondChoisi").textContent,
    "Le fond affiché ne se garde pas hors ligne. Choisissez dans la liste du haut : Plan IGN.");
  carte.handlers.baselayerchange({ layer: page.fonds().plan });
  assert.equal(page.sourceAGarder(), "plan");
  carte.zoom = 12;
  page.dessinerCases();
  const [carre] = page.grilleCases.layers;
  assert.equal(JSON.stringify(carre.bounds), "[[43,6],[44,7]]", "la case de Garéoult, N43E006");
  assert.equal(carre.options.dashArray, "5 5", "pointillés : pas encore de fond");
  carre.handlers.click();
  assert.equal(elements.get("hlSelection").textContent, "1 case(s) : environ 1 Go et 35 min.");
  elements.get("hlTelecharger").click();
  await tic();
  assert.deepEqual(JSON.parse(requetes.findLast((r) => r.url === "/api/preparer_fond").options.body),
    { carres: ["N43E006"], source: "plan" }, "la case choisie");
});

test("un fond de carte installé ne s'ajoute pas aux fonds en ligne, et se retire depuis le volet", async () => {
  const { page, elements, requetes, carte, confirmations } = charger();
  page.etat.fondsHorsLigne = { scan25: "SCAN 25 (IGN)", plan: "Plan IGN" };
  const fonds = [
    { nom: "N43E006-plan", zone: [43, 6, 44, 7], zoom: [13, 16], source: "plan", octets: 6e8 },
    { nom: "E5_N40-scan25", zone: [40, 5, 45, 10], zoom: [6, 13], source: "scan25", octets: 4e8 }];
  const charge = page.chargerFonds();
  repondre(requetes.findLast((r) => r.url === "/api/hors_ligne"), { lots: [], fonds });
  await charge;
  // « En ligne » ne liste que les cartes en ligne : les fonds téléchargés
  // servent au téléphone, à qui le PC les partage.
  assert.equal(page.fonds().horsLigne, undefined);
  assert.equal(Object.keys(page.controle().fonds).includes("Carte hors ligne"), false);
  // Dans l'onglet, en mode fond, la case installée est verte ; sélectionnée, elle se retire.
  await ouvrirHorsLigne(page, requetes, [], [], fonds);
  elements.get("hlFond").checked = true;
  changer(elements.get("hlFond"));
  carte.zoom = 12;
  page.dessinerCases();
  assert.equal(page.grilleCases.layers[0].options.color, "#1b7a3e");
  page.grilleCases.layers[0].handlers.click();
  assert.equal(elements.get("hlSelection").textContent, "1 déjà sur ce PC (600 Mo).");
  assert.equal(elements.get("hlTelecharger").disabled, true, "rien à télécharger : le Plan IGN est déjà là");
  assert.equal(elements.get("hlPartager").hidden, false, "ce qui est là se partage");
});

test("une case qui n'a qu'un autre fond n'est pas « déjà là » pour le fond choisi", async () => {
  const { page, elements, requetes, carte } = charger();
  page.etat.fondsHorsLigne = { scan25: "SCAN 25 (IGN)", plan: "Plan IGN" };
  // La case de Garéoult a un SCAN 25 ; la carte affiche le Plan IGN.
  const fonds = [{ nom: "N43E006-scan25", zone: [43, 6, 44, 7], zoom: [13, 16], source: "scan25", octets: 6e8 }];
  const charge = page.chargerFonds();
  repondre(requetes.findLast((r) => r.url === "/api/hors_ligne"), { lots: [], fonds });
  await charge;
  await ouvrirHorsLigne(page, requetes, [], [], fonds);
  elements.get("hlFond").checked = true;
  changer(elements.get("hlFond"));
  carte.zoom = 12;
  page.dessinerCases();
  page.grilleCases.layers[0].handlers.click();
  assert.equal(elements.get("hlSelection").textContent, "1 case(s) : environ 1 Go et 35 min.");
  assert.equal(elements.get("hlTelecharger").disabled, false, "le Plan IGN est à télécharger");
  assert.equal(elements.get("hlPartager").hidden, true, "rien à partager en Plan IGN");
});

test("le partage s'ouvre depuis le volet : son QR code, son état dans le volet, de quoi l'arrêter", async () => {
  const { page, elements, requetes } = charger();
  const attendre = () => new Promise((fin) => setImmediate(fin));
  page.basculerPartage(true, { lots: ["E5_N40"], carres: [] });
  const ouverture = requetes.findLast((r) => r.url === "/api/partage");
  assert.deepEqual(JSON.parse(ouverture.options.body), { ouvrir: true, lots: ["E5_N40"], carres: [] });
  repondre(ouverture, { ouvert: true, url: "http://192.168.1.20:8799/depot/catalog.json", qr: "<svg>qr</svg>",
    lien: "hike2gpx://depot?url=…", lots: ["E5_N40"], fonds: ["E5_N40-scan25"], octets: 412e6 });
  await attendre();
  assert.equal(elements.get("partageQr").innerHTML, "<svg>qr</svg>");
  assert.match(elements.get("partageFenetreTexte").textContent,
    /^Partagé : 1 zone de carte et 1 zone de routage, 412 Mo\. .*« Gestion des cartes », puis « Scanner le QR code de l’ordinateur »/);
  // Le QR code s'ouvre dans sa fenêtre, comme lidar2map ; Fermer la cache, le volet la rouvre.
  assert.equal(elements.get("partageFenetre").hidden, false);
  assert.equal(elements.get("arreterPartageFenetre").hidden, false);
  elements.get("fermerFenetrePartage").click();
  assert.equal(elements.get("partageFenetre").hidden, true);
  // Le partage reste ouvert : le volet le dit, et propose le QR code et l'arrêt.
  assert.equal(elements.get("hlPartage").hidden, false);
  assert.equal(elements.get("hlPartageTexte").textContent,
    "Partage ouvert : 1 zone de carte et 1 zone de routage, 412 Mo.");
  elements.get("hlPartageQr").click();
  assert.equal(elements.get("partageFenetre").hidden, false);
  elements.get("hlPartageArreter").click();
  const fermeture = requetes.findLast((r) => r.url === "/api/partage");
  assert.deepEqual(JSON.parse(fermeture.options.body), { ouvrir: false });
  repondre(fermeture, { ouvert: false });
  await attendre();
  assert.equal(elements.get("partageQr").innerHTML, "", "le QR code s'efface : son jeton ne vaut plus");
  assert.equal(elements.get("hlPartage").hidden, true);
  assert.equal(elements.get("partageFenetre").hidden, true, "partage fermé : plus de fenêtre");
});

test("un partage refusé s'affiche dans sa fenêtre, sans QR code ni bouton d'arrêt", async () => {
  const { page, elements, requetes } = charger();
  page.basculerPartage(true, { lots: ["E5_N40"], carres: [] });
  repondre(requetes.findLast((r) => r.url === "/api/partage"), { ouvert: false, erreur: "Pas de réseau local." });
  await tic();
  assert.equal(elements.get("partageFenetre").hidden, false);
  assert.equal(elements.get("partageFenetreTexte").textContent, "Partage impossible : Pas de réseau local.");
  assert.equal(elements.get("arreterPartageFenetre").hidden, true);
  assert.equal(elements.get("hlPartage").hidden, true);
});

test("le texte du partage ne nomme que ce qui est partagé, et la bonne page du téléphone", async () => {
  const { page, elements, requetes } = charger();
  const ouvrir = async (r) => {
    page.basculerPartage(true, { lots: [], carres: [] });
    repondre(requetes.findLast((q) => q.url === "/api/partage"), { ouvert: true, qr: "<svg/>", ...r });
    await tic();
    return elements.get("partageFenetreTexte").textContent;
  };
  // Des cartes seules : pas de « 0 zone de routage ».
  assert.match(await ouvrir({ lots: [], fonds: ["N43E005-scan25", "N43E006-scan25"], octets: 1.7e9 }),
    /^Partagé : 2 zones de carte, 1,7 Go\. .*« Gestion des cartes »/);
  // Du routage seul : le téléphone le scanne depuis ses itinéraires.
  assert.match(await ouvrir({ lots: ["E5_N40"], fonds: [], octets: 248e6 }),
    /^Partagé : 1 zone de routage, 248 Mo\. .*« Gestion des itinéraires »/);
  assert.equal(await ouvrir({ lots: [], fonds: [], octets: 0 }),
    "Rien à partager : ce PC n’a ni zone de carte ni zone de routage.");
});

test("les réglages s'enregistrent à la fermeture de leur page, seulement s'ils ont changé", async () => {
  const { page, document, requetes } = charger();
  page.etat.cleIgn = "ancienne";
  page.etat.renouvellementJours = 30;
  document.getElementById("cleIgn").value = "ancienne";
  document.getElementById("renouvellementJours").value = "30";
  const avant = requetes.length;
  const envois = () => requetes.filter((r) => r.url === "/api/reglages").length;
  const initiaux = envois();
  await page.enregistrerReglages();
  assert.equal(requetes.length, avant, "rien n'a changé : rien n'est envoyé");
  // Une nouvelle clé et un délai : un seul envoi, et les champs gardent ce que le serveur a retenu.
  document.getElementById("cleIgn").value = "nouvelle";
  document.getElementById("renouvellementJours").value = "45";
  const envoi = page.enregistrerReglages();
  const requete = requetes.findLast((r) => r.url === "/api/reglages");
  assert.deepEqual(JSON.parse(requete.options.body), { cle_ign: "nouvelle", renouvellement_jours: 45 });
  repondre(requete, { cle_ign: "nouvelle", renouvellement_jours: 45 });
  await envoi;
  assert.equal(page.etat.cleIgn, "nouvelle");
  assert.equal(page.etat.renouvellementJours, 45);
  // Un délai impossible est abandonné : le champ revient à la valeur enregistrée.
  document.getElementById("renouvellementJours").value = "9999";
  await page.enregistrerReglages();
  assert.equal(document.getElementById("renouvellementJours").value, 45);
  assert.equal(envois(), initiaux + 1, "pas de second envoi");
});

test("le volet de la grille partage sa sélection seule au téléphone", async () => {
  const { page, elements, requetes } = charger();
  await ouvrirHorsLigne(page, requetes, [{ case: "E5_N40", octets: 135e6 }], [{ case: "E5_N40", octets: 247e6, etat: "a_jour" }]);
  assert.equal(elements.get("hlPartager").hidden, true, "rien de sélectionné");
  page.grilleCases.layers[0].handlers.click();
  assert.equal(elements.get("hlPartager").hidden, false);
  assert.equal(elements.get("hlPartager").hidden, false, "« Partager au téléphone », libellé fixe");
  elements.get("hlPartager").click();
  assert.deepEqual(JSON.parse(requetes.findLast((r) => r.url === "/api/partage").options.body),
    { ouvrir: true, lots: ["E5_N40"], carres: [] }, "la zone choisie, pas tout le PC");
});

test("l'archive zip : « Exporter » prend la sélection, « Importer » envoie le zip tel quel", async () => {
  const { page, elements, requetes } = charger();
  await ouvrirHorsLigne(page, requetes, [{ case: "E5_N40", octets: 135e6 }], []);
  assert.equal(elements.get("hlExporter").hidden, true, "rien de sélectionné");
  page.grilleCases.layers[0].handlers.click();
  assert.equal(elements.get("hlExporter").hidden, false);
  assert.equal(page.adresseArchive(page.selectionGrille()), "/archive.zip?lots=E5_N40&carres=");
  // Le nom proposé dans « Enregistrer sous », celui que donne le serveur.
  assert.equal(page.nomArchive(page.selectionGrille()), "hike2gpx-E5_N40.zip");
  assert.equal(page.nomArchive({ lots: [], carres: ["N43E006", "N44E006"], source: "scan25" }), "hike2gpx-N43E006-scan25-et-1.zip");
  assert.equal(page.adresseArchive({ lots: [], carres: ["N43E006", "N44E006"], source: "scan25" }),
    "/archive.zip?lots=&carres=N43E006%2CN44E006&source=scan25");
  const fichier = { name: "ami.zip", size: 248e6 };
  elements.get("fichierArchive").ecouteurs.change[0]({ target: { files: [fichier], value: "ami.zip" } });
  assert.equal(elements.get("hlEnCours").textContent, "Import de ami.zip (248 Mo) en cours…");
  const envoi = requetes.findLast((r) => r.url === "/api/importer_archive");
  assert.equal(envoi.options.body, fichier, "le zip part tel quel, sans JSON");
  repondre(envoi, { importe: { lots: ["E5_N40"], fonds: ["N43E006-scan25"] }, lots: [], fonds: [] });
  await tic();
  await tic();
  assert.equal(elements.get("hlEnCours").textContent, "ami.zip importée : 1 carte(s) et 1 zone(s) de routage.");
});

test("la note suit la préparation hors ligne, puis la case est prête", async () => {
  const { page, requetes, elements, minuteurs } = charger();
  const suivi = page.suivreLot();
  repondre(requetes.findLast((r) => r.url === "/api/lot_en_cours"),
    { actif: true, case: "E5_N40", etape: "calques", faites: 4, total: 16, duree_s: 125 });
  await suivi;
  assert.equal(elements.get("lotHorsLigneTexte").textContent,
    "Préparation de la case E5_N40 : chemins et franchissements 4/16, depuis 2 min");
  assert.equal(elements.get("arreterLot").hidden, false);
  assert.equal(elements.get("lotHorsLigneBarre").style.width, "25%");
  assert.equal(minuteurs.at(-1).ms, 2000, "relu toutes les deux secondes");
  const fin = page.suivreLot();
  repondre(requetes.findLast((r) => r.url === "/api/lot_en_cours"), { actif: false, case: "E5_N40", etape: "fini" });
  await fin;
  assert.equal(elements.get("lotHorsLigneTexte").textContent, "Case E5_N40 prête hors ligne.");
  assert.equal(elements.get("arreterLot").hidden, true);
});

test("une case de fond de carte se nomme par sa carte, une zone de routage par son nom", async () => {
  const { page, requetes, elements } = charger();
  page.etat.fondsHorsLigne = { scan25: "SCAN 25 (IGN)" };
  const suivi = page.suivreLot();
  repondre(requetes.findLast((r) => r.url === "/api/lot_en_cours"),
    { actif: true, case: "N43E006", source: "scan25", etape: "fond", faites: 30, total: 600, duree_s: 60 });
  await suivi;
  assert.equal(elements.get("lotHorsLigne").dataset.titre, "Carte hors ligne « SCAN 25 (IGN) »");
  assert.equal(elements.get("lotHorsLigneTexte").textContent,
    "Préparation de la case N43E006 : téléchargement des tuiles 30/600, depuis 1 min");
  const zone = page.suivreLot();
  repondre(requetes.findLast((r) => r.url === "/api/lot_en_cours"),
    { actif: true, case: "E5_N40", etape: "calques", faites: 4, total: 16, duree_s: 125 });
  await zone;
  assert.equal(elements.get("lotHorsLigne").dataset.titre, "Zone de routage");
});

test("un clic droit affiche les coordonnées et permet de les copier sans ajouter de point", async () => {
  const { carte, page, pressePapiers } = charger();
  carte.handlers.contextmenu({ latlng: { lat: 50.71234567, lng: 10.24987654 } });
  const [titre, bouton] = carte.popup.content.enfants;
  assert.equal(titre.enfants[0].value, "50.712346, 10.249877");
  assert.equal(bouton.textContent, "Copier les coordonnées");
  await bouton.ecouteurs.click[0]();
  assert.deepEqual(pressePapiers, ["50.712346, 10.249877"]);
  assert.equal(page.etat.points.length, 0);
});

function documentGpx(segments) {
  const point = ([lat, lon]) => ({ hasAttribute: (nom) => nom === "lat" || nom === "lon",
    getAttribute: (nom) => nom === "lat" ? String(lat) : String(lon) });
  return { documentElement: { localName: "gpx" }, getElementsByTagName: () => [],
    getElementsByTagNameNS(_ns, nom) {
      if (nom === "trkseg") return segments.map((s) => ({ getElementsByTagNameNS: (_n, tag) =>
        tag === "trkpt" ? s.map(point) : [] }));
      return [];
    } };
}

test("un GPX chargé se coche dans les couches sans perdre son tracé", async () => {
  const { page, elements, carte, stockage } = charger({}, documentGpx([[[43.3, 6], [43.31, 6.02]]]));
  const fichier = { name: "2026-09-20_09-03.gpx", size: 250, text: async () => "<gpx/>" };
  await elements.get("fichierGpx").ecouteurs.change[0]({ target: { files: [fichier], value: "rando.gpx" } });
  assert.equal(page.traceGpxImporte.layers.length, 2);
  assert.equal(page.traceGpxImporte.layers[0].options.pane, "gpxImporte");
  assert.equal(page.traceGpxImporte.layers[1].options.color, "#ffe14a");
  assert.equal(JSON.stringify(carte.fit.bounds), "[[43.3,6],[43.31,6.02]]");
  assert.deepEqual(Object.keys(page.controle().calques),
    ["OSM", "IGN", "2026-09-20_09-03"]);
  page.majLegende();
  assert.equal(ligneLegende(elements, "gpx").hidden, false);
  page.traceGpxImporte.remove();
  carte.handlers["overlayadd overlayremove"]({ layer: page.traceGpxImporte, type: "overlayremove" });
  assert.equal(page.traceGpxImporte.layers.length, 2);
  page.traceGpxImporte.addTo(carte);
  page.construireFonds();
  assert.equal(page.controle().calques["2026-09-20_09-03"], page.traceGpxImporte);
  assert.equal(elements.get("chargerGpxTexte").textContent, "Retirer l'import");
  assert.equal(page.etat.points.length, 0);
  assert.equal(stockage.has("hike2gpx.points"), false);
  elements.get("chargerGpx").click();
  assert.equal(page.traceGpxImporte.layers.length, 0);
  assert.equal(page.controle().calques["2026-09-20_09-03"], undefined);
  page.majLegende();
  assert.equal(ligneLegende(elements, "gpx").hidden, true);
  assert.equal(elements.get("chargerGpxTexte").textContent, "Importer un GPX ou un KML");
});

test("la bulle d'une trace importée la retire, sans passer par le menu", async () => {
  // Nico, 2026-11-13 : « quand j'importe un gpx/kml, y a rien pour l'effacer ».
  const { page, elements } = charger({}, documentGpx([[[43.3, 6], [43.31, 6.02]]]));
  await elements.get("fichierGpx").ecouteurs.change[0]({ target: {
    files: [{ name: "rando.gpx", size: 250, text: async () => "<gpx/>" }], value: "rando.gpx" } });
  assert.ok(page.traceGpxImporte.layers.length > 0);
  const bulle = page.bulleTraceImportee({ nom: "rando", segments: [[[43.3, 6], [43.31, 6.02]]], infos: {} });
  const bouton = bulle.enfants.at(-1);
  assert.equal(bouton.textContent, "Retirer l'import");
  bouton.click();
  assert.equal(page.traceGpxImporte.layers.length, 0);
  assert.equal(elements.get("chargerGpxTexte").textContent, "Importer un GPX ou un KML");
});

test("un GPX invalide conserve le tracé précédemment chargé", async () => {
  const document = documentGpx([[[43.3, 6], [43.31, 6.02]]]);
  const { page, elements } = charger({}, document);
  const importer = (name) => elements.get("fichierGpx").ecouteurs.change[0]({ target: {
    files: [{ name, size: 250, text: async () => "<gpx/>" }], value: name } });
  await importer("bon.gpx");
  document.getElementsByTagNameNS = () => [{ getElementsByTagNameNS: () => [
    { hasAttribute: () => true, getAttribute: (nom) => nom === "lat" ? "91" : "6" }] }];
  await importer("mauvais.gpx");
  assert.equal(page.traceGpxImporte.layers.length, 2);
  assert.equal(page.controle().calques.bon, page.traceGpxImporte);
  assert.equal(page.controle().calques.mauvais, undefined);
  assert.equal(elements.get("erreurGpx").hidden, false);
});

test("le nom du fichier GPX est échappé dans le contrôle Leaflet", async () => {
  const { page, elements } = charger({}, documentGpx([[[43.3, 6], [43.31, 6.02]]]));
  await elements.get("fichierGpx").ecouteurs.change[0]({ target: {
    files: [{ name: "<b>rando</b>.gpx", size: 250, text: async () => "<gpx/>" }], value: "" } });
  assert.equal(page.controle().calques["&lt;b&gt;rando&lt;/b&gt;"], page.traceGpxImporte);
  assert.equal(page.controle().calques["<b>rando</b>"], undefined);
});

test("le bouton Réglages demande l'ouverture du dossier des journaux", async () => {
  const { elements, requetes } = charger();
  const ouverture = elements.get("ouvrirDossierJournaux").ecouteurs.click[0]();
  const requete = requetes.findLast((r) => r.url === "/api/ouvrir_journaux");
  assert.equal(requete.options.method, "POST");
  repondre(requete, { dossier: "C:\\journaux" });
  await ouverture;
  assert.equal(elements.get("ouvrirDossierJournaux").disabled, false);
  assert.equal(elements.get("erreurDossierJournaux").hidden, true);
});

// Chaque pays déclare ses capacités et leurs libellés dans son provider.
test("chaque fond et chaque calque des providers a son libellé FR et EN", () => {
  const { page } = charger();
  for (const [code, provider] of Object.entries(page.providers)) {
    if (code === "autre") continue;
    const fauxL = { tileLayer: Object.assign(() => ({}), { wms: () => ({}) }), CRS: { EPSG4326: {} } };
    const fonds = Object.keys(provider.bases({ L: fauxL, cleIgn: "cle", tuileIgn: () => "" }));
    assert.ok([...fonds, "osmRando", "osm", "satellite"].includes(provider.defaultBase),
      `${code} : fond par défaut ${provider.defaultBase} absent`);
    for (const langue of ["fr", "en"]) {
      assert.ok(provider.infoBase?.[langue], `${code} : fond du panneau ⓘ sans libellé ${langue}`);
      for (const fond of fonds) {
        assert.ok(provider.baseNames?.[fond]?.[langue],
          `${code} : libellé ${langue} « fond.${fond} » manquant`);
      }
      for (const calque of provider.overlays || []) {
        assert.ok(provider.overlayNames?.[calque]?.[langue],
          `${code} : calque du panneau ⓘ sans libellé ${langue}`);
      }
      if (provider.paths) assert.ok(provider.paths.name[langue]);
    }
  }
});

test("le rapport des pays présente fond, chemins et itinéraire depuis les providers", () => {
  const { page } = charger();
  const fr = couvertureCartographique(page.providers, "fr");
  assert.equal(fr.length, 11);
  assert.deepEqual(fr.map((p) => p.code).sort(),
    ["at", "ch", "cz", "de", "es", "fr", "lu", "nl", "no", "pl", "us"]);
  assert.match(fr.find((p) => p.code === "cz").chemins, /ZABAGED/);
  assert.equal(fr.find((p) => p.code === "cz").itineraire, "OSM + ZABAGED");
  assert.match(fr.find((p) => p.code === "ch").chemins, /swissTLM3D.*swisstopo/);
  assert.equal(fr.find((p) => p.code === "pl").itineraire, "OSM + BDOT10k");
  assert.equal(fr.find((p) => p.code === "at").chemins, "OSM");
  assert.equal(fr.find((p) => p.code === "es").itineraire, "OSM");
  const en = couvertureCartographique(page.providers, "en");
  assert.equal(en.find((p) => p.code === "pl").itineraire, "OSM + BDOT10k");
  assert.equal(en.find((p) => p.code === "us").fond, "USGS topographic map");
  assert.ok(fs.readFileSync(path.join(__dirname, "..", "RAPPORT_SOURCES_CHEMINS_BROUTER.md"), "utf8")
    .includes(sectionGeneree()), "le tableau du rapport doit être régénéré depuis les providers");
  assert.equal(fs.readFileSync(path.join(__dirname, "..", "COUNTRY_COVERAGE.md"), "utf8"), documentEnglish());
  assert.equal(lienCouverturePays("fr"), "/documentation/pays");
  assert.equal(lienCouverturePays("en"), "/documentation/pays?lang=en");
});

test("l'aide ouvre le README de la version installée, dans la langue de la page", () => {
  const { page, elements } = charger();
  page.etat.version = "0.3.3";
  page.appliquerLangue("fr");
  assert.equal(elements.get("aide").href, "https://github.com/nico579/hike2gpx/blob/v0.3.3/README.fr.md");
  assert.equal(elements.get("aide").title, "Aide : le mode d'emploi (README)");
  page.appliquerLangue("en");
  assert.equal(elements.get("aide").href, "https://github.com/nico579/hike2gpx/blob/v0.3.3/README.md");
  assert.equal(elements.get("aide")["aria-label"], "Help: the user guide (README)");
});

test("le panneau Réglages montre la version et vérifie les mises à jour", async () => {
  const { elements, requetes } = charger();
  repondre(requetes.findLast((r) => r.url === "/api/maj"), { version: "0.3.0", version_locale: "0.3.0" });
  await new Promise((fin) => setImmediate(fin));
  assert.equal(elements.get("versionApplication").textContent, "hike2gpx 0.3.0");
  assert.equal(elements.get("versionApplication").hidden, false);

  const verification = elements.get("verifierMaj").ecouteurs.click[0]();
  const requete = requetes.findLast((r) => r.url === "/api/maj-verifier");
  assert.equal(requete.options.method, "POST");
  assert.equal(elements.get("statutMaj").textContent, "Vérification…");
  repondre(requete, { ok: true, version: "0.3.10", version_locale: "0.3.9" });
  await verification;
  assert.equal(elements.get("statutMaj").textContent,
    "Version 0.3.10 disponible : le bandeau propose de l'installer.");
  assert.equal(elements.get("versionApplication").textContent, "hike2gpx 0.3.9");
  assert.equal(elements.get("verifierMaj").disabled, false);
});

test("la vérification des mises à jour dit « à jour » ou son échec", async () => {
  const { elements, requetes } = charger();
  let clic = elements.get("verifierMaj").ecouteurs.click[0]();
  repondre(requetes.findLast((r) => r.url === "/api/maj-verifier"), { ok: true, version: "0.3.1", version_locale: "0.3.1" });
  await clic;
  assert.equal(elements.get("statutMaj").textContent, "Vous avez la dernière version.");

  clic = elements.get("verifierMaj").ecouteurs.click[0]();
  repondre(requetes.findLast((r) => r.url === "/api/maj-verifier"), { ok: false, version: null, version_locale: "0.3.1" });
  await clic;
  assert.equal(elements.get("statutMaj").textContent, "Vérification impossible (réseau ?).");
  assert.equal(elements.get("verifierMaj").disabled, false);
});

test("le parcours revient après rechargement et se recalcule", async () => {
  const avant = charger();
  avant.page.ajouterPoint({ lat: 43.3, lng: 6 });
  avant.page.ajouterPoint({ lat: 43.31, lng: 6.02 });
  assert.equal(avant.stockage.get("hike2gpx.points"), "[[43.3,6],[43.31,6.02]]");

  const apres = charger(Object.fromEntries(avant.stockage));
  assert.equal(JSON.stringify(apres.page.etat.points.map((p) => [p.lat, p.lon])),
    "[[43.3,6],[43.31,6.02]]");
  assert.equal(apres.elements.get("exporter").disabled, true);
  const minuterie = apres.minuteurs.findLast((m) => m.ms === 250 && !m.annule);
  assert.ok(minuterie, "le calcul est relancé après la restauration");
  const calcul = minuterie.callback();
  assert.deepEqual(JSON.parse(apres.derniere().options.body).points, [[43.3, 6], [43.31, 6.02]]);
  repondre(apres.derniere(), resultat(6.02));
  await calcul;
  assert.equal(apres.elements.get("exporter").disabled, false);
});

test("le voyant suit les données du prochain calcul, pas le tracé affiché", async () => {
  const { page, elements, derniere, minuteurs } = charger();
  page.afficherDisponibilite({ pret: false, source: null, attente: "zone_absente" });
  assert.equal(elements.get("readinessText").textContent, "Tracé indisponible");
  page.ajouterPoint({ lat: 43.3, lng: 6 });
  page.ajouterPoint({ lat: 43.31, lng: 6.02 });
  const calcul = minuteurs.findLast((m) => m.ms === 250 && !m.annule).callback();
  repondre(derniere(), resultat(6.02));
  await calcul;
  page.afficherDisponibilite({ pret: false, source: null, attente: "zone_absente" });
  assert.equal(elements.get("readinessText").textContent, "Tracé indisponible");
  // Nico, 2026-11-13 : « le message n'est pas à jour ». La zone de routage et BRouter,
  // sans plus d'Overpass ni d'extraits OSM.
  page.afficherDisponibilite({ pret: true, source: "lot", nom: "E5_N40",
    details: { lot: { nom: "E5_N40", etat: "simple" } } });
  assert.equal(elements.get("readinessText").textContent, "Tracé disponible");
  assert.equal(elements.get("readiness").classList.contains("available"), true);
  assert.equal(elements.get("readinessInfoText").textContent, "Sources du prochain calcul\n"
    + "Zone de routage (E5_N40) : simple (sans chemins dessinés ni franchissements)\nBRouter : prêt");
  page.appliquerLangue("en");
  assert.equal(elements.get("readinessText").textContent, "Routing available");
  assert.match(elements.get("readinessInfoText").textContent, /Routing area \(E5_N40\) : simple/);
  page.ajouterPoint({ lat: 43.32, lng: 6.03 });
  assert.equal(elements.get("readinessText").textContent, "Routing unavailable");
});

test("déplacer, retirer et effacer mettent à jour le parcours sauvegardé", () => {
  const { page, elements, stockage } = charger();
  page.ajouterPoint({ lat: 43.3, lng: 6 });
  page.ajouterPoint({ lat: 43.31, lng: 6.02 });
  page.etat.points[1].marqueur.position = { lat: 43.32, lng: 6.03 };
  page.etat.points[1].marqueur.handlers.dragend();
  assert.equal(stockage.get("hike2gpx.points"), "[[43.3,6],[43.32,6.03]]");
  elements.get("retirerDernier").ecouteurs.click[0]();
  assert.equal(stockage.get("hike2gpx.points"), "[[43.3,6]]");
  elements.get("toutEffacer").ecouteurs.click[0]();
  assert.equal(stockage.get("hike2gpx.points"), "[]");
  assert.equal(charger(Object.fromEntries(stockage)).page.etat.points.length, 0);
});

test("une sauvegarde de points invalide est ignorée", () => {
  for (const valeur of ["{", "[[91,6]]", "[[43.3,6],[null,6]]"]) {
    assert.equal(charger({ "hike2gpx.points": valeur }).page.etat.points.length, 0);
  }
});

test("rechercher une ville recentre la carte sans ajouter de point", async () => {
  const { elements, requetes, carte, page } = charger();
  elements.get("cityQuery").value = "Grenoble";
  const recherche = elements.get("citySearch").ecouteurs.submit[0]({ preventDefault() {} });
  const requete = requetes.find((r) => r.url === "/api/communes");
  assert.equal(JSON.parse(requete.options.body).recherche, "Grenoble");
  repondre(requete, { communes: [{ nom: "Grenoble", detail: "Isère", code_pays: "fr", lat: 45.1842, lon: 5.7155 }] });
  await recherche;
  assert.equal(JSON.stringify(carte.center), "[45.1842,5.7155]");
  assert.equal(carte.viewZoom, 13);
  assert.equal(page.etat.points.length, 0);
});

test("la recherche accepte des coordonnées GPS sans appeler la recherche de ville", () => {
  const { elements, requetes, carte, page } = charger();
  for (const entree of ["50.725, 10.275", "50.725,10.275", "50,725 ; 10,275", "50.725 10.275"]) {
    elements.get("cityQuery").value = entree;
    elements.get("citySearch").ecouteurs.submit[0]({ preventDefault() {} });
    assert.equal(JSON.stringify(carte.center), "[50.725,10.275]");
    assert.equal(carte.viewZoom, 14);
  }
  assert.equal(requetes.filter((r) => r.url === "/api/communes").length, 0);
  assert.equal(page.etat.points.length, 0);
});

test("Madrid active IGN Espagne et ses sentiers, puis les couches IGN reviennent en France", async () => {
  const { page, elements, requetes, stockage, carte } = charger();
  page.etat.cleIgn = "cle-test";
  page.construireFonds();
  assert.deepEqual(Object.keys(page.fonds()), ["scan25", "plan", "photos", "reliefLidar", "osmRando", "osm", "satellite"]);
  assert.ok(page.controle().fonds["Relief LiDAR HD (IGN)"]);
  assert.match(page.fonds().reliefLidar.url, /IGNF_LIDAR-HD_MNT_ELEVATION\.ELEVATIONGRIDCOVERAGE\.SHADOW/);
  assert.match(page.fonds().reliefLidar.url, /TILEMATRIXSET=PM_0_18/);
  assert.equal(page.fonds().reliefLidar.options.maxNativeZoom, 18);
  carte.handlers.baselayerchange({ layer: page.fonds().reliefLidar });
  assert.equal(stockage.get("hike2gpx.fond.fr"), "reliefLidar");

  elements.get("cityQuery").value = "Madrid";
  const rechercheMadrid = elements.get("citySearch").ecouteurs.submit[0]({ preventDefault() {} });
  repondre(requetes.findLast((r) => r.url === "/api/communes"), { communes: [
    { nom: "Madrid", detail: "Espagne", code_pays: "es", lat: 40.416782, lon: -3.703507 },
  ] });
  await rechercheMadrid;
  assert.deepEqual(Object.keys(page.fonds()), ["espagne", "osmRando", "osm", "satellite"]);
  assert.deepEqual(Object.keys(page.controle().fonds), ["Carte topographique (IGN Espagne)", "OSM rando", "OSM", "Satellite"]);
  assert.match(page.fonds().osmRando.url, /tile\.opentopomap\.org/);
  assert.match(page.fonds().satellite.url, /World_Imagery/);
  assert.deepEqual(Object.keys(page.controle().calques), ["OSM", "Sentiers balisés GR/PR/SL (IGN Espagne)"]);
  assert.equal(page.fonds().reliefLidar, undefined);
  assert.match(page.fond().url, /ign\.es\/wmts\/mapa-raster/);
  assert.equal(page.CALQUES.bdtopo.groupe.removed, true);
  assert.equal(elements.get("ignOption").hidden, false);
  assert.equal(elements.get("ign").disabled, true);
  assert.match(elements.get("ignOptionTexte").textContent, /affichage seul/);
  assert.equal(ligneLegende(elements, "chemins_officiels").hidden, true, "Madrid : calques espagnols d affichage seul, pas de ligne officielle");
  assert.equal(JSON.parse(stockage.get("hike2gpx.vue")).hors_france, true);

  const recharge = charger(Object.fromEntries(stockage));
  recharge.page.restaurerCalques();
  recharge.page.construireFonds();
  assert.deepEqual(Object.keys(recharge.page.fonds()), ["espagne", "osmRando", "osm", "satellite"]);
  assert.equal(recharge.page.CALQUES.bdtopo.groupe.addedTo, undefined);
  assert.equal(recharge.page.fonds().reliefLidar, undefined);
  assert.equal(recharge.elements.get("ignOption").hidden, false);
  assert.equal(recharge.elements.get("ign").disabled, true);
  recharge.carte.handlers.baselayerchange({ layer: recharge.page.fonds().satellite });
  const rechargeSatellite = charger(Object.fromEntries(recharge.stockage));
  rechargeSatellite.page.construireFonds();
  assert.equal(rechargeSatellite.page.fond(), rechargeSatellite.page.fonds().satellite);

  elements.get("cityQuery").value = "Grenoble";
  const rechercheGrenoble = elements.get("citySearch").ecouteurs.submit[0]({ preventDefault() {} });
  repondre(requetes.findLast((r) => r.url === "/api/communes"), { communes: [
    { nom: "Grenoble", detail: "Isère", code_pays: "fr", lat: 45.1842, lon: 5.7155 },
  ] });
  await rechercheGrenoble;
  assert.deepEqual(Object.keys(page.fonds()), ["scan25", "plan", "photos", "reliefLidar", "osmRando", "osm", "satellite"]);
  assert.equal(Object.keys(page.controle().calques).length, 2);
  assert.equal(page.fond(), page.fonds().reliefLidar);
  assert.equal(elements.get("ignOption").hidden, false);
  assert.equal(elements.get("ign").disabled, false);
  assert.equal(elements.get("ignOptionTexte").textContent, "Inclure les chemins IGN", "le texte d'Android");
  assert.equal(JSON.parse(stockage.get("hike2gpx.vue")).hors_france, false);
  const rechargeFrance = charger(Object.fromEntries(stockage));
  rechargeFrance.page.construireFonds();
  assert.equal(rechargeFrance.page.fond(), rechargeFrance.page.fonds().reliefLidar);
});

test("un déplacement manuel de Madrid à Garéoult rétablit les couches IGN", async () => {
  const { page, elements, requetes, carte, minuteurs } = charger();
  elements.get("cityQuery").value = "Madrid";
  const recherche = elements.get("citySearch").ecouteurs.submit[0]({ preventDefault() {} });
  repondre(requetes.findLast((r) => r.url === "/api/communes"), { communes: [
    { nom: "Madrid", code_pays: "es", lat: 40.416782, lon: -3.703507 },
  ] });
  await recherche;
  assert.equal(page.fonds().plan, undefined);

  carte.vue = { s: 43.30, w: 5.98, n: 43.35, e: 6.04 };
  carte.handlers.moveend();
  const lecture = minuteurs.findLast((m) => m.ms === 600 && !m.annule).callback();
  repondre(requetes.findLast((r) => r.url.startsWith("/api/extrait?")),
    { en_cours: null, brouter: null, pays: "fr", hors_france: false });
  await lecture;
  assert.ok(page.fonds().plan);
  assert.equal(elements.get("ignOption").hidden, false);

  carte.vue = { s: 40.40, w: -3.73, n: 40.43, e: -3.68 };
  carte.handlers.moveend();
  const retour = minuteurs.findLast((m) => m.ms === 600 && !m.annule).callback();
  repondre(requetes.findLast((r) => r.url.startsWith("/api/extrait?")),
    { en_cours: null, brouter: null, pays: "es", hors_france: true });
  await retour;
  assert.equal(page.fonds().plan, undefined);
  assert.ok(page.fonds().espagne);
  assert.ok(page.controle().calques["Sentiers balisés GR/PR/SL (IGN Espagne)"]);
});

test("la Suisse active swisstopo et conserve un fond préféré par pays", () => {
  const { page, carte, stockage } = charger();
  page.choisirPays("ch");
  assert.match(page.fond().url, /ch\.swisstopo\.pixelkarte-farbe/);
  assert.match(page.controle().calques["Sentiers de randonnée (swisstopo)"].url,
    /ch\.swisstopo\.swisstlm3d-wanderwege/);
  assert.equal(page.fonds().plan, undefined);
  carte.handlers.baselayerchange({ layer: page.fonds().osm });
  assert.equal(stockage.get("hike2gpx.fond.ch"), "osm");
  page.choisirPays("es");
  assert.match(page.fond().url, /ign\.es\/wmts\/mapa-raster/);
  page.choisirPays("ch");
  assert.match(page.fond().url, /tile\.openstreetmap\.org/);
});

test("Autriche et Pays-Bas affichent leur fond officiel et seulement les chemins disponibles", () => {
  const { page, elements } = charger();
  page.choisirPays("at");
  assert.match(page.fond().url, /mapsneu\.wien\.gv\.at\/basemap/);
  assert.deepEqual(Object.keys(page.controle().calques), ["OSM"]);
  assert.equal(elements.get("ignOption").hidden, true);
  page.choisirPays("nl");
  assert.match(page.fond().url, /service\.pdok\.nl\/kadaster\/brt-achtergrondkaart/);
  assert.deepEqual(Object.keys(page.controle().calques), ["OSM"]);
  assert.equal(elements.get("ignOption").hidden, true);
});

test("l'Allemagne propose TopPlusOpen et le calque ATKIS par zone", async () => {
  const { page, elements, carte, requetes } = charger();
  page.choisirPays("de");
  assert.match(page.fond().url, /sgx\.geodatenzentrum\.de\/wmts_topplus_open\/tile\/1\.0\.0\/web\/default\/WEBMERCATOR\/\{z\}\/\{y\}\/\{x\}\.png/);
  assert.match(page.fond().options.attribution, /BKG.*dl-de\/by-2-0.*Datenquellen/);
  assert.deepEqual(Object.keys(page.controle().calques),
    ["OSM", "ATKIS"]);
  assert.match(page.CALQUES.atkis.groupe.getAttribution(), /GeoBasis-DE.*GDI-Th.*BVV.*CC BY 4\.0/);
  assert.equal(ligneLegende(elements, "chemins_officiels").hidden, true, "calque ATKIS non coché : pas de ligne");
  page.coucheCalque("atkis").addTo(carte);
  page.coucheCalque("atkis").getLayers = () => page.coucheCalque("atkis").layers;
  page.majLegende();
  assert.equal(ligneLegende(elements, "chemins_officiels").hidden, true, "coché mais rien de dessiné (zoom) : pas de ligne");
  page.coucheCalque("atkis").layers.push({ options: {} });
  page.majLegende();
  assert.equal(ligneLegende(elements, "chemins_officiels").hidden, false);
  assert.equal(elements.get("legendOfficielTexte").textContent, "chemin ATKIS");
  assert.equal(elements.get("ignOption").hidden, false);
  assert.equal(elements.get("ign").disabled, false);
  page.CALQUES.atkis.groupe.addTo(carte);
  carte.hasLayer = (layer) => layer === page.CALQUES.atkis.groupe;
  const lecture = page.rafraichirCalques();
  const requete = requetes.find((r) => r.url.startsWith("/api/atkis?"));
  assert.ok(requete);
  repondre(requete, { troncons: [{ id: "TH:test", land: "TH", nature: "Wirtschaftsweg",
    pts: [[50.717, 10.25], [50.718, 10.251]] }], bornes: [50.7, 10.2, 50.75, 10.3] });
  await lecture;
  assert.equal(page.CALQUES.atkis.groupe.layers.length, 1);
});

test("les nouveaux providers transmettent leur source au calcul, la BDOT10k dans toute la Pologne", async () => {
  for (const [pays, source, centre] of [
    ["cz", "zabaged", [49.125, 13.475]],
    ["ch", "swisstlm3d", [46.225, 8.625]],
    ["pl", "bdot10k_ds", [50.65, 16.48]],
  ]) {
    const { page, carte, elements, derniere } = charger();
    carte.vue = { s: centre[0] - 0.005, w: centre[1] - 0.005,
      n: centre[0] + 0.005, e: centre[1] + 0.005 };
    page.choisirPays(pays);
    if (pays === "pl") {
      assert.match(page.fond().url, /geoportal\.gov\.pl\/wss\/service\/img\/guest\/TOPO/);
      assert.equal(page.fond().options.layers, "Raster");
      assert.equal(page.fond().options.crs.code, "EPSG:4326");
    }
    assert.ok(page.controle().calques[page.providers[pays].paths.label], "la coche porte le nom court");
    assert.equal(elements.get("ign").disabled, false);
    page.etat.points = [{ lat: centre[0], lon: centre[1] },
      { lat: centre[0] + 0.001, lon: centre[1] + 0.001 }];
    const calcul = page.calculer();
    const requete = derniere();
    assert.equal(JSON.parse(requete.options.body).source, source);
    repondre(requete, { erreur: "fin de l'essai" });
    await calcul;
    if (pays === "pl") {
      // Poznań, hors de Basse-Silésie : la BDOT10k couvre toute la Pologne
      // depuis le 2026-11-09, l'option reste active.
      carte.vue = { s: 52.0, w: 16.0, n: 52.01, e: 16.01 };
      carte.handlers.moveend();
      assert.equal(elements.get("ign").disabled, false);
    }
  }
});

test("les États-Unis proposent le fond USGS et ses sentiers agrégés", () => {
  const { page, elements } = charger();
  page.choisirPays("us");
  assert.match(page.fond().url, /basemap\.nationalmap\.gov.*USGSTopo/);
  assert.ok(page.controle().calques["Sentiers recensés par l’USGS"]);
  assert.equal(elements.get("ignOption").hidden, false);
  assert.equal(elements.get("ign").disabled, true);
  assert.match(elements.get("ignOptionTexte").textContent, /USGS.*affichage seul/);
});

test("durée de marche et points extrêmes attendent puis reprennent gpx2elev", async () => {
  const { page, elements, derniere, requetes } = charger();
  page.etat.points = [{ lat: 43.3, lon: 6 }, { lat: 43.3, lon: 6.01 }];
  const calcul = page.calculer();
  const trajet = resultat(6.01);
  trajet.longueur_m = 10000;
  repondre(derniere(), trajet);
  await calcul;
  assert.equal(elements.get("duree").textContent, "…");
  const relief = requetes.find((r) => r.url === "/api/denivele");
  repondre(relief, { montee_m: 120, descente_m: 90, altitude_min_m: 400, altitude_max_m: 700,
    modele: "Mapterhorn", duree_marche_s: 8100 });
  await new Promise(setImmediate);
  assert.equal(elements.get("duree").textContent, "2 h 15");
  assert.equal(elements.get("pointHaut").textContent, "700 m");
  assert.equal(elements.get("pointBas").textContent, "400 m");
assert.equal(elements.get("denivele").textContent, "+ 120 m / − 90 m");
assert.match(elements.get("sourceDenivele").textContent, /Source des altitudes du parcours : Mapterhorn/);
});

test("les flèches suivent le sens du tracé et disparaissent au zoom éloigné", () => {
  const { page, carte } = charger();
  const est = page.preparerFleches([[6, 43], [6.01, 43]]);
  const ouest = page.preparerFleches([[6.01, 43], [6, 43]]);
  assert.ok(est.length > 0);
  assert.ok(Math.abs(est[0].angle) < 1);
  assert.ok(Math.abs(ouest[0].angle) > 179);
  page.setFleches(est);
  page.afficherFleches();
  assert.equal(page.fleches.layers.length, est.length);
  assert.ok(page.fleches.layers.every((fleche) => fleche.options.pane === "sensTrace"));
  carte.zoom = 11;
  carte.handlers.zoomend();
  assert.equal(page.fleches.layers.length, 0);
});

test("une ouverture vérifie les tuiles BRouter même si le moteur est déjà installé", async () => {
  const { requetes } = charger();
  repondre(requetes.find((r) => r.url === "/api/etat"),
    { version: "0.1.0", brouter: "1.7.10", moteur_installe: true });
  repondre(requetes.find((r) => r.url === "/api/reglages"),
    { cle_ign: "", renouvellement_jours: 30 });
  await new Promise(setImmediate);
  assert.ok(requetes.some((r) => r.url === "/api/moteur"));
});

test("les deux calques sont cochés par défaut, sans écraser un choix mémorisé", () => {
  function cochés(preferences) {
    const { page } = charger(preferences);
    const vus = [];
    for (const [nom, calque] of Object.entries(page.CALQUES)) {
      calque.groupe.addTo = () => vus.push(nom);
    }
    page.restaurerCalques();
    return vus;
  }
  assert.deepEqual(cochés({}), ["osm", "bdtopo"]);
  assert.deepEqual(cochés({ "hike2gpx.calques": "[]" }), []);
  assert.deepEqual(cochés({ "hike2gpx.calques": '["osm"]' }), ["osm"]);
});

test("les options de marche et le fond reviennent à l'ouverture", () => {
  assert.equal(charger().elements.get("strict").checked, true);
  assert.equal(charger({ "hike2gpx.options": JSON.stringify({ strict: false }) })
    .elements.get("strict").checked, false);
  const { page, elements, stockage, carte } = charger({
    "hike2gpx.options": JSON.stringify({ strict: true, ign: false, comparer: false }),
    "hike2gpx.fond": "osm",
  });
  assert.equal(elements.get("strict").checked, true);
  assert.equal(elements.get("ign").checked, false);
  assert.equal(elements.get("comparer").checked, false);
  page.construireFonds();
  assert.match(page.fond().url, /tile\.openstreetmap\.org/);
  elements.get("comparer").checked = true;
  elements.get("comparer").ecouteurs.change[0]();
  assert.deepEqual(JSON.parse(stockage.get("hike2gpx.options")), { strict: true, ign: false, comparer: true });
  carte.handlers.baselayerchange({ layer: page.fonds().plan });
  assert.equal(stockage.get("hike2gpx.fond.fr"), "plan");
  carte.zoom = 19;
  carte.handlers.zoomend();
  assert.equal(elements.get("carte").style["--tile-overlap"], "1px");
});

async function calculReussi(page, derniere) {
  page.etat.points = [{ lat: 43.3, lon: 6 }, { lat: 43.3, lon: 6.01 }];
  const calcul = page.calculer();
  repondre(derniere(), resultat(6.01));
  await calcul;
}

test("modifier un point retire aussitôt l'ancien tracé de l'export", async () => {
  const { page, elements, derniere } = charger();
  await calculReussi(page, derniere);
  assert.equal(elements.get("exporter").disabled, false);
  page.etat.points[1].lon = 6.02;
  page.planifierCalcul();
  assert.equal(page.etat.dernier, null);
  assert.equal(elements.get("exporter").disabled, true);
});

test("un recalcul en échec ne laisse pas exporter l'ancien tracé", async () => {
  const { page, elements, derniere } = charger();
  await calculReussi(page, derniere);
  const calcul = page.calculer();
  derniere().reject(new Error("panne réseau simulée"));
  await calcul;
  assert.equal(page.etat.dernier, null);
  assert.equal(elements.get("exporter").disabled, true);
});

test("une réponse arrivée après une modification est ignorée", async () => {
  const { page, elements, derniere } = charger();
  page.etat.points = [{ lat: 43.3, lon: 6 }, { lat: 43.3, lon: 6.01 }];
  const calcul = page.calculer();
  page.etat.points = [];
  page.planifierCalcul();         // la minuterie de 250 ms n'a pas encore tourné
  repondre(derniere(), resultat(6.01));
  await calcul;
  assert.equal(page.etat.dernier, null);
  assert.equal(elements.get("exporter").disabled, true);
});

test("un clic sur une zone stockée recentre la carte, et choisit sa carte pour une zone de carte", async () => {
  const { page, elements, requetes, carte } = charger();
  page.etat.fondsHorsLigne = { scan25: "SCAN 25 (IGN)", plan: "Plan IGN", osm: "OpenStreetMap" };
  page.construireFonds();
  assert.equal(page.fond(), page.fonds().plan, "le Plan IGN au départ");
  // Gestion des cartes : la zone OSM de N43E006, recentrée et affichée en OSM.
  const charge = page.chargerFonds();
  repondre(requetes.findLast((r) => r.url === "/api/hors_ligne"), { lots: [], fonds: [
    { nom: "N43E006-osm", zone: [43, 6, 44, 7], zoom: [0, 21], source: "osm", format: "map", octets: 48e6 }] });
  await charge;
  const [ligneCarte] = elements.get("zonesCartes").enfants;
  assert.equal(ligneCarte.enfants[0].title, "Centrer la carte sur cette zone");
  ligneCarte.enfants[0].click();
  assert.equal(JSON.stringify(carte.fit.bounds), "[[43,6],[44,7]]");
  assert.equal(page.fond(), page.fonds().osm, "la carte de la zone");
  // Gestion des itinéraires : la case de 5°, recentrée.
  elements.get("pane-itineraires").hidden = false;
  page.chargerLots();
  repondre(requetes.findLast((r) => r.url === "/api/hors_ligne"),
    { lots: [{ case: "E5_N40", type: "enrichi", sources: { osm: {}, bdtopo: {} }, octets: 248e6 }], fonds: [] });
  await tic();
  elements.get("zonesLocales").enfants[0].enfants[0].click();
  assert.equal(JSON.stringify(carte.fit.bounds), "[[40,5],[45,10]]");
});

test("« Gestion des cartes » liste ses zones stockées localement, toutes cartes confondues", async () => {
  const { page, elements, requetes, confirmations } = charger();
  page.etat.fondsHorsLigne = { scan25: "SCAN 25 (IGN)", plan: "Plan IGN", osm: "OpenStreetMap" };
  const charge = page.chargerFonds();
  repondre(requetes.findLast((r) => r.url === "/api/hors_ligne"), { lots: [], fonds: [
    { nom: "N43E006-scan25", zone: [43, 6, 44, 7], zoom: [13, 16], source: "scan25", octets: 830e6 },
    { nom: "N43E006-osm", zone: [43, 6, 44, 7], zoom: [0, 21], source: "osm", format: "map", octets: 48e6 }] });
  await charge;
  const lignes = elements.get("zonesCartes").enfants;
  assert.deepEqual(lignes.map((l) => l.enfants[0].textContent),
    ["N43E006 · OpenStreetMap · 48 Mo", "N43E006 · SCAN 25 (IGN) · 830 Mo"], "la zone, sa carte et sa taille");
  // Supprimer : la zone de cette carte seule, après une confirmation qui nomme les deux.
  confirmations.reponse = true;
  lignes[1].enfants[1].click();
  await tic();
  assert.match(confirmations.at(-1), /^Supprimer de ce PC la zone N43E006 de la carte SCAN 25 \(IGN\) \(830 Mo\)/);
  assert.deepEqual(JSON.parse(requetes.findLast((r) => r.url === "/api/supprimer_fond").options.body),
    { carre: "N43E006", source: "scan25" });
  repondre(requetes.findLast((r) => r.url === "/api/supprimer_fond"), { octets: 830e6 });
  await tic();
  repondre(requetes.findLast((r) => r.url === "/api/hors_ligne"), { lots: [], fonds: [] });
  await tic();
  assert.equal(elements.get("zonesCartes").enfants[0].textContent, "Aucune zone de carte sur ce PC.");
});

test("« Zones stockées localement » liste les lots installés, comme le téléphone", async () => {
  const { page, elements, requetes, confirmations } = charger();
  elements.get("pane-itineraires").hidden = false;          // la page ouverte
  page.chargerLots();
  repondre(requetes.findLast((r) => r.url === "/api/hors_ligne"),
    { lots: [{ case: "E5_N40", type: "enrichi", sources: { osm: {}, bdtopo: {}, relief: {} }, octets: 248e6 }],
      fonds: [] });
  await tic();
  repondre(requetes.findLast((r) => r.url === "/api/catalogue_lots"), { lots: [{ case: "E5_N40", etat: "ancien" }] });
  await tic();
  const [ligne] = elements.get("zonesLocales").enfants;
  const [texte, maj, supprimer] = ligne.enfants;
  assert.equal(texte.textContent, "E5_N40 · enrichi IGN · 248 Mo");
  assert.equal(maj.textContent, "Mettre à jour", "le serveur en publie un plus récent");
  assert.equal(supprimer.enfants[1].textContent, "Supprimer", "un bouton à icône : pictogramme, puis texte");
  assert.match(supprimer.className, /zone-supprimer/, "le bouton rouge du volet");
  // Supprimer : après confirmation, le routage seul, pas les fonds du carré.
  confirmations.reponse = true;
  supprimer.click();
  await tic();
  assert.match(confirmations.at(-1), /^Supprimer de ce PC la zone E5_N40 \(248 Mo\)/);
  assert.deepEqual(JSON.parse(requetes.findLast((r) => r.url === "/api/supprimer_case").options.body),
    { case: "E5_N40", fonds: false });
  // Sans lot installé, la page le dit.
  repondre(requetes.findLast((r) => r.url === "/api/supprimer_case"), { octets: 248e6 });
  await tic();
  repondre(requetes.findLast((r) => r.url === "/api/hors_ligne"), { lots: [], fonds: [] });
  await tic();
  assert.equal(elements.get("zonesLocales").enfants[0].textContent, "Aucune zone de routage installée.");
});

test("une recherche aboutie referme le champ, comme sur le téléphone", () => {
  const { elements, evenements } = charger();
  elements.get("cityQuery").value = "43.3, 6.04";
  elements.get("citySearch").ecouteurs.submit[0]({ preventDefault() {} });
  assert.ok(evenements.includes("hike2gpx:recherche-aboutie"), "presentation.js referme le champ");
});

test("un clic sur la carte ne pose un point qu'en planification, comme sur le téléphone", () => {
  const { page, carte, corps } = charger();
  carte.handlers.click({ latlng: { lat: 43.3, lng: 6 } });
  assert.equal(page.etat.points.length, 0, "carte consultée : le clic ne pose rien");
  page.planifier(true);
  assert.equal(corps.classList.contains("planification"), true, "le curseur en croix");
  carte.handlers.click({ latlng: { lat: 43.3, lng: 6 } });
  assert.equal(page.etat.points.length, 1);
  // La page refermée : le point reste, un nouveau clic ne pose plus rien.
  page.planifier(false);
  carte.handlers.click({ latlng: { lat: 43.31, lng: 6.01 } });
  assert.equal(page.etat.points.length, 1);
  // Le tracé reste, mais ses points ne se déplacent plus et n'ont plus de bulle « Retirer ».
  const marqueur = page.etat.points[0].marqueur;
  assert.equal(marqueur.dragging.actif, false, "hors planification : pas de glissement");
  assert.equal(marqueur.popupLie, false, "hors planification : pas de bulle");
  page.planifier(true);
  assert.equal(marqueur.dragging.actif, true, "planification reprise : le point se déplace");
  assert.equal(marqueur.popupLie, true);
});

test("un clic sur la carte le dit à la page, que la planification soit active ou non", () => {
  const { carte, evenements } = charger();
  const avant = evenements.filter((t) => t === "hike2gpx:carte-cliquee").length;
  carte.handlers.click({ latlng: { lat: 43.3, lng: 6 } });
  assert.equal(evenements.filter((t) => t === "hike2gpx:carte-cliquee").length, avant + 1,
    "presentation.js en profite pour refermer la recherche de ville");
});

test("revenir au départ ferme la boucle, une seule fois", () => {
  const { page, elements } = charger();
  page.ajouterPoint({ lat: 43.3, lng: 6 });
  assert.equal(elements.get("boucler").disabled, true);      // un seul point : rien à boucler
  page.ajouterPoint({ lat: 43.31, lng: 6.01 });
  assert.equal(elements.get("boucler").disabled, false);
  page.boucler();
  // Tableaux nés dans le contexte de la page : comparés par leur JSON.
  assert.equal(JSON.stringify(page.etat.points.map((p) => [p.lat, p.lon])), "[[43.3,6],[43.31,6.01],[43.3,6]]");
  assert.equal(elements.get("boucler").disabled, true);      // déjà revenu au départ
  page.boucler();
  assert.equal(page.etat.points.length, 3);
});

test("pointeur d'attente et barre de progression le temps du calcul", async () => {
  const { page, elements, derniere, corps } = charger();
  page.etat.points = [{ lat: 43.3, lon: 6 }, { lat: 43.3, lon: 6.01 }];
  const calcul = page.calculer();
  assert.equal(corps.classList.contains("calcul"), true);
  assert.equal(elements.get("progression").hidden, false);
  assert.match(elements.get("progressionTexte").textContent, /Préparation/);
  repondre(derniere(), resultat(6.01));
  await calcul;
  assert.equal(corps.classList.contains("calcul"), false);
  assert.equal(elements.get("progression").hidden, true);
});

test("en anglais, la page traduit ses textes et les erreurs du serveur", async () => {
  const { page, elements, document, derniere } = charger();
  page.appliquerLangue("en");
  assert.equal(document.title, "hike2gpx — plan a route");
  assert.equal(elements.get("entree-trace").textContent, "Plan a route");
  assert.equal(elements.get("entree-reglages").textContent, "Settings");
  assert.equal(elements.get("menuPrincipal")["aria-label"], "Menu");
  assert.match(page.ts("Chemin ATKIS absent d'OpenStreetMap : existence et accès à vérifier"), /ATKIS path missing/);
  assert.match(page.ts("Chemin IGN absent d'OpenStreetMap : existence et accès à vérifier"), /^IGN path missing/);
  assert.match(page.ts("Chemin swissTLM3D absent d'OpenStreetMap : existence et accès à vérifier"), /^swissTLM3D path missing/);
  page.ajouterPoint({ lat: 43.3, lng: 6 });
  await page.calculer();
  assert.equal(elements.get("statut").textContent, "Place a second point.");
  const refus = { erreur: "Itinéraire refusé : …", code: "itineraire_refuse",
    valeurs: { nature: "Clôture", statut: "blocked", distance_m: 1500 } };
  assert.equal(page.texteErreur(refus), "Route refused: it passes a blocking crossing (Fence, 1.50 km from the start).");
  assert.equal(page.texteErreur({ erreur: "Calcul trop long : rapprochez les points." }),
    "Calculation too long: bring the points closer.");
  page.appliquerLangue("fr");
  assert.equal(document.title, "hike2gpx — tracer un parcours");
  assert.equal(elements.get("entree-trace").textContent, "Planifier un itinéraire");
  assert.equal(elements.get("entree-reglages").textContent, "Réglages");
  assert.equal(elements.get("statut").textContent, "Posez un deuxième point.");
});

test("plein écran : la carte seule, puis la page revient", () => {
  const { page, corps } = charger();
  page.basculerPleinEcran();
  assert.equal(corps.classList.contains("plein-ecran"), true);
  page.basculerPleinEcran();
  assert.equal(corps.classList.contains("plein-ecran"), false);
});

test("le calque OSM montre clôtures et franchissements sans itinéraire", async () => {
  const { page, carte, requetes } = charger();
  carte.hasLayer = (layer) => layer === page.CALQUES.osm.groupe;
  const lecture = page.rafraichirCalques();
  const osm = requetes.find((r) => r.url.startsWith("/api/osm?"));
  repondre(osm, { voies: [], barrieres: [{ id: 7, nature: "Clôture", pts: [[43.3, 6], [43.31, 6]] }],
    franchissements: [
      { cle: "noeud-8", statut: "uncertain", raison: "Franchissement à vérifier sur place",
        nature: "Portail", lat: 43.3, lon: 6.01, osm: "node/8" },
      { cle: "ligne-7", statut: "blocked", raison: "Accès interdit ou privé",
        nature: "Clôture", lat: 43.31, lon: 6.01, osm: "way/7" },
    ],
    // Un chemin qui s'arrête à 5 m d'une route sans la toucher.
    jonctions: [{ cle: "jonction-2-21", lat: 43.32, lon: 6.02, voie: 2, vers: 1, distance_m: 5.1, osm: "way/2" }],
    bornes: [43.3, 6, 43.35, 6.05] });
  await lecture;
  assert.equal(page.etat.points.length, 0);
  assert.equal(page.etat.dernier, null);
  const couches = page.CALQUES.osm.groupe.layers;
  assert.equal(couches.length, 4);
  assert.equal(couches[0].options.color, "#e53935");
  assert.deepEqual(couches.slice(1).map((c) => c.options.fillColor), ["#ef6c00", "#d32f2f", "#fdd835"],
    "le chemin non raccordé en jaune, à part des franchissements");
  assert.ok(couches.slice(1).every((c) => c.options.pane === "obstaclesOsm"));
  // Puis une vue sans zone de routage : la carte de fond seule, sans les chemins d'avant
  // (Nico, 2026-11-13, à Montréal : « Supprimer » l'affichage à la volée).
  page.CALQUES.osm.charge = null;
  const ailleurs = page.rafraichirCalques();
  repondre(requetes.findLast((r) => r.url.startsWith("/api/osm?")),
    { erreur: "Pas de zone de routage ici : les chemins s'afficheront avec elle (« Planifier un itinéraire »).",
      code: "calques_sans_zone" });
  await ailleurs;
  assert.equal(page.CALQUES.osm.groupe.layers.length, 0);
  assert.equal(page.CALQUES.osm.charge, null, "redemandé à la vue suivante");
});

test("calques : la vue seule, une vue quittée coupée, rien de relu dans les tuiles déjà lues", async () => {
  // Journal du 2026-10-19 : chaque déplacement ajoutait ses lectures à celles
  // des vues quittées, et la vue demandée était élargie de 15 %.
  const { page, requetes, carte } = charger();
  carte.hasLayer = (layer) => layer === page.CALQUES.osm.groupe || layer === page.CALQUES.bdtopo.groupe;
  const calques = () => requetes.filter((r) => /^\/api\/(osm|bdtopo)\?/.test(r.url));
  const premiere = page.rafraichirCalques();
  const [osmA, bdtopoA] = calques();
  assert.match(osmA.url, /^\/api\/osm\?s=43\.31000&w=6\.01000&n=43\.33000&e=6\.04000&vue=\d+\.\d{3}$/);
  carte.vue = { s: 43.41, w: 6.21, n: 43.43, e: 6.24 };
  const seconde = page.rafraichirCalques();
  await premiere;
  assert.equal(osmA.options.signal.aborted && bdtopoA.options.signal.aborted, true);
  const [osmB, bdtopoB] = calques().slice(2);
  repondre(osmB, { voies: [], barrieres: [], bornes: [43.4, 6.2, 43.45, 6.25] });
  repondre(bdtopoB, { troncons: [], bornes: [43.4, 6.2, 43.45, 6.25] });
  await seconde;
  assert.deepEqual(JSON.parse(JSON.stringify(page.CALQUES.osm.charge)), { s: 43.4, w: 6.2, n: 43.45, e: 6.25 });
  // Un petit déplacement dans les tuiles déjà lues : rien à redemander.
  carte.vue = { s: 43.42, w: 6.22, n: 43.44, e: 6.245 };
  await page.rafraichirCalques();
  assert.equal(calques().length, 4);
  // Zoom trop faible pendant une lecture : coupée, et le serveur prévenu.
  carte.vue = { s: 43.31, w: 6.01, n: 43.33, e: 6.04 };
  const troisieme = page.rafraichirCalques();
  carte.getZoom = () => 12;
  await page.rafraichirCalques();
  await troisieme;
  const arret = requetes.find((r) => r.url === "/api/arreter_calques");
  const { calques: arretes, vue } = JSON.parse(arret.options.body);
  assert.deepEqual(arretes, ["osm", "bdtopo"]);
  assert.equal(typeof vue, "number");
});

test("le zoom minimal des calques se règle, reste entre 14 et 19, et se retient", async () => {
  const { page, elements, stockage } = charger();
  // Au grand écran du PC : 14 par défaut ; les bornes sont celles du lot (rien sous 14) et de la carte.
  assert.equal(elements.get("zoomCalques").value, "14");
  assert.equal(page.borneZoomCalques(3), 14);
  assert.equal(page.borneZoomCalques(16), 16);
  assert.equal(page.borneZoomCalques(116), 19);
  assert.equal(page.borneZoomCalques("abc"), 14);
  // Réglé à 16, il est retenu d'une session à l'autre, et la saisie hors bornes y est ramenée.
  page.reglerZoomCalques(16);
  assert.equal(stockage.get("hike2gpx.zoomCalques"), "16");
  page.reglerZoomCalques(2);
  assert.equal(stockage.get("hike2gpx.zoomCalques"), "14");
  // Une page rouverte relit le réglage : 16 retenu, le champ le montre.
  const rouverte = charger({ "hike2gpx.zoomCalques": "16" });
  assert.equal(rouverte.elements.get("zoomCalques").value, "16");
});

test("données hors ligne : téléchargées d'elles-mêmes, suivies, et le calcul reprend", async () => {
  // Décision de Nico du 2026-10-19 : aucun bouton. Le serveur télécharge ce
  // qui manque, la page le montre et relance le calcul qui attendait.
  const { page, elements, requetes } = charger();
  const texte = () => elements.get("extraitTexte").textContent;
  const statut = () => elements.get("statut").textContent;
  const nom = "Provence Alpes-Cote-d'Azur";
  const installe = { id: "paca", nom, date: "2026-10-18T20:25:06Z" };
  page.afficherExtrait({ en_cours: null, brouter: null });
  assert.equal(elements.get("extraitOsm").hidden, true);
  assert.equal(elements.get("brouterEnCours").hidden, true);
  // Overpass en panne pendant un calcul : le serveur a lancé l'extrait.
  page.afficherErreur({ erreur: "Overpass ne répond pas : barrières non vérifiées (HTTP 502).",
    extrait_en_cours: { id: "paca", nom } });
  assert.equal(statut(), `Overpass ne répond pas ; l'extrait OSM ${nom} se télécharge, le calcul reprendra de lui-même.`);
  assert.equal(page.etat.donneesAttendues.extrait, "paca");
  assert.ok(requetes.some((r) => r.url.startsWith("/api/extrait?")));
  page.afficherExtrait({ en_cours: { id: "paca", nom, etape: "telechargement", fraction: 0.42, voies: 0 }, brouter: null });
  assert.equal(texte(), `Données OSM hors ligne : téléchargement de l'extrait ${nom}, 42 %`);
  // Sa barre suit le téléchargement, puis va et vient pendant l'import.
  const piste = elements.get("extraitPiste");
  assert.equal(piste.hidden, false);
  assert.equal(piste.classList.contains("indeterminee"), false);
  assert.equal(elements.get("extraitBarre").style.width, "42%");
  page.afficherExtrait({ en_cours: { id: "paca", nom, etape: "import", fraction: 1, voies: 210710 }, brouter: null });
  assert.match(texte(), /^Données OSM hors ligne : import de l'extrait .*, 210.710 voies lues…$/);
  assert.equal(piste.classList.contains("indeterminee"), true);
  assert.equal(elements.get("extraitBarre").style.width, "");
  // L'extrait est là, mais une tuile BRouter arrive encore : on attend toujours.
  page.afficherExtrait({ en_cours: { ...installe, etape: "fini" }, installe, brouter: { moteur: false, segments: ["E0_N45"] } });
  assert.equal(elements.get("brouterTexte").textContent, "Données BRouter : téléchargement en cours (E0_N45)…");
  assert.equal(elements.get("brouterEnCours").hidden, false);
  assert.equal(piste.hidden, true);
  assert.equal(page.etat.donneesAttendues.extrait, "paca");
  // Tout est arrivé : l'extrait sert, et le calcul qui attendait repart.
  page.afficherExtrait({ en_cours: { ...installe, etape: "fini" }, installe, brouter: null });
  assert.equal(texte(), `Données OSM hors ligne : extrait ${nom} du 18/10/2026, renouvelé tous les 30 jours.`);
  assert.equal(elements.get("brouterEnCours").hidden, true);
  assert.equal(page.etat.donneesAttendues, false);
  page.appliquerLangue("en");
  assert.equal(texte(), `Offline OSM data: ${nom} extract of 18/10/2026, renewed every 30 days.`);
  // Moteur et tuile BRouter manquants : même attente, sans bouton.
  page.appliquerLangue("fr");
  page.afficherErreur({ erreur: "Données BRouter absentes pour cette zone.", segments_manquants: ["E0_N45"],
    brouter_en_cours: { moteur: true, segments: ["E0_N45"] } });
  assert.equal(statut(), "Téléchargement des données BRouter (moteur BRouter, E0_N45) : le calcul reprendra de lui-même.");
  assert.equal(page.etat.donneesAttendues.extrait, null);
});

test("cascade : le Var sert aussitôt, la PACA se prépare sans faire attendre", () => {
  // Nico, 2026-10-20 : « on a la main rapidement sur le var (garéoult), on
  // peut travailler, pendant ce temps paca se prépare ».
  const { page, elements, requetes } = charger();
  const texte = () => elements.get("extraitTexte").textContent;
  const paca = "Provence Alpes-Cote-d'Azur";
  const var_ = { id: "fr-var", nom: "Var", date: "2026-10-19T01:38:06Z" };
  page.afficherErreur({ erreur: "Overpass ne répond pas : barrières non vérifiées (HTTP 502).",
    extrait_en_cours: { id: "fr-var", nom: "Var" } });
  page.debutLecture("osm", 1, "chemins OSM");
  page.afficherExtrait({ en_cours: { id: "fr-var", nom: "Var", etape: "import", fraction: 1, voies: 184075 }, brouter: null });
  assert.equal(page.etat.donneesAttendues.extrait, "fr-var");
  const lectures = () => requetes.filter((r) => r.url.startsWith("/api/osm?")).length;
  const avant = lectures();
  // Le Var installé, la PACA part dans la seconde : le calcul reprend et le
  // calque se relit dans le Var, sans attendre la PACA.
  page.afficherExtrait({ en_cours: { id: "provence-alpes-cote-d-azur", nom: paca, etape: "telechargement",
    fraction: 0.12, voies: 0, relais: true }, installe: var_, brouter: null });
  assert.equal(page.etat.donneesAttendues, false);
  assert.equal(lectures(), avant + 1);
  assert.equal(texte(), `Données OSM hors ligne : extrait Var du 19/10/2026 ; la région ${paca} se télécharge pour prendre le relais, 12 %`);
  page.afficherExtrait({ en_cours: { id: "provence-alpes-cote-d-azur", nom: paca, etape: "import",
    fraction: 1, voies: 210710, relais: true }, installe: var_, brouter: null });
  assert.match(texte(), /^Données OSM hors ligne : extrait Var du 19\/10\/2026 ; la région .* s'importe pour prendre le relais, 210.710 voies lues…$/);
  page.appliquerLangue("en");
  assert.match(texte(), /^Offline OSM data: Var extract of 19\/10\/2026; the .* region is importing to take over, 210.710 ways read…$/);
  page.appliquerLangue("fr");
  // La PACA installée : c'est elle qui sert.
  const installe = { id: "provence-alpes-cote-d-azur", nom: paca, date: "2026-10-18T20:25:06Z" };
  page.afficherExtrait({ en_cours: { ...installe, etape: "fini", relais: true }, installe, brouter: null });
  assert.equal(texte(), `Données OSM hors ligne : extrait ${paca} du 18/10/2026, renouvelé tous les 30 jours.`);
});

// Une tuile MVT minimale, écrite à la main : une couche « voies » (un sentier
// qui sort de la tuile) et une couche « franchissements » (un point).
function tuileMvt() {
  const varint = (n) => { const o = []; while (n > 127) { o.push((n & 127) | 128); n >>>= 7; } o.push(n); return o; };
  const zz = (n) => (n << 1) ^ (n >> 31);
  const champ = (numero, octets) => [...varint((numero << 3) | 2), ...varint(octets.length), ...octets];
  const texte = (numero, s) => champ(numero, [...Buffer.from(s, "utf8")]);
  const paquet = (numero, valeurs) => champ(numero, valeurs.flatMap(varint));
  const valeur = (s) => texte(1, s);
  const objet = (type, balises, commandes) => [...paquet(2, balises), 24, type, ...paquet(4, commandes)];
  // Le sentier : de (1000, 1000) à (5000, 1000), recoupé au bord droit (4096).
  const voies = [...texte(1, "voies"),
    ...champ(2, objet(2, [0, 0], [9, zz(1000), zz(1000), 10, zz(4000), zz(0)])),
    ...texte(3, "genre"), ...champ(4, valeur("sentier")), 40, ...varint(4096), 120, 2];
  const points = [...texte(1, "franchissements"),
    ...champ(2, objet(1, [0, 0, 1, 1], [9, zz(2048), zz(2048)])),
    ...texte(3, "cle"), ...texte(3, "statut"), ...champ(4, valeur("noeud-1")), ...champ(4, valeur("blocked")),
    40, ...varint(4096), 120, 2];
  return new Uint8Array([...champ(3, voies), ...champ(3, points)]);
}

test("un lot installé couvre la vue : la page lit et décode ses tuiles elle-même", async () => {
  // Nico, 2026-11-12 : « le pc est bien plus puissant que le téléphone, et il attend plus ».
  const { page, requetes, carte } = charger();
  carte.hasLayer = () => true;
  page.rafraichirCalques();
  const vue = requetes.findLast((r) => r.url.startsWith("/api/osm?"));
  repondre(vue, { lot: { case: "E5_N40", date: 7 }, tuiles: [[8465, 5973]], bornes: [43.3, 6.0, 43.35, 6.05],
    couches: { voies: "voies", barrieres: "barrieres", franchissements: "franchissements", jonctions: "jonctions" } });
  await tic();
  const tuile = requetes.findLast((r) => r.url.startsWith("/calques/"));
  assert.equal(tuile.url, "/calques/E5_N40/8465/5973?v=7", "la tuile brute, datée du lot");
  const octets = tuileMvt();
  tuile.resolve({ ok: true, status: 200, arrayBuffer: async () => octets.buffer });
  for (let i = 0; i < 5; i++) await tic();
  const dessins = page.CALQUES.osm.groupe.layers;
  const sentier = dessins.find((c) => c.options.leg === "osm");
  assert.ok(sentier, "le sentier est dessiné");
  assert.equal(sentier.options.dashArray, "6 4", "avec le style d'un sentier");
  const b = page.bornesTuile(8465, 5973);
  const lons = sentier.points.map(([, lon]) => lon);
  assert.ok(Math.abs(Math.max(...lons) - b.e) < 1e-9, "recoupé au bord de la tuile");
  assert.ok(Math.min(...lons) > b.w);
  assert.ok(dessins.some((c) => c.options.fillColor && c.options.leg !== "osm"), "le franchissement aussi");
  // La même vue ne redemande rien : la tuile est gardée décodée.
  page.CALQUES.osm.charge = null;
  page.rafraichirCalques();
  repondre(requetes.findLast((r) => r.url.startsWith("/api/osm?")), { lot: { case: "E5_N40", date: 7 },
    tuiles: [[8465, 5973]], bornes: [43.3, 6.0, 43.35, 6.05],
    couches: { voies: "voies", barrieres: "barrieres", franchissements: "franchissements", jonctions: "jonctions" } });
  for (let i = 0; i < 5; i++) await tic();
  assert.equal(requetes.filter((r) => r.url.startsWith("/calques/")).length, 1, "pas de seconde requête de tuile");
});

test("chargement des calques : la note suit les tuiles lues, barre comprise", () => {
  // Nico, 2026-10-20 : « Chargement des chemins OSM… » sans barre de progression.
  const { page, elements, minuteurs } = charger();
  const note = () => elements.get("noteCalquesTexte")?.textContent ?? "";
  page.debutLecture("osm", 1, "chemins OSM");
  // Nico, 2026-11-12 : une lecture brève (un lot installé) ne montre rien ;
  // la note attend une seconde, puis paraît si la lecture dure.
  assert.equal(note(), "");
  assert.equal(minuteurs.at(-1).ms, 1000);
  page.afficherLectures(null);
  const piste = elements.get("noteCalquesPiste");
  assert.equal(note(), "Chargement des chemins OSM… (la première fois, jusqu'à une minute)");
  assert.equal(piste.hidden, false);
  assert.equal(piste.classList.contains("indeterminee"), true);
  page.afficherLectures({ osm: { faites: 2, total: 6, duree_s: 12.4 } });
  assert.equal(note(), "Chargement des chemins OSM… 2 sur 6 tuiles · 12 s");
  assert.equal(piste.classList.contains("indeterminee"), false);
  assert.equal(elements.get("noteCalquesBarre").style.width, "33%");
  // Deux calques à la fois : une note, leurs tuiles additionnées.
  page.debutLecture("bdtopo", 1, "chemins BD TOPO (IGN)");
  page.afficherLectures({ osm: { faites: 3, total: 6, duree_s: 20 }, bdtopo: { faites: 6, total: 6, duree_s: 3 } });
  assert.equal(note(), "Chargement des chemins OSM et chemins BD TOPO (IGN)… 9 sur 12 tuiles · 20 s");
  // La fin d'une vue périmée ne retire pas la lecture de la vue suivante.
  assert.equal(page.finLecture("osm", 0), true);
  assert.equal(page.finLecture("osm", 1), true);
  assert.equal(page.finLecture("bdtopo", 1), false);
});

test("extrait installé pendant la lecture des chemins OSM : elle repart sur lui", () => {
  // Essai du 2026-10-20 : l'extrait Corse installé en 16 s, la lecture partie
  // avant lui attendait encore Overpass (HTTP 504, 502) deux minutes après.
  const { page, requetes, carte } = charger();
  carte.hasLayer = () => true;
  const lues = (cle) => requetes.filter((r) => r.url.startsWith(`/api/${cle}?`)).length;
  page.afficherExtrait({ en_cours: { id: "corse", nom: "Corse", etape: "import", fraction: 1, voies: 35811 }, brouter: null });
  page.rafraichirCalques();
  assert.equal(lues("osm"), 1);
  const installe = { id: "corse", nom: "Corse", date: "2026-10-18T20:25:06Z" };
  page.afficherExtrait({ en_cours: { ...installe, etape: "fini" }, installe, brouter: null });
  assert.equal(lues("osm"), 2);
  assert.equal(lues("bdtopo"), 1);          // la BD TOPO ne dépend pas de l'extrait
  // Déjà installé : un nouvel état « fini » ne relance rien.
  page.afficherExtrait({ en_cours: { ...installe, etape: "fini" }, installe, brouter: null });
  assert.equal(lues("osm"), 2);
});

test("vues datées : le serveur ne lit que la plus récente, et la note ne reste pas figée", async () => {
  // Calque figé du 2026-10-20 : une requête plus ancienne, arrivée après la
  // plus récente, passait au serveur pour la vue en cours. Les vues portent
  // désormais leur date, strictement croissante.
  const { page, elements, requetes, carte } = charger();
  carte.hasLayer = (groupe) => groupe === page.CALQUES.osm.groupe;
  const premiere = page.rafraichirCalques();
  carte.vue = { s: 43.41, w: 6.21, n: 43.44, e: 6.26 };
  const seconde = page.rafraichirCalques();
  await premiere;
  const osm = requetes.filter((r) => r.url.startsWith("/api/osm?"));
  const dates = osm.map((r) => Number(new URL(r.url, "http://h").searchParams.get("vue")));
  assert.equal(dates.length, 2);
  assert.ok(dates[0] > 0 && dates[1] > dates[0]);
  // Remplacée malgré tout (une autre page ouverte) : pas de chargement sans fin.
  repondre(osm[1], { erreur: "Vue remplacée par une autre.", code: "vue_remplacee" });
  await seconde;
  assert.equal(elements.get("noteCalques").hidden, true);
  // L'arrêt envoyé au serveur porte aussi sa date.
  carte.vue = { s: 43.51, w: 6.31, n: 43.54, e: 6.36 };
  page.rafraichirCalques();
  carte.getZoom = () => 10;
  await page.rafraichirCalques();
  const arret = requetes.find((r) => r.url === "/api/arreter_calques");
  const corps = JSON.parse(arret.options.body);
  assert.deepEqual(corps.calques, ["osm"]);
  assert.ok(corps.vue > dates[1]);
});

test("un bouton unique vide les caches locaux après confirmation", () => {
  const { page, elements, requetes, confirmations } = charger();
  page.afficherDonnees({
    osm: { fichiers: 42, octets: 12_400_000 }, bdtopo: { fichiers: 0, octets: 0 },
    extraits: [{ id: "fr-var", nom: "Var", date: "2026-10-19T01:38:06Z", octets: 69_080_000, provisoire: true },
      { id: "provence-alpes-cote-d-azur", nom: "Provence Alpes-Cote-d'Azur", date: "2026-10-18T20:25:06Z",
        octets: 345_800_000, provisoire: false }],
    brouter: [{ nom: "E5_N40", octets: 69_219_770, date: "2026-10-19T09:00:00Z" }],
    restes: { fichiers: 1, octets: 3_600_000 },
    occupe: { extrait: "provence-alpes-cote-d-azur", brouter: false },
  });
  let controles = elements.get("donnees").enfants[0];
  let bouton = controles.enfants[0];
  assert.equal(bouton.enfants[1].textContent, "Vider le cache", "pictogramme, puis texte");
  assert.match(controles.enfants[1].enfants[0].textContent, /IGN LiDAR HD|gpx2elev/);
  assert.match(controles.enfants[1].enfants[0].textContent, /tuiles des fonds de carte/);
  assert.equal(bouton.disabled, true);
  page.afficherDonnees({ occupe: { extrait: null, brouter: false } });
  bouton = elements.get("donnees").enfants[0].enfants[0];
  assert.equal(bouton.disabled, false);
  bouton.ecouteurs.click[0]();
  assert.match(confirmations[0], /les zones de routage et les fonds hors ligne/);
  assert.equal(requetes.filter((r) => r.url === "/api/donnees").length, 0);
  confirmations.reponse = true;
  bouton.ecouteurs.click[0]();
  const envoi = requetes.find((r) => r.url === "/api/donnees");
  assert.deepEqual(JSON.parse(envoi.options.body), { action: "vider_cache", cible: null });
  page.appliquerLangue("en");
  assert.equal(elements.get("donnees").enfants[0].enfants[0].enfants[1].textContent, "Clear cache");
  assert.match(elements.get("donnees").enfants[0].enfants[1].enfants[0].textContent, /BRouter data/);
});

test("la légende ne montre que ce qui est sur la carte, dans l'ordre voulu", () => {
  const { page, elements, carte } = charger();
  const ordre = elements.get("legendRows").enfants.map((l) => l.dataset.legende);
  assert.deepEqual(ordre, ["osm", "chemins_officiels", "itineraire", "gpx", "barriere", "bloque", "verifier", "jonction"]);
  page.majLegende();
  assert.deepEqual(legendeVisible(elements), [], "rien sur la carte : aucune ligne");
  assert.equal(elements.get("mapLegend").classList.contains("vide"), true);
  // Un franchissement à vérifier et un tracé : ces deux lignes seules, dans l'ordre de la légende.
  carte.layers.push({ options: { leg: "verifier" } }, { options: { leg: "itineraire" } });
  page.majLegende();
  assert.deepEqual(legendeVisible(elements), ["itineraire", "verifier"]);
  assert.equal(elements.get("mapLegend").classList.contains("vide"), false);
  // Un groupe de couches compte aussi par ses enfants (le calque OSM).
  carte.layers.push({ layers: [{ options: { leg: "osm" } }, { options: { leg: "barriere" } }] });
  page.majLegende();
  assert.deepEqual(legendeVisible(elements), ["osm", "itineraire", "barriere", "verifier"]);
});

test("les couches d'affichage seul (Espagne, États-Unis) n'ont pas de ligne de légende officielle", () => {
  const { page, elements, carte } = charger();
  page.choisirPays("es");
  page.coucheCalque("senderos").addTo(carte);
  page.majLegende();
  assert.equal(ligneLegende(elements, "chemins_officiels").hidden, true);
  page.choisirPays("fr");
  page.coucheCalque("bdtopo").addTo(carte);
  page.coucheCalque("bdtopo").getLayers = () => page.coucheCalque("bdtopo").layers;
  page.coucheCalque("bdtopo").layers.push({ options: {} });
  page.majLegende();
  assert.equal(elements.get("legendOfficielTexte").textContent, "chemin IGN");
});

test("un KML de gpx2dash : nom, date, D+ et durée lus dans le nom, couleur KML convertie", () => {
  const { page } = charger();
  const lu = page.lireNomTrace("2020-12-13_LA ROQUEBRUSSANNE_8.7KM_D+350M_2H18");
  assert.equal(lu.titre, "LA ROQUEBRUSSANNE");
  assert.equal(lu.date.toISOString().slice(0, 10), "2020-12-13");
  assert.equal(lu.km, 8.7);
  assert.equal(lu.dplus, 350);
  assert.equal(lu.minutes, 138);
  const autre = page.lireNomTrace("2015-04-24_Tourris10_Le Revest-les-Eaux_11.5km_D+514m_2h21");
  assert.equal(autre.titre, "Tourris10 Le Revest-les-Eaux");
  assert.equal(autre.minutes, 141);
  const recente = page.lireNomTrace("2026-04-27_12-14 La Roquebrussanne_17.8km_D+690m_3h49");
  assert.equal(recente.titre, "La Roquebrussanne");
  assert.equal(recente.heure, "12 h 14");
  assert.equal(JSON.stringify(page.lireNomTrace("Sortie du dimanche")), JSON.stringify({ titre: "Sortie du dimanche" }));
  // KML : aabbggrr. ff5622e5 = opaque, rouge e5, vert 22, bleu 56.
  assert.equal(JSON.stringify(page.couleurKml("ff5622e5")), JSON.stringify({ couleur: "#e52256", opacite: 1 }));
  assert.equal(JSON.stringify(page.couleurKml("pas une couleur")), "{}");
});

test("sans zone installée, la planification demande la zone, et s'ouvre une fois téléchargée", async () => {
  // Nico, 2026-11-13 : « laisser le menu de planification disponible, mais avec une question
  // sur le téléchargement si aucune zone est là localement ».
  const { page, requetes, confirmations, evenements } = charger();
  const ouvertures = () => evenements.filter((e) => e === "hike2gpx:ouvrir-page").length;
  // Refusée : la page se referme, rien ne se télécharge.
  confirmations.reponse = false;
  page.planifier(true);
  repondre(requetes.findLast((r) => r.url === "/api/zone_planification"), { proposer: { case: "E5_N40", octets: 248e6 } });
  await tic();
  await tic();
  assert.match(confirmations.at(-1), /case E5_N40, 248 Mo/);
  assert.equal(ouvertures(), 1, "la page se referme");
  assert.equal(requetes.some((r) => r.url === "/api/telecharger_lot"), false);
  // Acceptée : la zone se télécharge, la page se rouvre à la fin.
  confirmations.reponse = true;
  page.planifier(true);
  repondre(requetes.findLast((r) => r.url === "/api/zone_planification"), { proposer: { case: "E5_N40", octets: 248e6 } });
  await tic();
  await tic();
  const telechargement = requetes.findLast((r) => r.url === "/api/telecharger_lot");
  assert.deepEqual(JSON.parse(telechargement.options.body), { case: "E5_N40" });
  repondre(telechargement, { lot_en_cours: { actif: true, case: "E5_N40", etape: "telechargement" } });
  await tic();
  await tic();
  assert.equal(ouvertures(), 2, "la carte et la ligne d'activité, le temps du téléchargement");
  repondre(requetes.findLast((r) => r.url === "/api/lot_en_cours"), { actif: false, case: "E5_N40", etape: "fini" });
  for (let k = 0; k < 6; k++) await tic();
  for (const r of requetes.filter((r) => r.url === "/api/hors_ligne" && !r.repondue)) { r.repondue = true; repondre(r, { lots: [], fonds: [] }); }
  for (let k = 0; k < 6; k++) await tic();
  assert.equal(ouvertures(), 3, "la page se rouvre, la zone installée");
  // Une zone installée : la page reste ouverte, sans question.
  const avant = confirmations.length;
  page.planifier(true);
  repondre(requetes.findLast((r) => r.url === "/api/zone_planification"), { ouvrir: true });
  await tic();
  assert.equal(confirmations.length, avant);
});

test("sans zone publiée par le serveur, la planification propose de la fabriquer sur le PC", async () => {
  // Montréal, Nico, 2026-11-13 : « je lance la planification, mais j'ai pas le message de
  // création du lot par le pc ».
  const { page, requetes, confirmations, evenements } = charger();
  const ouvertures = () => evenements.filter((e) => e === "hike2gpx:ouvrir-page").length;
  const fabriquer = { fabriquer: { case: "W75_N45", octets: 120e6 } };
  confirmations.reponse = false;
  page.planifier(true);
  repondre(requetes.findLast((r) => r.url === "/api/zone_planification"), fabriquer);
  await tic();
  await tic();
  assert.match(confirmations.at(-1), /case W75_N45\. La préparer sur ce PC \? D'abord la zone simple de brouter\.de \(120 Mo\)/);
  assert.equal(ouvertures(), 1, "refusée, la page se referme");
  assert.equal(requetes.some((r) => r.url === "/api/preparer_lot"), false);
  // Acceptée : la zone simple d'abord, puis la zone étendue (Nico : « pour ne pas bloquer la
  // planification, sur le pc on commence par la zone simple brouter »).
  confirmations.reponse = true;
  page.planifier(true);
  repondre(requetes.findLast((r) => r.url === "/api/zone_planification"), fabriquer);
  await tic();
  await tic();
  const preparation = requetes.findLast((r) => r.url === "/api/preparer_lot");
  assert.deepEqual(JSON.parse(preparation.options.body), { case: "W75_N45", simple: true });
  repondre(preparation, { lot_en_cours: { actif: true, case: "W75_N45", etape: "debut" } });
  await tic();
  await tic();
  assert.equal(ouvertures(), 2, "la carte et la ligne d'activité, le temps de la zone simple");
  // La zone simple installée : la page s'ouvre, la zone étendue continue.
  repondre(requetes.findLast((r) => r.url === "/api/lot_en_cours"),
    { actif: true, case: "W75_N45", etape: "extraits", simple_installee: true });
  for (let k = 0; k < 6; k++) await tic();
  for (const r of requetes.filter((r) => r.url === "/api/hors_ligne" && !r.repondue)) { r.repondue = true; repondre(r, { lots: [], fonds: [] }); }
  for (let k = 0; k < 6; k++) await tic();
  assert.equal(ouvertures(), 3, "la page s'ouvre sur la zone simple");
  // La zone étendue finie ne rouvre rien de plus.
  repondre(requetes.findLast((r) => r.url === "/api/lot_en_cours"), { actif: false, case: "W75_N45", etape: "fini" });
  for (let k = 0; k < 6; k++) await tic();
  for (const r of requetes.filter((r) => r.url === "/api/hors_ligne" && !r.repondue)) { r.repondue = true; repondre(r, { lots: [], fonds: [] }); }
  for (let k = 0; k < 6; k++) await tic();
  assert.equal(ouvertures(), 3);
  // Ni zone ici ni serveur joignable : pas de données de routage, la page se referme
  // (Nico : « on avait dit qu'on bloquait la planification, si pas de données »).
  page.planifier(true);
  repondre(requetes.findLast((r) => r.url === "/api/zone_planification"),
    { erreur: "Pas de zone de routage ici, et le serveur des zones est injoignable.", code: "serveur_zones_injoignable" });
  await tic();
  await tic();
  assert.equal(ouvertures(), 4, "la page se referme");
});

