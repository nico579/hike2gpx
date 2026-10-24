"use strict";

const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { couvertureCartographique } = require("../hike2gpx/assets/web/presentation.js");

const racine = path.resolve(__dirname, "..");
const rapport = path.join(racine, "RAPPORT_SOURCES_CHEMINS_BROUTER.md");
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

function sectionGeneree() {
  const lignes = couvertureCartographique(fournisseurs(), "fr").map(({ nom, fond, chemins, itineraire }) =>
    `| ${[nom, fond, chemins, itineraire].map(cellule).join(" | ")} |`);
  return [debut,
    "", "## Pays pris en charge", "",
    "Ce tableau est généré depuis les fichiers `hike2gpx/assets/web/providers/*.js`. Il décrit séparément le fond de carte national, les calques de chemins et les données ajoutées au calcul BRouter. OpenStreetMap reste disponible partout.",
    "", "| Pays | Fond de carte | Calques de chemins | Calcul d’itinéraire |",
    "| --- | --- | --- | --- |", ...lignes,
    "", "Les chemins officiels sont chargés seulement dans la zone consultée. Pour la Pologne, le calque BDOT10k et son utilisation par BRouter sont limités à la Basse-Silésie. Les sentiers balisés d’Espagne et des États-Unis servent uniquement à l’affichage.",
    "", fin].join("\n");
}

function main() {
  const contenu = fs.readFileSync(rapport, "utf8");
  const start = contenu.indexOf(debut);
  const end = contenu.indexOf(fin);
  if (start < 0 || end < start) throw new Error("Marqueurs de couverture absents du rapport");
  const attendu = contenu.slice(0, start) + sectionGeneree() + contenu.slice(end + fin.length);
  if (process.argv.includes("--check")) {
    if (attendu !== contenu) {
      console.error("Le tableau des pays est périmé : node tools/generer_couverture_pays.cjs");
      process.exitCode = 1;
    }
  } else {
    fs.writeFileSync(rapport, attendu);
  }
}

if (require.main === module) main();
module.exports = { sectionGeneree };
