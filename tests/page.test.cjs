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
    hasLayer() { return false; }, getZoom() { return 14; } };
  const requetes = [];
  const corps = element();
  const contexte = vm.createContext({
    console, URL, URLSearchParams, Blob, Date, Number, String,
    document: { getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
      createElement: element, createTextNode: String, body: corps },
    localStorage: { getItem() { return null; }, setItem() {} },
    setTimeout() { return 0; }, clearTimeout() {},
    L: { map() { return carte; }, layerGroup: couche, canvas: couche, polyline: couche, circleMarker: couche,
      marker: couche, tileLayer: couche, divIcon: couche, control: { layers: couche },
      latLng: (lat, lng) => ({ lat, lng }) },
    fetch(url, options) { return new Promise((resolve, reject) => requetes.push({ url, options, resolve, reject })); },
  });
  const source = path.join(__dirname, "..", "hike2gpx", "assets", "web", "app.js");
  vm.runInContext(fs.readFileSync(source, "utf8")
    + "\nglobalThis.page = { etat, calculer, planifierCalcul, ajouterPoint, boucler };", contexte);
  const derniere = () => requetes.filter((r) => r.url === "/api/itineraire").at(-1);
  return { page: contexte.page, elements, derniere, corps };
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

test("pointeur d'attente le temps du calcul", async () => {
  const { page, derniere, corps } = charger();
  page.etat.points = [{ lat: 43.3, lon: 6 }, { lat: 43.3, lon: 6.01 }];
  const calcul = page.calculer();
  assert.equal(corps.classList.contains("calcul"), true);
  repondre(derniere(), resultat(6.01));
  await calcul;
  assert.equal(corps.classList.contains("calcul"), false);
});
