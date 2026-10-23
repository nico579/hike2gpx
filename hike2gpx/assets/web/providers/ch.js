window.HIKE2GPX_MAP_PROVIDERS.ch = {
  defaultBase: "suisse",
  overlays: ["suisseSentiers"],
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
