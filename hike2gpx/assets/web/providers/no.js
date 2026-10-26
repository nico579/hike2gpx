window.HIKE2GPX_MAP_PROVIDERS.no = {
  defaultBase: "norvege",
  infoBase: { fr: "Carte topographique Kartverket", en: "Kartverket topographic map" },
  baseNames: { norvege: { fr: "Carte de randonnée (Kartverket)", en: "Hiking map (Kartverket)" } },
  overlays: [],
  bases({ L }) {
    return { norvege: L.tileLayer(
      "https://cache.kartverket.no/v1/wmts/1.0.0/toporaster/default/webmercator/{z}/{y}/{x}.png",
      { maxNativeZoom: 18, maxZoom: 19,
        attribution: '© <a href="https://www.kartverket.no/">Kartverket</a>' },
    ) };
  },
};
