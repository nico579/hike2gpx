window.HIKE2GPX_MAP_PROVIDERS.es = {
  defaultBase: "espagne",
  infoBase: { fr: "Carte topographique IGN Espagne", en: "Spanish IGN topographic map" },
  overlays: ["senderos"],
  overlayNames: { senderos: { fr: "Sentiers balisés FEDME", en: "FEDME waymarked trails" } },
  bases({ L }) {
    return { espagne: L.tileLayer(
      "https://www.ign.es/wmts/mapa-raster?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=MTN&STYLE=default&TILEMATRIXSET=GoogleMapsCompatible&FORMAT=image/jpeg&TILEMATRIX={z}&TILECOL={x}&TILEROW={y}",
      { maxNativeZoom: 18, maxZoom: 19, attribution: '© <a href="https://www.ign.es/">IGN España</a>' },
    ) };
  },
  calques: {
    senderos(L) {
      // Le serveur FEDME autorise le CORS : la page lit ses tuiles directement.
      return L.vectorGrid.protobuf("https://vt-fedme.idee.es/vt.senderogr,vt.senderopr,vt.senderosl/{z}/{x}/{y}.pbf", {
        rendererFactory: L.canvas.tile,
        interactive: false,
        minZoom: 8,
        maxNativeZoom: 19,
        maxZoom: 19,
        vectorTileLayerStyles: {
          "vt.senderogr": { color: "#d32f2f", weight: 3, opacity: 0.9 },
          "vt.senderopr": { color: "#e6a000", weight: 3, opacity: 0.9 },
          "vt.senderosl": { color: "#29935d", weight: 3, opacity: 0.9 },
        },
        attribution: '© <a href="https://www.ign.es/">IGN España</a> / FEDME',
      });
    },
  },
};
