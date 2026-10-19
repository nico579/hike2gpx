// Comportement de la page (app.js) sous Node : un DOM et un Leaflet réduits au
// nécessaire, le réseau et les minuteries tenus à la main. Repris du banc de
// l'audit du 18 octobre (B06). Lancé par test_page.py, ou : node --test tests

"use strict";
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const test = require("node:test");
const assert = require("node:assert/strict");

function charger() {
  const elements = new Map();
  const element = () => {
    const classes = new Set();
    return { disabled: true, hidden: false, checked: false, textContent: "", value: "", style: {},
      classList: { toggle(c, oui) { (oui ?? !classes.has(c)) ? classes.add(c) : classes.delete(c); },
        contains: (c) => classes.has(c) },
      append() {}, replaceChildren() {}, addEventListener() {}, remove() {}, click() {} };
  };
  const couche = () => ({ addTo() { return this; }, bindPopup() { return this; }, bindTooltip() { return this; },
    on() { return this; }, setIcon() { return this; }, clearLayers() {}, remove() {}, closePopup() {} });
  const carte = { setView() { return this; }, on() {}, createPane() { return { style: {} }; },
    hasLayer() { return false; }, getZoom() { return 14; }, invalidateSize() {},
    vue: { s: 43.31, w: 6.01, n: 43.33, e: 6.04 },
    getBounds() { const v = this.vue; return { getSouth: () => v.s, getWest: () => v.w, getNorth: () => v.n,
      getEast: () => v.e }; } };
  const requetes = [];
  const corps = element();
  const contexte = vm.createContext({
    console, URL, URLSearchParams, Blob, Date, Number, String, AbortController,
    document: { getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
      createElement: element, createTextNode: String, body: corps, documentElement: element(),
      addEventListener() {}, querySelectorAll() { return []; } },
    localStorage: { getItem() { return null; }, setItem() {} },
    setTimeout() { return 0; }, clearTimeout() {}, setInterval() { return 1; }, clearInterval() {},
    L: { map() { return carte; }, layerGroup: couche, canvas: couche, polyline: couche, circleMarker: couche,
      marker: couche, tileLayer: couche, divIcon: couche, control: { layers: couche },
      latLng: (lat, lng) => ({ lat, lng }),
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
  const source = path.join(__dirname, "..", "hike2gpx", "assets", "web", "app.js");
  vm.runInContext(fs.readFileSync(source, "utf8")
    + "\nglobalThis.page = { etat, calculer, planifierCalcul, ajouterPoint, boucler, basculerPleinEcran,"
    + " appliquerLangue, texteErreur, rafraichirCalques, CALQUES, afficherExtrait, afficherErreur };", contexte);
  const derniere = () => requetes.filter((r) => r.url === "/api/itineraire").at(-1);
  return { page: contexte.page, elements, derniere, corps, requetes, carte };
}

function resultat(lonArrivee) {
  return { itineraire: { type: "Feature", properties: {},
    geometry: { type: "LineString", coordinates: [[6, 43.3, 0], [lonArrivee, 43.3, 0]] } },
    franchissements: [], sur_le_trace: [], portions_ign: [], longueur_m: 809, denivele_m: 0, duree_s: 0.1 };
}

const repondre = (requete, corps) => requete.resolve({ ok: true, json: async () => corps });

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
  carte.hasLayer = () => true;
  const calques = () => requetes.filter((r) => /^\/api\/(osm|bdtopo)\?/.test(r.url));
  const premiere = page.rafraichirCalques();
  const [osmA, bdtopoA] = calques();
  assert.equal(osmA.url, "/api/osm?s=43.31000&w=6.01000&n=43.33000&e=6.04000");
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
  assert.deepEqual(JSON.parse(arret.options.body), { calques: ["osm", "bdtopo"] });
});

test("données OSM hors ligne : proposées, téléchargées, installées, et le calcul reprend", async () => {
  const { page, elements, requetes } = charger();
  const texte = () => elements.get("extraitTexte").textContent;
  const nom = "Provence Alpes-Cote-d'Azur";
  page.afficherExtrait({ en_cours: null, propose: { id: "paca", nom, taille_mo: 373, trop_gros: false } });
  assert.equal(elements.get("extraitOsm").hidden, false);
  assert.equal(elements.get("extraitBouton").hidden, false);
  assert.equal(texte(), `Données OSM hors ligne : l'extrait ${nom} (373 Mo) remplacerait Overpass dans cette région.`);
  // Overpass en panne pendant un calcul : la page propose l'extrait, le clic le lance.
  page.afficherErreur({ erreur: "Overpass ne répond pas : barrières non vérifiées (HTTP 502).",
    extrait: { id: "paca", nom, taille_mo: 373, trop_gros: false } });
  assert.equal(page.etat.extraitAttendu, false);
  page.afficherExtrait({ en_cours: { id: "paca", nom, etape: "telechargement", fraction: 0.42, voies: 0 } });
  assert.equal(texte(), `Téléchargement de l'extrait ${nom} : 42 %`);
  assert.equal(elements.get("extraitBouton").hidden, true);
  page.afficherExtrait({ en_cours: { id: "paca", nom, etape: "import", fraction: 1, voies: 210710 } });
  assert.match(texte(), /^Import de l'extrait .* : 210.710 voies lues…$/);
  // Fin : l'extrait sert, et un calcul qui l'attendait repart.
  page.etat.extraitAttendu = true;
  page.afficherExtrait({ en_cours: { id: "paca", nom, etape: "fini", date: "2026-10-18T20:25:06Z" },
    installe: { id: "paca", nom, date: "2026-10-18T20:25:06Z" } });
  assert.equal(texte(), `Données OSM hors ligne : extrait ${nom} du 18/10/2026, renouvelé chaque semaine.`);
  assert.equal(page.etat.extraitAttendu, false);
  page.appliquerLangue("en");
  assert.equal(texte(), `Offline OSM data: ${nom} extract of 18/10/2026, renewed every week.`);
  assert.equal(requetes.filter((r) => r.url === "/api/extrait").length, 0);
});
