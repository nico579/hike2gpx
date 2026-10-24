window.HIKE2GPX_MAP_PROVIDERS.cz = {
  defaultBase: "tchequie",
  infoBase: { fr: "Carte ZTM (ČÚZK)", en: "ZTM map (ČÚZK)" },
  baseNames: { tchequie: { fr: "Carte topographique (ČÚZK)", en: "Topographic map (ČÚZK)" } },
  paths: {
    overlay: "zabaged", source: "zabaged", label: "ZABAGED",
    name: { fr: "chemins ZABAGED (Tchéquie)", en: "ZABAGED paths (Czechia)" },
    legend: { fr: "portion sur un chemin ZABAGED absent d'OSM, à vérifier",
              en: "section on a ZABAGED path missing from OSM, to check" },
    gpx: { fr: ", chemins ZABAGED © ČÚZK", en: ", ZABAGED paths © ČÚZK" },
    attribution: '© <a href="https://www.cuzk.gov.cz/">ČÚZK</a>',
    draw({ L, groupe, donnees, rendu, texte }) {
      for (const troncon of donnees.troncons) {
        L.polyline(troncon.pts, { color: "#aa6b13", weight: 3, dashArray: "5 4", renderer: rendu })
          .bindTooltip(texte(`${troncon.nature} (ZABAGED)`), { sticky: true }).addTo(groupe);
      }
    },
  },
  bases({ L }) {
    return { tchequie: L.tileLayer(
      "https://ags.cuzk.gov.cz/arcgis1/rest/services/ZTM_WM/MapServer/tile/{z}/{y}/{x}",
      { maxNativeZoom: 18, maxZoom: 19,
        attribution: '© <a href="https://www.cuzk.gov.cz/">ČÚZK</a>' },
    ) };
  },
};
