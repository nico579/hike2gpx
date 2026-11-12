window.HIKE2GPX_MAP_PROVIDERS.pl = {
  defaultBase: "plTopo",
  infoBase: { fr: "Carte topographique polonaise (Geoportal)", en: "Polish topographic map (Geoportal)" },
  baseNames: { plTopo: { fr: "Carte topographique (Geoportal Pologne)",
    en: "Topographic map (Polish Geoportal)" } },
  paths: {
    overlay: "bdot10k_ds", source: "bdot10k_ds", label: "BDOT10k",
    name: { fr: "chemins BDOT10k (Pologne)", en: "BDOT10k paths (Poland)" },
    gpx: { fr: ", chemins BDOT10k © GUGiK", en: ", BDOT10k paths © GUGiK" },
    attribution: '© <a href="https://www.geoportal.gov.pl/">GUGiK / Geoportal Polska</a>',
    draw({ couleur, L, groupe, donnees, rendu, texte }) {
      for (const troncon of donnees.troncons) {
        L.polyline(troncon.pts, { color: couleur, weight: 3, dashArray: "5 4", renderer: rendu })
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
