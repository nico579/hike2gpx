// Comportement de la page (app.js) sous Node : un DOM et un Leaflet réduits au
// nécessaire, le réseau et les minuteries tenus à la main. Repris du banc de
// l'audit du 18 octobre (B06). Lancé par test_page.py, ou : node --test tests

"use strict";
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");
const assert = require("node:assert/strict");
const { couvertureCartographique } = require("../hike2gpx/assets/web/presentation.js");

function charger(preferences = {}, documentGpx = null) {
  const elements = new Map();
  const stockage = new Map(Object.entries(preferences));
  const minuteurs = [];
  const element = () => {
    const classes = new Set();
    return { disabled: true, hidden: false, checked: false, textContent: "", value: "", dataset: {},
      style: { setProperty(name, value) { this[name] = value; } },
      classList: { toggle(c, oui) { (oui ?? !classes.has(c)) ? classes.add(c) : classes.delete(c); },
        contains: (c) => classes.has(c) },
      enfants: [], ecouteurs: {},
      append(...e) { this.enfants.push(...e); }, replaceChildren(...e) { this.enfants = e; },
      setAttribute(name, value) { this[name] = value; },
      addEventListener(type, f) { (this.ecouteurs[type] ??= []).push(f); }, remove() { this.removed = true; },
      click() { for (const action of this.ecouteurs.click || []) action(); } };
  };
  const couche = () => ({ handlers: {}, layers: [], addTo(parent) { this.addedTo = parent; parent.layers?.push(this); return this; }, bindPopup() { return this; }, bindTooltip() { return this; },
    on(name, handler) { this.handlers[name] = handler; return this; }, setIcon() { return this; }, clearLayers() { this.layers = []; }, remove() { this.removed = true; }, closePopup() {} });
  const carte = { handlers: {}, zoom: 14, setView(center, zoom) { this.center = center; this.viewZoom = zoom; return this; },
    fitBounds(bounds, options) { this.fit = { bounds, options }; return this; },
    on(name, handler) { const precedent = this.handlers[name]; this.handlers[name] = precedent
      ? (...args) => { precedent(...args); handler(...args); } : handler; }, createPane() { return { style: {} }; },
    hasLayer() { return false; }, getZoom() { return this.zoom; }, invalidateSize() {},
    getCenter() { return { lat: (this.vue.s + this.vue.n) / 2, lng: (this.vue.w + this.vue.e) / 2 }; },
    vue: { s: 43.31, w: 6.01, n: 43.33, e: 6.04 },
    getBounds() { const v = this.vue; return { getSouth: () => v.s, getWest: () => v.w, getNorth: () => v.n,
      getEast: () => v.e }; } };
  const requetes = [];
  const pressePapiers = [];
  const confirmations = Object.assign([], { reponse: false });
  const corps = element();
  const contexte = vm.createContext({
    console, URL, URLSearchParams, Blob, Date, Number, String, AbortController, performance,
    DOMParser: class { parseFromString() { return documentGpx; } },
    document: { getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
      createElement: element, createTextNode: String, body: corps, documentElement: element(),
       addEventListener() {}, querySelectorAll(selector) {
         if (selector !== "[data-map-overlay]") return [];
         return [["legendBdtopo", "bdtopo"], ["legendAtkis", "atkis"], ["legendSenderos", "senderos"],
           ["legendSuisse", "suisseSentiers"]].map(([id, cle]) => {
           const ligne = this.getElementById(id); ligne.dataset.mapOverlay = cle; return ligne;
         });
       } },
    localStorage: { getItem(key) { return stockage.get(key) ?? null; }, setItem(key, value) { stockage.set(key, value); } },
    confirm: (texte) => { confirmations.push(texte); return confirmations.reponse; },
    navigator: { clipboard: { async writeText(texte) { pressePapiers.push(texte); } } },
    setTimeout(callback, ms) { minuteurs.push({ callback, ms }); return minuteurs.length; },
    clearTimeout(id) { if (minuteurs[id - 1]) minuteurs[id - 1].annule = true; },
    setInterval() { return 1; }, clearInterval() {},
     L: { map() { return carte; }, layerGroup: couche, canvas: couche,
       popup: (options) => ({ options, setLatLng(latlng) { this.latlng = latlng; return this; },
         setContent(content) { this.content = content; return this; },
         openOn(map) { map.popup = this; return this; } }),
       vectorGrid: { protobuf: (url, options) => Object.assign(couche(), { url, options }) },
      polyline: (points, options) => Object.assign(couche(), { points, options }), circleMarker: couche,
      marker: (latlng, options) => Object.assign(couche(), { position: latlng, options, getLatLng() { return this.position; } }),
      tileLayer: Object.assign((url, options) => Object.assign(couche(), { url, options }),
        { wms: (url, options) => Object.assign(couche(), { url, options }) }),
      CRS: { EPSG4326: { code: "EPSG:4326" } }, divIcon: (options) => ({ options }),
      control: { layers: (fonds, calques) => Object.assign(couche(), { fonds, calques,
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
  const source = path.join(__dirname, "..", "hike2gpx", "assets", "web", "app.js");
  vm.runInContext(fs.readFileSync(source, "utf8")
    + "\nglobalThis.page = { etat, calculer, planifierCalcul, ajouterPoint, boucler, basculerPleinEcran,"
    + " appliquerLangue, texteErreur, rafraichirCalques, CALQUES, afficherExtrait, afficherErreur,"
    + " afficherDisponibilite,"
     + " debutLecture, finLecture, afficherLectures, afficherDonnees, construireFonds, choisirPays,"
    + " fond: () => fondActif, fonds: () => couchesFonds, controle: () => controleFonds, restaurerCalques,"
    + " preparerFleches, afficherFleches, fleches, traceGpxImporte, TEXTES, providers: window.HIKE2GPX_MAP_PROVIDERS,"
    + " setFleches: (valeur) => { flechesTrace = valeur; } };", contexte);
  const derniere = () => requetes.filter((r) => r.url === "/api/itineraire").at(-1);
  return { page: contexte.page, elements, derniere, corps, requetes, carte, confirmations, stockage, minuteurs, pressePapiers };
}

function resultat(lonArrivee) {
  return { itineraire: { type: "Feature", properties: {},
    geometry: { type: "LineString", coordinates: [[6, 43.3, 0], [lonArrivee, 43.3, 0]] } },
    franchissements: [], sur_le_trace: [], portions_ign: [], longueur_m: 809, denivele_m: 0, duree_s: 0.1 };
}

const repondre = (requete, corps) => requete.resolve({ ok: true, json: async () => corps });

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
    ["Chemins OSM", "Chemins BD TOPO (IGN)", "2026-09-20_09-03"]);
  assert.equal(elements.get("legendGpx").hidden, false);
  page.traceGpxImporte.remove();
  carte.handlers["overlayadd overlayremove"]({ layer: page.traceGpxImporte, type: "overlayremove" });
  assert.equal(page.traceGpxImporte.layers.length, 2);
  page.traceGpxImporte.addTo(carte);
  page.construireFonds();
  assert.equal(page.controle().calques["2026-09-20_09-03"], page.traceGpxImporte);
  assert.equal(elements.get("chargerGpx").textContent, "Supprimer le GPX");
  assert.equal(page.etat.points.length, 0);
  assert.equal(stockage.has("hike2gpx.points"), false);
  elements.get("chargerGpx").click();
  assert.equal(page.traceGpxImporte.layers.length, 0);
  assert.equal(page.controle().calques["2026-09-20_09-03"], undefined);
  assert.equal(elements.get("legendGpx").hidden, true);
  assert.equal(elements.get("chargerGpx").textContent, "Charger un GPX");
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
        assert.ok(provider.baseNames?.[fond]?.[langue] || page.TEXTES[langue][`fond.${fond}`],
          `${code} : libellé ${langue} « fond.${fond} » manquant`);
      }
      for (const calque of provider.overlays || []) {
        assert.ok(page.TEXTES[langue][`calque.${calque}`], `${code} : libellé ${langue} « calque.${calque} » manquant`);
        assert.ok(provider.overlayNames?.[calque]?.[langue],
          `${code} : calque du panneau ⓘ sans libellé ${langue}`);
      }
      if (provider.paths) assert.ok(provider.paths.name[langue] && provider.paths.legend[langue]);
    }
  }
});

test("le bouton d'information présente fond, chemins et itinéraire pour tous les pays", () => {
  const { page } = charger();
  const fr = couvertureCartographique(page.providers, "fr");
  assert.equal(fr.length, 11);
  assert.deepEqual(fr.map((p) => p.code).sort(),
    ["at", "ch", "cz", "de", "es", "fr", "lu", "nl", "no", "pl", "us"]);
  assert.match(fr.find((p) => p.code === "cz").chemins, /ZABAGED/);
  assert.equal(fr.find((p) => p.code === "cz").itineraire, "OSM + ZABAGED");
  assert.match(fr.find((p) => p.code === "ch").chemins, /swissTLM3D.*swisstopo/);
  assert.equal(fr.find((p) => p.code === "pl").itineraire, "OSM + BDOT10k (Basse-Silésie)");
  assert.equal(fr.find((p) => p.code === "at").chemins, "OSM");
  assert.equal(fr.find((p) => p.code === "es").itineraire, "OSM");
  const en = couvertureCartographique(page.providers, "en");
  assert.equal(en.find((p) => p.code === "pl").itineraire, "OSM + BDOT10k (Lower Silesia)");
  assert.equal(en.find((p) => p.code === "us").fond, "USGS topographic map");
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
  page.afficherDisponibilite({ pret: false, source: null, attente: "osm" });
  assert.equal(elements.get("readinessText").textContent, "Tracé indisponible");
  page.ajouterPoint({ lat: 43.3, lng: 6 });
  page.ajouterPoint({ lat: 43.31, lng: 6.02 });
  const calcul = minuteurs.findLast((m) => m.ms === 250 && !m.annule).callback();
  repondre(derniere(), resultat(6.02));
  await calcul;
  page.afficherDisponibilite({ pret: false, source: null, attente: "osm" });
  assert.equal(elements.get("readinessText").textContent, "Tracé indisponible");
  page.afficherDisponibilite({ pret: true, source: "cache", details: {
    overpass: "oui", local: { nom: "Var", etat: "disponible" },
    regional: { nom: "Provence-Alpes-Côte d’Azur", etat: "import" },
  } });
  assert.equal(elements.get("readinessText").textContent, "Tracé disponible");
  assert.equal(elements.get("readiness").classList.contains("available"), true);
  assert.match(elements.get("readinessInfoText").textContent, /Overpass : répond/);
  assert.match(elements.get("readinessInfoText").textContent, /Extrait OSM local \(Var\) : disponible/);
  assert.match(elements.get("readinessInfoText").textContent, /Extrait OSM régional .* : import en cours/);
  page.appliquerLangue("en");
  assert.equal(elements.get("readinessText").textContent, "Routing available");
  assert.match(elements.get("readinessInfoText").textContent, /Regional OSM extract .* : importing/);
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
  assert.deepEqual(Object.keys(page.controle().calques), ["Chemins OSM", "Sentiers balisés GR/PR/SL (IGN Espagne)"]);
  assert.equal(page.fonds().reliefLidar, undefined);
  assert.match(page.fond().url, /ign\.es\/wmts\/mapa-raster/);
  assert.equal(page.CALQUES.bdtopo.groupe.removed, true);
  assert.equal(elements.get("ignOption").hidden, false);
  assert.equal(elements.get("ign").disabled, true);
  assert.match(elements.get("ignOptionTexte").textContent, /affichage seul/);
  assert.equal(elements.get("legendBdtopo").hidden, true);
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
  assert.match(elements.get("ignOptionTexte").textContent, /chemins BD TOPO \(IGN\)/);
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
  assert.deepEqual(Object.keys(page.controle().calques), ["Chemins OSM"]);
  assert.equal(elements.get("ignOption").hidden, true);
  page.choisirPays("nl");
  assert.match(page.fond().url, /service\.pdok\.nl\/kadaster\/brt-achtergrondkaart/);
  assert.deepEqual(Object.keys(page.controle().calques), ["Chemins OSM"]);
  assert.equal(elements.get("ignOption").hidden, true);
});

test("l'Allemagne propose TopPlusOpen et le calque ATKIS par zone", async () => {
  const { page, elements, carte, requetes } = charger();
  page.choisirPays("de");
  assert.match(page.fond().url, /sgx\.geodatenzentrum\.de\/wmts_topplus_open\/tile\/1\.0\.0\/web\/default\/WEBMERCATOR\/\{z\}\/\{y\}\/\{x\}\.png/);
  assert.match(page.fond().options.attribution, /BKG.*dl-de\/by-2-0.*Datenquellen/);
  assert.deepEqual(Object.keys(page.controle().calques),
    ["Chemins OSM", "Chemins ATKIS (Allemagne)"]);
  assert.match(page.CALQUES.atkis.groupe.getAttribution(), /GeoBasis-DE.*GDI-Th.*BVV.*CC BY 4\.0/);
  assert.equal(elements.get("legendAtkis").hidden, false);
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

test("les nouveaux providers transmettent leur source au calcul, avec limite régionale polonaise", async () => {
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
    assert.ok(page.controle().calques[page.providers[pays].paths.name.fr]);
    assert.equal(elements.get("ign").disabled, false);
    page.etat.points = [{ lat: centre[0], lon: centre[1] },
      { lat: centre[0] + 0.001, lon: centre[1] + 0.001 }];
    const calcul = page.calculer();
    const requete = derniere();
    assert.equal(JSON.parse(requete.options.body).source, source);
    repondre(requete, { erreur: "fin de l'essai" });
    await calcul;
    if (pays === "pl") {
      carte.vue = { s: 52.0, w: 16.0, n: 52.01, e: 16.01 };
      carte.handlers.moveend();
      assert.equal(elements.get("ign").disabled, true);
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
  const { page, elements, derniere } = charger();
  page.appliquerLangue("en");
  page.ajouterPoint({ lat: 43.3, lng: 6 });
  await page.calculer();
  assert.equal(elements.get("statut").textContent, "Place a second point.");
  const refus = { erreur: "Itinéraire refusé : …", code: "itineraire_refuse",
    valeurs: { nature: "Clôture", statut: "blocked", distance_m: 1500 } };
  assert.equal(page.texteErreur(refus), "Route refused: it passes a blocking crossing (Fence, 1.50 km from the start).");
  assert.equal(page.texteErreur({ erreur: "Calcul trop long : rapprochez les points." }),
    "Calculation too long: bring the points closer.");
  page.appliquerLangue("fr");
  assert.equal(elements.get("statut").textContent, "Posez un deuxième point.");
});

test("plein écran : la carte seule, puis la page revient", () => {
  const { page, corps } = charger();
  page.basculerPleinEcran();
  assert.equal(corps.classList.contains("plein-ecran"), true);
  page.basculerPleinEcran();
  assert.equal(corps.classList.contains("plein-ecran"), false);
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

test("chargement des calques : la note suit les tuiles lues, barre comprise", () => {
  // Nico, 2026-10-20 : « Chargement des chemins OSM… » sans barre de progression.
  const { page, elements } = charger();
  const note = () => elements.get("noteCalquesTexte").textContent;
  page.debutLecture("osm", 1, "chemins OSM");
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
  assert.equal(bouton.textContent, "Vider le cache");
  assert.match(controles.enfants[1].enfants[0].textContent, /IGN LiDAR HD|gpx2elev/);
  assert.match(controles.enfants[1].enfants[0].textContent, /tuiles des fonds de carte IGN et OSM/);
  assert.equal(bouton.disabled, true);
  page.afficherDonnees({ occupe: { extrait: null, brouter: false } });
  bouton = elements.get("donnees").enfants[0].enfants[0];
  assert.equal(bouton.disabled, false);
  bouton.ecouteurs.click[0]();
  assert.match(confirmations[0], /Les tuiles de fond de carte restent dans le cache du navigateur/);
  assert.equal(requetes.filter((r) => r.url === "/api/donnees").length, 0);
  confirmations.reponse = true;
  bouton.ecouteurs.click[0]();
  const envoi = requetes.find((r) => r.url === "/api/donnees");
  assert.deepEqual(JSON.parse(envoi.options.body), { action: "vider_cache", cible: null });
  page.appliquerLangue("en");
  assert.equal(elements.get("donnees").enfants[0].enfants[0].textContent, "Clear cache");
  assert.match(elements.get("donnees").enfants[0].enfants[1].enfants[0].textContent, /BRouter data/);
});
