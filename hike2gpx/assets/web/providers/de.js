window.HIKE2GPX_MAP_PROVIDERS.de = {
  defaultBase: "allemagne",
  overlays: [],
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
