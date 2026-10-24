window.HIKE2GPX_MAP_PROVIDERS.de = {
  defaultBase: "allemagne",
  paths: {
    overlay: "atkis", source: "atkis", label: "ATKIS",
    legendStatic: true,
    name: { fr: "Chemins ATKIS (Allemagne)", en: "ATKIS paths (Germany)" },
    routeName: { fr: "chemins ATKIS (Allemagne)", en: "ATKIS paths (Germany)" },
    legend: { fr: "portion sur un chemin ATKIS absent d'OSM, à vérifier",
              en: "section on an ATKIS path missing from OSM, to check" },
    gpx: { fr: ", chemins ATKIS © GeoBasis-DE / BKG et Länder",
           en: ", ATKIS paths © GeoBasis-DE / BKG and states" },
    attribution: '© <a href="https://basemap.de/open-data/">GeoBasis-DE / BKG</a> '
      + '(<a href="https://basemap.de/open-data/">licences des Länder</a>), '
      + '<a href="https://geoportal.thueringen.de/">GDI-Th</a> / '
      + '<a href="https://geodatenonline.bayern.de/geodatenonline/seiten/wfs_atkis">BVV</a> '
      + '(<a href="https://creativecommons.org/licenses/by/4.0/">CC BY 4.0</a>)',
    draw({ L, groupe, donnees, rendu, texte, t }) {
      for (const troncon of donnees.troncons) {
        const style = troncon.nature === "Weg/Pfad/Steig"
          ? { color: "#c85508", weight: 3, dashArray: "5 4" }
          : { color: "#c85508", weight: 3, opacity: 0.8 };
        L.polyline(troncon.pts, { ...style, renderer: rendu })
          .bindTooltip(texte(`${troncon.nature || t("atkis.troncon")} (ATKIS ${troncon.land})`),
            { sticky: true }).addTo(groupe);
      }
    },
  },
  bases({ L }) {
    const annee = new Date().getFullYear();
    return { allemagne: L.tileLayer(
      "https://sgx.geodatenzentrum.de/wmts_topplus_open/tile/1.0.0/web/default/WEBMERCATOR/{z}/{y}/{x}.png",
      { maxNativeZoom: 18, maxZoom: 19,
        attribution: `© <a href="https://www.bkg.bund.de/">BKG</a> (${annee}) `
          + '<a href="https://www.govdata.de/dl-de/by-2-0">dl-de/by-2-0</a>, '
          + '<a href="https://sgx.geodatenzentrum.de/web_public/gdz/datenquellen/datenquellen_topplusopen.html">Datenquellen</a>' },
    ) };
  },
};
