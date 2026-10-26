"use strict";

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { couvertureCartographique } = require("../hike2gpx/assets/web/presentation.js");

const racine = path.resolve(__dirname, "..");
const rapport = path.join(racine, "RAPPORT_SOURCES_CHEMINS_BROUTER.md");
const rapportEn = path.join(racine, "COUNTRY_COVERAGE.md");
const debut = "<!-- DEBUT COUVERTURE PROVIDERS : généré par tools/generer_couverture_pays.cjs -->";
const fin = "<!-- FIN COUVERTURE PROVIDERS -->";

function fournisseurs() {
  const window = { HIKE2GPX_MAP_PROVIDERS: {} };
  const dossier = path.join(racine, "hike2gpx", "assets", "web", "providers");
  for (const nom of fs.readdirSync(dossier).filter(nom => /^[a-z]{2}\.js$/.test(nom)).sort()) {
    vm.runInNewContext(fs.readFileSync(path.join(dossier, nom), "utf8"), { window }, { filename: nom });
  }
  return window.HIKE2GPX_MAP_PROVIDERS;
}

function cellule(valeur) {
  return String(valeur).replaceAll("|", "\\|").replaceAll("\n", " ");
}

function lignesPays(langue) {
  return couvertureCartographique(fournisseurs(), langue).map(({ nom, fond, chemins, itineraire }) =>
    `| ${[nom, fond, chemins, itineraire].map(cellule).join(" | ")} |`);
}

function sectionGeneree() {
  return [debut,
    "", "## Pays pris en charge", "",
    "Ce tableau est généré depuis les fichiers `hike2gpx/assets/web/providers/*.js`. Il décrit séparément le fond de carte national, les calques de chemins et les données ajoutées au calcul BRouter. OpenStreetMap reste disponible partout.",
    "", "| Pays | Fond de carte | Calques de chemins | Calcul d’itinéraire |",
    "| --- | --- | --- | --- |", ...lignesPays("fr"),
    "", "Les chemins officiels sont chargés seulement dans la zone consultée. Pour la Pologne, le calque BDOT10k et son utilisation par BRouter sont limités à la Basse-Silésie. Les sentiers balisés d’Espagne et des États-Unis servent uniquement à l’affichage.",
    "", fin].join("\n");
}

function documentEnglish() {
  return ["# Supported countries", "",
    "This table is generated from `hike2gpx/assets/web/providers/*.js`. It lists each national map, its path layers and the data used by BRouter for route calculation. OpenStreetMap remains available everywhere.",
    "", "| Country | Map base | Path layers | Route calculation |",
    "| --- | --- | --- | --- |", ...lignesPays("en"),
    "", "Official paths are loaded only for the area being viewed. In Poland, the BDOT10k path layer and routing support cover Lower Silesia only. Marked trails in Spain and the United States are display only.",
    "", "For the measurements and source limitations, see the [French report](RAPPORT_SOURCES_CHEMINS_BROUTER.md).",
    ""].join("\n");
}

function main() {
  const contenu = fs.readFileSync(rapport, "utf8");
  const start = contenu.indexOf(debut);
  const end = contenu.indexOf(fin);
  if (start < 0 || end < start) throw new Error("Marqueurs de couverture absents du rapport");
  const attendu = contenu.slice(0, start) + sectionGeneree() + contenu.slice(end + fin.length);
  const anglais = documentEnglish();
  if (process.argv.includes("--check")) {
    if (attendu !== contenu || !fs.existsSync(rapportEn) || fs.readFileSync(rapportEn, "utf8") !== anglais) {
      console.error("Les tableaux FR/EN sont périmés : node tools/generer_couverture_pays.cjs");
      process.exitCode = 1;
    }
  } else {
    fs.writeFileSync(rapport, attendu);
    fs.writeFileSync(rapportEn, anglais);
  }
}

if (require.main === module) main();
module.exports = { sectionGeneree, documentEnglish };
