window.HIKE2GPX_MAP_PROVIDERS.fr = {
  defaultBase: "plan",
  overlays: ["bdtopo"],
  routableOverlay: "bdtopo",
  routableName: { fr: "chemins BD TOPO (IGN)", en: "BD TOPO paths (IGN)" },
  bases({ L, cleIgn, tuileIgn }) {
    const ign = '© <a href="https://www.ign.fr/">IGN</a>';
    const fonds = {};
    if (cleIgn) fonds.scan25 = L.tileLayer(
      tuileIgn("GEOGRAPHICALGRIDSYSTEMS.MAPS", "image/jpeg", cleIgn),
      { maxNativeZoom: 16, maxZoom: 19, attribution: ign },
    );
    fonds.plan = L.tileLayer(tuileIgn("GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2", "image/png"),
      { maxNativeZoom: 18, maxZoom: 19, attribution: ign });
    fonds.photos = L.tileLayer(tuileIgn("ORTHOIMAGERY.ORTHOPHOTOS", "image/jpeg"),
      { maxNativeZoom: 19, maxZoom: 19, attribution: ign });
    fonds.reliefLidar = L.tileLayer(
      tuileIgn("IGNF_LIDAR-HD_MNT_ELEVATION.ELEVATIONGRIDCOVERAGE.SHADOW", "image/png", null, "PM_0_18"),
      { maxNativeZoom: 18, maxZoom: 19, attribution: ign },
    );
    return fonds;
  },
};
