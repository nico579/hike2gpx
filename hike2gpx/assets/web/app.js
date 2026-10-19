"use strict";

// Page de tracé de hike2gpx : points posés sur la carte, itinéraire calculé
// par le serveur local (BRouter et les coupes des franchissements), export
// GPX. Les textes venus d'OpenStreetMap passent toujours par textContent.

const DELAI_CALCUL_MS = 250;
const CLE_VUE = "hike2gpx.vue";
const COULEURS = { blocked: "#d32f2f", uncertain: "#ef6c00" };

const etat = { points: [], sequence: 0, minuterie: null, dernier: null, cleIgn: "", version: "", sequenceDenivele: 0 };
const $ = (id) => document.getElementById(id);

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

function afficherStatut(texte, erreur = false) {
  $("statut").textContent = texte;
  $("statut").classList.toggle("erreur", erreur);
}

function km(metres) {
  return metres == null ? "?" : `${(metres / 1000).toFixed(2).replace(".", ",")} km`;
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
carte.on("baselayerchange", (e) => { fondActif = e.layer; });

// ------------------------------------------------------------ calques de chemins

// Le tracé et ses franchissements passent au-dessus des chemins dessinés.
carte.createPane("trace").style.zIndex = 450;
const rendu = L.canvas({ padding: 0.2 });
const ZOOM_CALQUES = 14;
const CLE_CALQUES = "hike2gpx.calques";
const CALQUES = {
  osm: { nom: "Chemins OSM", groupe: L.layerGroup(), charge: null, sequence: 0 },
  bdtopo: { nom: "Chemins BD TOPO (IGN)", groupe: L.layerGroup(), charge: null, sequence: 0 },
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
        .bindTooltip(texte(`${b.nature} (OSM)`), { sticky: true }).addTo(groupe);
    }
  },
  bdtopo(groupe, donnees) {
    for (const t of donnees.troncons) {
      const details = [t.nature || "Tronçon"];
      if (t.acces_pieton) details.push(`accès piéton : ${t.acces_pieton}`);
      if (t.prive) details.push("privé");
      L.polyline(t.pts, { ...styleBdtopo(t.nature), renderer: rendu })
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
  const parametres = new URLSearchParams(Object.entries(zone).map(([k, v]) => [k, v.toFixed(5)]));
  noteCalques(`Chargement des ${calque.nom.charAt(0).toLowerCase()}${calque.nom.slice(1)}… (la première fois, jusqu'à une minute)`);
  let donnees;
  try {
    donnees = await api(`${cle}?${parametres}`);
  } catch (e) {
    if (numero === calque.sequence) noteCalques(`${calque.nom} : ${e.message}`);
    return;
  }
  if (numero !== calque.sequence || !carte.hasLayer(calque.groupe)) return;
  if (donnees.erreur) {
    noteCalques(`${calque.nom} : ${donnees.erreur}`);
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
    noteCalques(`Zoomez davantage (niveau ${ZOOM_CALQUES}) pour voir les chemins.`);
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

function construireFonds() {
  const fonds = {};
  if (etat.cleIgn) {
    fonds["SCAN 25 (IGN)"] = L.tileLayer(tuileIgn("GEOGRAPHICALGRIDSYSTEMS.MAPS", "image/jpeg", etat.cleIgn),
      { maxNativeZoom: 16, maxZoom: 19, attribution: IGN });
  }
  fonds["Plan IGN"] = L.tileLayer(tuileIgn("GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2", "image/png"),
    { maxNativeZoom: 18, maxZoom: 19, attribution: IGN });
  fonds["Photos aériennes (IGN)"] = L.tileLayer(tuileIgn("ORTHOIMAGERY.ORTHOPHOTOS", "image/jpeg"),
    { maxNativeZoom: 19, maxZoom: 19, attribution: IGN });
  fonds["OpenStreetMap"] = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    { maxNativeZoom: 19, maxZoom: 19,
      attribution: '© <a href="https://www.openstreetmap.org/copyright">contributeurs OpenStreetMap</a>' });
  if (controleFonds) controleFonds.remove();
  if (fondActif) fondActif.remove();
  fondActif = Object.values(fonds)[0].addTo(carte);
  const calques = Object.fromEntries(Object.values(CALQUES).map((c) => [c.nom, c.groupe]));
  controleFonds = L.control.layers(fonds, calques, { collapsed: false, position: "topright" }).addTo(carte);
}

// ------------------------------------------------------------ points

const couches = L.layerGroup().addTo(carte);

function icone(rang, total) {
  const depart = rang === 0;
  const arrivee = total > 1 && rang === total - 1;
  return L.divIcon({
    className: `point${depart ? " depart" : arrivee ? " arrivee" : ""}`,
    html: depart ? "D" : arrivee ? "A" : String(rang),
    iconSize: [24, 24],
  });
}

function rafraichirPoints() {
  etat.points.forEach((p, rang) => p.marqueur.setIcon(icone(rang, etat.points.length)));
  $("retirerDernier").disabled = etat.points.length === 0;
  $("toutEffacer").disabled = etat.points.length === 0;
}

function bullePoint(point) {
  const div = document.createElement("div");
  div.className = "bulle";
  const bouton = document.createElement("button");
  bouton.type = "button";
  bouton.textContent = "Retirer ce point";
  bouton.addEventListener("click", () => retirerPoint(point));
  div.append(bouton);
  return div;
}

function ajouterPoint(latlng) {
  const point = { lat: latlng.lat, lon: latlng.lng };
  point.marqueur = L.marker(latlng, { draggable: true, keyboard: false, icon: icone(0, 1) }).addTo(carte);
  point.marqueur.on("dragend", () => {
    const position = point.marqueur.getLatLng();
    point.lat = position.lat;
    point.lon = position.lng;
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

function planifierCalcul() {
  clearTimeout(etat.minuterie);
  etat.minuterie = setTimeout(calculer, DELAI_CALCUL_MS);
}

function effacerResultat() {
  couches.clearLayers();
  etat.dernier = null;
  $("resultat").hidden = true;
  $("exporter").disabled = true;
}

async function calculer() {
  const numero = ++etat.sequence;
  $("actions").replaceChildren();
  if (etat.points.length < 2) {
    effacerResultat();
    afficherStatut(etat.points.length ? "Posez un deuxième point." : "");
    return;
  }
  afficherStatut("Calcul en cours… La première fois dans une zone, la lecture des barrières OSM prend jusqu'à une minute"
    + ($("ign").checked ? ", puis la fusion avec les chemins IGN quelques secondes." : "."));
  let reponse;
  try {
    reponse = await api("itineraire", {
      points: etat.points.map((p) => [p.lat, p.lon]),
      strict: $("strict").checked,
      ign: $("ign").checked,
      comparer: $("comparer").checked,
    });
  } catch (e) {
    if (numero === etat.sequence) afficherStatut(`Erreur : ${e.message}`, true);
    return;
  }
  if (numero !== etat.sequence) return;   // un calcul plus récent est en route
  if (reponse.erreur) afficherErreur(reponse);
  else afficher(reponse);
}

function boutonAction(texte, action) {
  const bouton = document.createElement("button");
  bouton.type = "button";
  bouton.textContent = texte;
  bouton.addEventListener("click", async () => {
    bouton.disabled = true;
    try {
      await action();
    } catch (e) {
      afficherStatut(`Erreur : ${e.message}`, true);
    } finally {
      bouton.disabled = false;
    }
  });
  return bouton;
}

function proposerInstallation() {
  $("actions").append(boutonAction("Installer le moteur BRouter (7 Mo)", async () => {
    afficherStatut("Installation de BRouter…");
    const r = await api("moteur", {});
    if (r.erreur) afficherStatut(r.erreur, true);
    else { $("actions").replaceChildren(); afficherStatut("BRouter installé."); planifierCalcul(); }
  }));
}

function afficherErreur(reponse) {
  effacerResultat();
  afficherStatut(reponse.erreur, true);
  for (const nom of reponse.segments_manquants || []) {
    $("actions").append(boutonAction(`Télécharger les données BRouter ${nom} (70 à 250 Mo)`, async () => {
      afficherStatut(`Téléchargement de ${nom}…`);
      const r = await api("segment", { nom });
      if (r.erreur) afficherStatut(r.erreur, true);
      else planifierCalcul();
    }));
  }
  if (reponse.moteur_absent) proposerInstallation();
}

function lignes(feature) {
  return feature.geometry.coordinates.map((c) => [c[1], c[0]]);
}

function paragraphe(texte, gras = false) {
  const p = document.createElement("p");
  if (gras) {
    const fort = document.createElement("strong");
    fort.textContent = texte;
    p.append(fort);
  } else {
    p.textContent = texte;
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
  lien.textContent = "Voir dans OpenStreetMap";
  div.append(paragraphe(`${f.nature} : ${f.statut === "blocked" ? "bloquant" : "à vérifier"}`, true),
             paragraphe(f.raison));
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
  $("distance").textContent = km(r.longueur_m);
  $("denivele").textContent = r.denivele_m == null ? "?" : `+${Math.round(r.denivele_m)} m`;
  $("sourceDenivele").textContent = "Estimation de BRouter ; calcul de gpx2elev en cours…";
  calculerDenivele(r);
  const n = (r.naif_traverse || []).length;
  $("comparaison").textContent = !r.naif ? "" :
    `Le tracé standard (profil Randonnée de BRouter, sans les barrières) mesure ${km(r.naif_longueur_m)}`
    + (n ? ` et traverse ${n} franchissement${n > 1 ? "s" : ""} bloquant${n > 1 ? "s" : ""}.`
         : " et ne traverse aucun franchissement bloquant connu.");
  const liste = $("aVerifier");
  liste.replaceChildren();
  for (const f of r.sur_le_trace) {
    const li = document.createElement("li");
    li.textContent = `${km(f.distance_m)} : ${f.nature}, ${f.raison.charAt(0).toLowerCase()}${f.raison.slice(1)}`;
    li.title = "Centrer la carte sur ce point";
    li.addEventListener("click", () => carte.setView([f.lat, f.lon], Math.max(carte.getZoom(), 17)));
    liste.append(li);
  }
  $("aucunAVerifier").hidden = r.sur_le_trace.length > 0;
  $("resultat").hidden = false;
  $("exporter").disabled = false;
  const total = r.franchissements.length;
  const bilan = `Calculé en ${String(r.duree_s).replace(".", ",")} s ; ${total} franchissement${total > 1 ? "s" : ""} connu${total > 1 ? "s" : ""} dans la zone examinée.`;
  // Repli sur OSM seul : les chemins IGN demandés n'ont pas pu servir, il faut le voir.
  afficherStatut(r.avertissement ? `${r.avertissement} ${bilan}` : bilan, Boolean(r.avertissement));
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
    $("sourceDenivele").textContent = `Estimation de BRouter ; gpx2elev indisponible : ${d.erreur}`;
    return;
  }
  r.denivele = d;
  $("denivele").textContent = `+${d.montee_m} m, −${d.descente_m} m`;
  $("sourceDenivele").textContent = `gpx2elev, ${d.modele} : échantillonnage 5 m, lissage 20 m, `
    + `hystérésis 2 m ; altitude de ${d.altitude_min_m} à ${d.altitude_max_m} m.`;
}

// ------------------------------------------------------------ GPX

function echapper(texte) {
  return String(texte).replace(/[<>&'"]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;", "'": "&apos;", '"': "&quot;" }[c]));
}

function descriptionGpx(r) {
  const denivele = r.denivele
    ? `D+ ${r.denivele.montee_m} m, D- ${r.denivele.descente_m} m (gpx2elev, ${r.denivele.modele})`
    : `D+ ${Math.round(r.denivele_m ?? 0)} m (estimation BRouter)`;
  const aVerifier = r.sur_le_trace.length;
  return `Distance ${km(r.longueur_m)}, ${denivele}, ${aVerifier} passage${aVerifier > 1 ? "s" : ""} à vérifier. `
    + "Barrières © contributeurs OpenStreetMap"
    + ((r.portions_ign || []).length ? ", chemins BD TOPO © IGN" : "") + " ; tracé hike2gpx.";
}

function gpx(r) {
  const nom = `hike2gpx ${new Date().toLocaleDateString("fr-FR")}`;
  const wpt = r.sur_le_trace.map((f) => `  <wpt lat="${f.lat}" lon="${f.lon}"><name>${echapper(`À vérifier : ${f.nature}`)}</name>`
    + `<desc>${echapper(f.raison)}</desc><type>${f.statut === "blocked" ? "bloquant" : "a_verifier"}</type></wpt>\n`);
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
$("toutEffacer").addEventListener("click", () => {
  etat.points.forEach((p) => p.marqueur.remove());
  etat.points = [];
  rafraichirPoints();
  planifierCalcul();
});
$("exporter").addEventListener("click", exporter);
$("strict").addEventListener("change", planifierCalcul);
$("ign").addEventListener("change", planifierCalcul);
$("comparer").addEventListener("change", planifierCalcul);
$("enregistrerCle").addEventListener("click", async () => {
  try {
    const r = await api("reglages", { cle_ign: $("cleIgn").value });
    if (r.erreur) { afficherStatut(r.erreur, true); return; }
    etat.cleIgn = r.cle_ign;
    construireFonds();
    afficherStatut(etat.cleIgn ? "Clé enregistrée : SCAN 25 disponible." : "Clé retirée : Plan IGN par défaut.");
  } catch (e) {
    afficherStatut(`Erreur : ${e.message}`, true);
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
      afficherStatut("Le moteur BRouter n'est pas encore installé.", true);
      proposerInstallation();
    }
  } catch (e) {
    afficherStatut(`Serveur injoignable : ${e.message}`, true);
  }
  restaurerCalques();     // avant le contrôle des fonds, pour que ses cases soient cochées
  construireFonds();
  rafraichirCalques();
}

demarrer();
