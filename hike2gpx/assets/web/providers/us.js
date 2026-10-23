window.HIKE2GPX_MAP_PROVIDERS.us = {
  defaultBase: "etatsUnis",
  overlays: ["npsSentiers"],
  bases({ L }) {
    return { etatsUnis: L.tileLayer(
      "https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/tile/{z}/{y}/{x}",
      { maxNativeZoom: 16, maxZoom: 19,
        attribution: '© <a href="https://www.usgs.gov/programs/national-geospatial-program/national-map">USGS The National Map</a>' },
    ) };
  },
  calques: {
    npsSentiers(L) {
      const style = encodeURIComponent(JSON.stringify([{
        id: 0,
        source: { type: "mapLayer", mapLayerId: 0 },
        drawingInfo: { renderer: { type: "simple", symbol: {
          type: "esriSLS", style: "esriSLSSolid", color: [255, 150, 0, 255], width: 2,
        } } },
      }]));
      const couche = L.tileLayer("", {
        maxNativeZoom: 16, maxZoom: 19,
        attribution: '© <a href="https://www.nps.gov/subjects/gisandmapping/index.htm">National Park Service</a>',
      });
      couche.getTileUrl = function (coords) {
        const taille = this.getTileSize();
        const nordOuest = this._map.unproject(L.point(coords.x * taille.x, coords.y * taille.y), coords.z);
        const sudEst = this._map.unproject(L.point((coords.x + 1) * taille.x, (coords.y + 1) * taille.y), coords.z);
        const basGauche = L.CRS.EPSG3857.project(L.latLng(sudEst.lat, nordOuest.lng));
        const hautDroit = L.CRS.EPSG3857.project(L.latLng(nordOuest.lat, sudEst.lng));
        const bbox = [basGauche.x, basGauche.y, hautDroit.x, hautDroit.y].join(",");
        return "https://mapservices.nps.gov/arcgis/rest/services/NationalDatasets/NPS_Public_Trails/MapServer/export"
          + `?bbox=${bbox}&bboxSR=3857&imageSR=3857&size=256%2C256&format=png32&transparent=true&dynamicLayers=${style}&f=image`;
      };
      return couche;
    },
  },
};
