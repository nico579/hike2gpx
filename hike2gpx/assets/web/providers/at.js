window.HIKE2GPX_MAP_PROVIDERS.at = {
  defaultBase: "autriche",
  infoBase: { fr: "basemap.at", en: "basemap.at" },
  baseNames: { autriche: { fr: "Carte officielle (basemap.at)", en: "Official map (basemap.at)" } },
  overlays: [],
  bases({ L }) {
    return { autriche: L.tileLayer(
      "https://mapsneu.wien.gv.at/basemap/geolandbasemap/normal/google3857/{z}/{y}/{x}.png",
      { maxNativeZoom: 19, maxZoom: 19,
        attribution: '© <a href="https://basemap.at/">basemap.at</a>' },
    ) };
  },
};
