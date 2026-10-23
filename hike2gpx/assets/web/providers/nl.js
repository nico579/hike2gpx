window.HIKE2GPX_MAP_PROVIDERS.nl = {
  defaultBase: "paysBas",
  overlays: [],
  bases({ L }) {
    return { paysBas: L.tileLayer(
      "https://service.pdok.nl/kadaster/brt-achtergrondkaart/wmts/v2_0/standaard/EPSG:3857/{z}/{x}/{y}.png",
      { maxNativeZoom: 19, maxZoom: 19,
        attribution: '© <a href="https://www.pdok.nl/">Kadaster / PDOK</a>' },
    ) };
  },
};
