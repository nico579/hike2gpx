window.HIKE2GPX_MAP_PROVIDERS.ch = {
  defaultBase: "suisse",
  infoBase: { fr: "Carte nationale swisstopo", en: "swisstopo national map" },
  baseNames: { suisse: { fr: "Carte nationale (swisstopo)", en: "National map (swisstopo)" } },
  overlays: ["suisseSentiers"],
  overlayNames: { suisseSentiers: { fr: "Sentiers de randonnée (swisstopo)", en: "Hiking trails (swisstopo)" } },
  overlayLegendStyles: { suisseSentiers: { borderTop: "3px dashed #e8a619" } },
  paths: {
    legendStyle: { borderTop: "3px dashed #8650ac" },
    overlay: "swisstlm3d", source: "swisstlm3d", label: "swissTLM3D",
    name: { fr: "chemins swissTLM3D (Suisse)", en: "swissTLM3D paths (Switzerland)" },
    legend: { fr: "portion sur un chemin swissTLM3D absent d'OSM, à vérifier",
              en: "section on a swissTLM3D path missing from OSM, to check" },
    gpx: { fr: ", chemins swissTLM3D © swisstopo", en: ", swissTLM3D paths © swisstopo" },
    attribution: '© <a href="https://www.swisstopo.admin.ch/">swisstopo</a>',
    draw({ L, groupe, donnees, rendu, texte }) {
      for (const troncon of donnees.troncons) {
        L.polyline(troncon.pts, { color: "#8650ac", weight: 3, dashArray: "5 4", renderer: rendu })
          .bindTooltip(texte(`${troncon.nature} (swissTLM3D)`), { sticky: true }).addTo(groupe);
      }
    },
  },
  bases({ L }) {
    return { suisse: L.tileLayer(
      "https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.pixelkarte-farbe/default/current/3857/{z}/{x}/{y}.jpeg",
      { maxNativeZoom: 18, maxZoom: 19,
        attribution: '© <a href="https://www.swisstopo.admin.ch/">swisstopo</a>' },
    ) };
  },
  calques: {
    suisseSentiers(L) {
      return L.tileLayer(
        "https://wmts.geo.admin.ch/1.0.0/ch.swisstopo.swisstlm3d-wanderwege/default/current/3857/{z}/{x}/{y}.png",
        { maxNativeZoom: 18, maxZoom: 19, opacity: 0.85,
          attribution: '© <a href="https://www.swisstopo.admin.ch/">swisstopo</a>' },
      );
    },
  },
};
