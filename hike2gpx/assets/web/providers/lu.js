window.HIKE2GPX_MAP_PROVIDERS.lu = {
  defaultBase: "luxembourg",
  overlays: [],
  bases({ L }) {
    return { luxembourg: L.tileLayer(
      "https://wmts1.geoportail.lu/opendata/wmts/topomap/GLOBAL_WEBMERCATOR/{z}/{x}/{y}.png",
      { maxNativeZoom: 19, maxZoom: 19,
        attribution: '© <a href="https://geoportail.lu/">ACT Luxembourg</a>' },
    ) };
  },
};
