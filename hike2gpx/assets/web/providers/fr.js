window.HIKE2GPX_MAP_PROVIDERS.fr = {
  defaultBase: "plan",
  paths: {
    overlay: "bdtopo", source: "ign", label: "IGN",
    legendStatic: true,
    name: { fr: "Chemins BD TOPO (IGN)", en: "BD TOPO paths (IGN)" },
    routeName: { fr: "chemins BD TOPO (IGN)", en: "BD TOPO paths (IGN)" },
    legend: { fr: "portion sur un chemin IGN absent d'OSM, à vérifier",
              en: "section on an IGN path missing from OSM, to check" },
    gpx: { fr: ", chemins BD TOPO © IGN", en: ", BD TOPO paths © IGN" },
    draw({ L, groupe, donnees, rendu, texte, t, styleBdtopo }) {
      for (const troncon of donnees.troncons) {
        const details = [troncon.nature || t("bdtopo.troncon")];
        if (troncon.acces_pieton) details.push(t("bdtopo.acces", { valeur: troncon.acces_pieton }));
        if (troncon.prive) details.push(t("bdtopo.prive"));
        L.polyline(troncon.pts, { ...styleBdtopo(troncon.nature), renderer: rendu })
          .bindTooltip(texte(`${details.join(", ")} (BD TOPO)`), { sticky: true }).addTo(groupe);
      }
    },
  },
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
