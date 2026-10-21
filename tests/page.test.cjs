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
      enfants: [], ecouteurs: {},
      append(...e) { this.enfants.push(...e); }, replaceChildren(...e) { this.enfants = e; },
      setAttribute(name, value) { this[name] = value; },
      addEventListener(type, f) { (this.ecouteurs[type] ??= []).push(f); }, remove() {}, click() {} };
  };
  const couche = () => ({ addTo() { return this; }, bindPopup() { return this; }, bindTooltip() { return this; },
    on() { return this; }, setIcon() { return this; }, clearLayers() {}, remove() {}, closePopup() {} });
  const carte = { setView() { return this; }, on() {}, createPane() { return { style: {} }; },
    hasLayer() { return false; }, getZoom() { return 14; }, invalidateSize() {},
    vue: { s: 43.31, w: 6.01, n: 43.33, e: 6.04 },
    getBounds() { const v = this.vue; return { getSouth: () => v.s, getWest: () => v.w, getNorth: () => v.n,
      getEast: () => v.e }; } };
  const requetes = [];
  const confirmations = Object.assign([], { reponse: false });
  const corps = element();
  const contexte = vm.createContext({
    console, URL, URLSearchParams, Blob, Date, Number, String, AbortController, performance,
    document: { getElementById(id) { if (!elements.has(id)) elements.set(id, element()); return elements.get(id); },
      createElement: element, createTextNode: String, body: corps, documentElement: element(),
      addEventListener() {}, querySelectorAll() { return []; } },
    localStorage: { getItem() { return null; }, setItem() {} },
    confirm: (texte) => { confirmations.push(texte); return confirmations.reponse; },
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
    + " appliquerLangue, texteErreur, rafraichirCalques, CALQUES, afficherExtrait, afficherErreur,"
    + " debutLecture, finLecture, afficherLectures, afficherDonnees };", contexte);
  const derniere = () => requetes.filter((r) => r.url === "/api/itineraire").at(-1);
  return { page: contexte.page, elements, derniere, corps, requetes, carte, confirmations };
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
  assert.equal(texte(), `Données OSM hors ligne : extrait ${nom} du 18/10/2026, renouvelé chaque semaine.`);
  assert.equal(elements.get("brouterEnCours").hidden, true);
  assert.equal(page.etat.donneesAttendues, false);
  page.appliquerLangue("en");
  assert.equal(texte(), `Offline OSM data: ${nom} extract of 18/10/2026, renewed every week.`);
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
  assert.equal(texte(), `Données OSM hors ligne : extrait ${paca} du 18/10/2026, renouvelé chaque semaine.`);
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
