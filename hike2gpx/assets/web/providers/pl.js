window.HIKE2GPX_MAP_PROVIDERS.pl = {
  defaultBase: "plTopo",
  infoBase: { fr: "Carte topographique polonaise (Geoportal)", en: "Polish topographic map (Geoportal)" },
  baseNames: { plTopo: { fr: "Carte topographique (Geoportal Pologne)",
    en: "Topographic map (Polish Geoportal)" } },
  paths: {
    overlay: "bdot10k_ds", source: "bdot10k_ds", label: "BDOT10k",
    scope: { fr: "Basse-Silésie", en: "Lower Silesia" },
    name: { fr: "chemins BDOT10k (Basse Silésie)", en: "BDOT10k paths (Lower Silesia)" },
    legend: { fr: "portion sur un chemin BDOT10k absent d'OSM, à vérifier",
              en: "section on a BDOT10k path missing from OSM, to check" },
    gpx: { fr: ", chemins BDOT10k © Geoportal Dolny Śląsk",
           en: ", BDOT10k paths © Geoportal Dolny Śląsk" },
    attribution: '© <a href="https://geoportal.dolnyslask.pl/">Geoportal Dolny Śląsk</a>',
    bounds: [50.0, 14.7, 51.85, 17.85],
    draw({ L, groupe, donnees, rendu, texte }) {
      for (const troncon of donnees.troncons) {
        L.polyline(troncon.pts, { color: "#b04a75", weight: 3, dashArray: "5 4", renderer: rendu })
          .bindTooltip(texte(`${troncon.nature} (BDOT10k)`), { sticky: true }).addTo(groupe);
      }
    },
  },
  bases({ L }) {
    return { plTopo: L.tileLayer.wms(
      "https://mapy.geoportal.gov.pl/wss/service/img/guest/TOPO/MapServer/WMSServer",
      { layers: "Raster", format: "image/png", version: "1.1.1", transparent: false,
        crs: L.CRS.EPSG4326, maxZoom: 19,
        attribution: '© <a href="https://www.geoportal.gov.pl/">GUGiK / Geoportal Polska</a>' }) };
  },
};
