function tuileIgn(couche, format, cle, matrices = "PM") {
  const base = cle ? "https://data.geopf.fr/private/wmts" : "https://data.geopf.fr/wmts";
  return `${base}?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=${couche}&STYLE=normal`
    + `&TILEMATRIXSET=${matrices}&FORMAT=${format}&TILEMATRIX={z}&TILECOL={x}&TILEROW={y}`
    + (cle ? `&apikey=${encodeURIComponent(cle)}` : "");
}

window.HIKE2GPX_MAP_PROVIDERS.fr = {
  defaultBase: "plan",
  infoBase: { fr: "Plan IGN (SCAN 25 avec clé)", en: "IGN map (SCAN 25 with a key)" },
  baseNames: {
    scan25: { fr: "SCAN 25 (IGN)", en: "SCAN 25 (IGN)" },
    plan: { fr: "Plan IGN", en: "Plan IGN" },
    photos: { fr: "Photos aériennes (IGN)", en: "Aerial photos (IGN)" },
    reliefLidar: { fr: "Relief LiDAR HD (IGN)", en: "LiDAR HD terrain relief (IGN)" },
  },
  texts: {
    fr: { "bdtopo.troncon": "Tronçon", "bdtopo.acces": "accès piéton : {valeur}", "bdtopo.prive": "privé" },
    en: { "bdtopo.troncon": "Section", "bdtopo.acces": "pedestrian access: {valeur}", "bdtopo.prive": "private" },
  },
  serverTexts: { "Chemin de la BD TOPO absent d'OpenStreetMap : existence et accès à vérifier":
    "BD TOPO path missing from OpenStreetMap: existence and access to check",
    "Hors connexion : chemins BD TOPO de cette zone jamais chargés.":
    "Offline: the BD TOPO paths of this area were never loaded." },
  paths: {
    overlay: "bdtopo", source: "ign", label: "IGN",
    legendStyle: { borderTop: "3px dashed #00897b" },
    name: { fr: "Chemins BD TOPO (IGN)", en: "BD TOPO paths (IGN)" },
    routeName: { fr: "chemins BD TOPO (IGN)", en: "BD TOPO paths (IGN)" },
    legend: { fr: "portion sur un chemin IGN absent d'OSM, à vérifier",
              en: "section on an IGN path missing from OSM, to check" },
    gpx: { fr: ", chemins BD TOPO © IGN", en: ", BD TOPO paths © IGN" },
    draw({ L, groupe, donnees, rendu, texte, t }) {
      function style(nature) {
        if (["Sentier", "Chemin", "Escalier"].includes(nature)) return { color: "#00897b", weight: 3, dashArray: "4 4" };
        if (nature === "Route empierrée") return { color: "#00897b", weight: 3 };
        return { color: "#00897b", weight: 2, opacity: 0.45 };
      }
      for (const troncon of donnees.troncons) {
        const details = [troncon.nature || t("bdtopo.troncon")];
        if (troncon.acces_pieton) details.push(t("bdtopo.acces", { valeur: troncon.acces_pieton }));
        if (troncon.prive) details.push(t("bdtopo.prive"));
        L.polyline(troncon.pts, { ...style(troncon.nature), renderer: rendu })
          .bindTooltip(texte(`${details.join(", ")} (BD TOPO)`), { sticky: true }).addTo(groupe);
      }
    },
  },
  bases({ L, cleIgn }) {
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
