/* Présentation de la page ; le moteur de tracé reste app.js. */
function couvertureCartographique(providers, langue) {
  const noms = new Intl.DisplayNames([langue], { type: "region" });
  return Object.entries(providers)
    .filter(([code]) => code !== "autre")
    .map(([code, provider]) => {
      const chemins = [
        ...(provider.paths?.overlay ? [provider.paths.name[langue]] : []),
        ...(provider.overlays || []).map(cle => provider.overlayNames?.[cle]?.[langue] || cle),
      ];
      const source = provider.paths?.source;
      const nomSource = provider.paths?.label || source;
      const region = provider.paths?.scope?.[langue];
      return {
        code,
        nom: noms.of(code.toUpperCase()),
        fond: provider.infoBase?.[langue] || provider.defaultBase,
        chemins: chemins.length ? chemins.join(" · ") : "OSM",
        itineraire: source ? `OSM + ${nomSource}${region ? ` (${region})` : ""}` : "OSM",
      };
    })
    .sort((a, b) => a.nom.localeCompare(b.nom, langue));
}
function lienCouverturePays(langue) {
  return langue === "en" ? "/documentation/pays?lang=en" : "/documentation/pays";
}
if (typeof module !== "undefined") module.exports = { couvertureCartographique, lienCouverturePays };
(() => {
  if (typeof document === "undefined") return;
  // Les pages du menu : chaque entrée [data-pane] ouvre la sienne dans le panneau.
  const tabs = [...document.querySelectorAll("[data-pane]")];
  const pageNames = tabs.map(tab => tab.dataset.pane);
  const panel = document.getElementById("panneau");
  const pageTitle = document.getElementById("pageTitre");
  const pagePreference = "hike2gpx.page";
  const transparencySlider = document.getElementById("panelTransparency");
  const transparencyValue = document.getElementById("panelTransparencyValue");
  const transparencyPreference = "hike2gpx.panelTransparency";
  function setTransparency(value, remember = false) {
    const parsed = Number(value);
    const transparency = Number.isFinite(parsed) ? Math.max(0, Math.min(80, Math.round(parsed))) : 45;
    transparencySlider.value = String(transparency);
    transparencyValue.textContent = `${transparency} %`;
    document.documentElement.style.setProperty("--band-opacity", String(1 - transparency / 100));
    if (remember) {
      try { localStorage.setItem(transparencyPreference, String(transparency)); } catch (error) {}
    }
  }
  let savedTransparency = transparencySlider.value;
  try { savedTransparency = localStorage.getItem(transparencyPreference) ?? savedTransparency; } catch (error) {}
  setTransparency(savedTransparency);
  transparencySlider.addEventListener("input", () => setTransparency(transparencySlider.value, true));
  // Sans page ouverte, le panneau s'efface : la carte reste seule, comme sur le téléphone.
  function setPanelCollapsed(collapsed) {
    document.body.classList.toggle("panel-collapsed", collapsed);
    panel.toggleAttribute("inert", collapsed);
    panel.setAttribute("aria-hidden", String(collapsed));
    setTimeout(() => window.dispatchEvent(new Event("resize")), 260);
  }
  // Les états réels de app.js restent visibles sur la carte, quelle que soit la page.
  const activity = document.getElementById("mapActivity");
  const activityRows = document.getElementById("mapActivityRows");
  const jobs = [
    ["Chemins de la carte", "noteCalques", "noteCalquesTexte", "noteCalquesPiste", "noteCalquesBarre"],
    ["Extrait OSM", "extraitOsm", "extraitTexte", "extraitPiste", "extraitBarre"],
    ["BRouter", "brouterEnCours", "brouterTexte", "brouterPiste", "brouterBarre"],
    ["Calcul du parcours", "progression", "progressionTexte", "progression", "progressionBarre"],
    ["Lot hors ligne", "lotHorsLigne", "lotHorsLigneTexte", "lotHorsLignePiste", "lotHorsLigneBarre"],
  ].map(([label, sourceId, textId, trackId, barId]) => {
    const row = document.createElement("div");
    row.className = "map-activity-row";
    row.hidden = true;
    const title = document.createElement("strong");
    title.textContent = label;
    const message = document.createElement("p");
    const track = document.createElement("span");
    track.className = "piste";
    track.setAttribute("role", "progressbar");
    track.setAttribute("aria-label", label);
    const bar = document.createElement("span");
    bar.className = "barre";
    track.append(bar);
    row.append(title, message, track);
    activityRows.append(row);
    return { source: document.getElementById(sourceId), text: document.getElementById(textId),
      sourceTrack: document.getElementById(trackId), sourceBar: document.getElementById(barId),
      row, message, track, bar };
  });
  function refreshActivity() {
    const wasVisible = !activity.hidden;
    let visible = false;
    for (const job of jobs) {
      const active = !job.source.hidden && !job.sourceTrack.hidden;
      job.row.hidden = !active;
      if (!active) continue;
      visible = true;
      job.message.textContent = job.text.textContent;
      const indeterminate = job.sourceTrack.classList.contains("indeterminee") || job.source.id === "brouterEnCours";
      job.track.classList.toggle("indeterminee", indeterminate);
      const width = job.sourceBar.style.width || "0%";
      job.bar.style.width = indeterminate ? "" : width;
      if (indeterminate) job.track.removeAttribute("aria-valuenow");
      else job.track.setAttribute("aria-valuenow", String(parseInt(width, 10) || 0));
      job.track.setAttribute("aria-valuetext", job.message.textContent);
    }
    activity.hidden = !visible;
    if (!visible && wasVisible) chargerDonnees();
  }
  for (const job of jobs) {
    new MutationObserver(refreshActivity).observe(job.source,
      { attributes: true, childList: true, characterData: true, subtree: true });
  }
  refreshActivity();
  // Le volet des tuiles hors ligne : un seul bloc, que « Gestion des cartes »
  // ouvre pour les fonds (carrés de 1°) et « Gestion des itinéraires » pour le
  // routage (cases de 5°). Ouvert, app.js affiche la grille sur la carte.
  const offline = document.getElementById("horsLigne");
  const offlineButtons = [...document.querySelectorAll(".hl-ouvrir")];
  function setOffline(mode) {
    for (const button of offlineButtons) {
      const open = button.dataset.hlMode === mode;
      button.setAttribute("aria-expanded", String(open));
      button.dataset.i18n = open ? "horsLigne.terminer" : button.dataset.hlTexte;
      button.textContent = t(button.dataset.i18n);
      if (!open) continue;
      button.after(offline);
      // Le mode qui compte est celui d'app.js (horsLigne.mode), pas la case :
      // au rechargement, le navigateur restaure la case sans prévenir personne.
      const radio = document.getElementById(mode === "fond" ? "hlFond" : "hlRoutage");
      radio.checked = true;
      if (horsLigne.mode !== mode) radio.dispatchEvent(new Event("change"));
    }
    offline.hidden = !mode;
  }
  for (const button of offlineButtons) {
    button.addEventListener("click", () =>
      setOffline(button.getAttribute("aria-expanded") === "true" ? "" : button.dataset.hlMode));
  }
  // Une page du menu, ou aucune ("") : la carte seule.
  function selectPane(name, remember = true) {
    const open = pageNames.includes(name);
    for (const tab of tabs) {
      const selected = tab.dataset.pane === name;
      if (selected) tab.setAttribute("aria-current", "page");
      else tab.removeAttribute("aria-current");
      document.getElementById(`pane-${tab.dataset.pane}`).hidden = !selected;
    }
    setOffline("");
    if (open) {
      pageTitle.dataset.i18n = `menu.${name}`;
      pageTitle.textContent = t(`menu.${name}`);
    }
    setPanelCollapsed(!open);
    panel.querySelector(".panel-scroll").scrollTop = 0;
    if (name === "reglages") chargerDonnees();
    document.body.classList.toggle("sheet-expanded", open && innerWidth <= 700 && name !== "trace");
    if (remember) {
      try { localStorage.setItem(pagePreference, open ? name : ""); } catch (error) {}
    }
  }
  // Le menu : un bouton à trois traits sur la carte, puis une entrée par page.
  const menuButton = document.getElementById("menuButton");
  const menu = document.getElementById("menuPrincipal");
  const menuBackdrop = document.getElementById("menuFond");
  function setMenuOpen(open) {
    menu.hidden = !open;
    menuBackdrop.hidden = !open;
    menuButton.setAttribute("aria-expanded", String(open));
    if (open) menu.querySelector(".menu-entry").focus();
  }
  // Ces éléments sont posés sur la carte : un clic dessus ne doit ni poser un
  // point ni déplacer la carte. C'est l'idiome de Leaflet pour ses contrôles.
  for (const element of [menuButton, menu, menuBackdrop]) {
    L.DomEvent.disableClickPropagation(element);
    L.DomEvent.disableScrollPropagation(element);
  }
  menuButton.addEventListener("click", () => setMenuOpen(menu.hidden));
  menuBackdrop.addEventListener("click", () => setMenuOpen(false));
  document.getElementById("aide").addEventListener("click", () => setMenuOpen(false));
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && !menu.hidden) {
      setMenuOpen(false);
      menuButton.focus();
    }
  });
  for (const tab of tabs) {
    tab.addEventListener("click", () => {
      setMenuOpen(false);
      selectPane(tab.dataset.pane);
    });
  }
  document.getElementById("pageFermer").addEventListener("click", () => {
    selectPane("");
    menuButton.focus();
  });
  // « Recherche » montre ou replie le champ, en haut de la carte.
  const search = document.getElementById("citySearch");
  const searchEntry = document.getElementById("menuRecherche");
  const searchPreference = "hike2gpx.searchOpen";
  function setSearchOpen(open, remember = false) {
    search.hidden = !open;
    searchEntry.setAttribute("aria-pressed", String(open));
    if (!remember) return;
    if (open) document.getElementById("cityQuery").focus();
    try { localStorage.setItem(searchPreference, String(open)); } catch (error) {}
  }
  searchEntry.addEventListener("click", () => {
    setMenuOpen(false);
    setSearchOpen(search.hidden, true);
  });
  try { setSearchOpen(localStorage.getItem(searchPreference) === "true"); }
  catch (error) { setSearchOpen(false); }
  let savedPage = "";
  try { savedPage = localStorage.getItem(pagePreference) || ""; } catch (error) {}
  selectPane(savedPage, false);
  // Un premier point posé sur la carte seule ouvre « Planifier un itinéraire » :
  // ses boutons et l'état du calcul sont là.
  const removeLast = document.getElementById("retirerDernier");
  new MutationObserver(() => {
    if (!removeLast.disabled && document.body.classList.contains("panel-collapsed")) selectPane("trace");
  }).observe(removeLast, { attributes: true, attributeFilter: ["disabled"] });
  const routeSummary = document.getElementById("routeSummary");
  const result = document.getElementById("resultat");
  const elevationPanel = document.getElementById("elevationPanel");
  const elevationToggle = document.getElementById("elevationToggle");
  const elevationContent = document.getElementById("elevationContent");
  const hideElevation = document.getElementById("hideElevation");
  const elevationVisibilityPreference = "hike2gpx.hideElevation";
  try { hideElevation.checked = localStorage.getItem(elevationVisibilityPreference) === "true"; } catch (error) {}
  const profilePreference = "hike2gpx.profileCollapsed";
  try { elevationContent.hidden = localStorage.getItem(profilePreference) === "true"; } catch (error) {}
  elevationToggle.setAttribute("aria-expanded", String(!elevationContent.hidden));
  const profileSvg = document.getElementById("elevationProfile");
  const profileSource = document.getElementById("profileSource");
  const profileReadout = document.getElementById("profileReadout");
  const profileAxis = document.getElementById("profileAxis");
  const profileCursor = document.getElementById("profileCursor");
  const profileCursorPoint = document.getElementById("profileCursorPoint");
  let profilePoints = [];
  let scaledPoints = [];
  let cursorIndex = 0;
  function hideProfileCursor() {
    profileCursor.setAttribute("hidden", "");
    profileCursorPoint.setAttribute("hidden", "");
    profileReadout.textContent = "";
    document.dispatchEvent(new CustomEvent("hike2gpx:profil-position", { detail: null }));
  }
  const collapsedDistance = document.getElementById("collapsedDistance");
  const collapsedElevation = document.getElementById("collapsedElevation");
  function syncCollapsedMetrics() {
    collapsedDistance.textContent = document.getElementById("distance").textContent || "—";
    collapsedElevation.textContent = document.getElementById("denivele").textContent || "—";
  }
  for (const id of ["distance", "denivele"]) {
    new MutationObserver(syncCollapsedMetrics).observe(document.getElementById(id),
      { childList: true, characterData: true, subtree: true });
  }
  syncCollapsedMetrics();
  function syncProfileHeight() {
    const visible = !elevationPanel.hidden && !hideElevation.checked;
    document.body.classList.toggle("profile-open", visible && !elevationContent.hidden);
    document.body.classList.toggle("profile-collapsed", visible && elevationContent.hidden);
  }
  function syncElevationVisibility() {
    document.body.classList.toggle("hide-elevation", hideElevation.checked);
    elevationPanel.toggleAttribute("inert", hideElevation.checked);
    elevationPanel.setAttribute("aria-hidden", String(hideElevation.checked));
    if (hideElevation.checked) hideProfileCursor();
    syncProfileHeight();
  }
  hideElevation.addEventListener("change", () => {
    try { localStorage.setItem(elevationVisibilityPreference, String(hideElevation.checked)); } catch (error) {}
    syncElevationVisibility();
  });
  syncElevationVisibility();
  function syncRoute() {
    // L'export est désactivé dès qu'un point change, pendant que le nouveau
    // parcours se calcule. Garder le profil précédent en place jusque-là.
    const ready = !result.hidden;
    const wasVisible = !elevationPanel.hidden;
    routeSummary.hidden = !ready;
    elevationPanel.hidden = !ready;
    if (!ready) {
      profilePoints = [];
      profileSvg.setAttribute("hidden", "");
      profileAxis.hidden = true;
      hideProfileCursor();
    } else if (!wasVisible) {
      profileSource.textContent = t("profil.attente");
      profileReadout.textContent = "";
      document.getElementById("elevationRange").textContent = "";
    }
    syncProfileHeight();
  }
  new MutationObserver(syncRoute).observe(result, { attributes: true, attributeFilter: ["hidden"] });
  elevationToggle.addEventListener("click", () => {
    elevationContent.hidden = !elevationContent.hidden;
    if (elevationContent.hidden) hideProfileCursor();
    elevationToggle.setAttribute("aria-expanded", String(!elevationContent.hidden));
    try { localStorage.setItem(profilePreference, String(elevationContent.hidden)); } catch (error) {}
    syncProfileHeight();
  });
  for (const eventName of ["click", "mousedown", "dblclick"]) {
    elevationPanel.addEventListener(eventName, event => event.stopPropagation());
  }
  function showCursor(index) {
    if (!scaledPoints.length) return;
    cursorIndex = Math.max(0, Math.min(scaledPoints.length - 1, index));
    const [x, y] = scaledPoints[cursorIndex];
    const [distance, altitude] = profilePoints[cursorIndex];
    profileCursor.setAttribute("x1", x);
    profileCursor.setAttribute("x2", x);
    profileCursorPoint.setAttribute("cx", x);
    profileCursorPoint.setAttribute("cy", y);
    profileCursor.removeAttribute("hidden");
    profileCursorPoint.removeAttribute("hidden");
    profileReadout.textContent = `${(distance / 1000).toFixed(2).replace(".", ",")} km · ${Math.round(altitude)} m`;
    document.dispatchEvent(new CustomEvent("hike2gpx:profil-position", {
      detail: distance / Math.max(1, profilePoints.at(-1)[0]),
    }));
  }
  profileSvg.addEventListener("pointermove", event => {
    const rect = profileSvg.getBoundingClientRect();
    const x = (event.clientX - rect.left) * 800 / rect.width;
    let nearest = 0;
    for (let i = 1; i < scaledPoints.length; i++) {
      if (Math.abs(scaledPoints[i][0] - x) < Math.abs(scaledPoints[nearest][0] - x)) nearest = i;
    }
    showCursor(nearest);
  });
  profileSvg.addEventListener("pointerleave", hideProfileCursor);
  profileSvg.addEventListener("keydown", event => {
    const next = { ArrowLeft: cursorIndex - 1, ArrowRight: cursorIndex + 1,
      Home: 0, End: scaledPoints.length - 1 }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    showCursor(next);
  });
  document.addEventListener("hike2gpx:denivele", event => {
    if (elevationPanel.hidden) return;
    hideProfileCursor();
    const data = event.detail;
    if (data.erreur || !Array.isArray(data.profil) || data.profil.length < 2) {
      profileSource.textContent = t("profil.indisponible", { erreur: data.erreur || "données manquantes" });
      profileSvg.setAttribute("hidden", "");
      profileAxis.hidden = true;
      return;
    }
    profilePoints = data.profil.filter(p => Array.isArray(p) && p.length === 2 && p.every(Number.isFinite));
    if (profilePoints.length < 2) return;
    const min = Math.min(...profilePoints.map(p => p[1]));
    const max = Math.max(...profilePoints.map(p => p[1]));
    const low = min - Math.max(5, (max - min) * 0.08);
    const high = max + Math.max(5, (max - min) * 0.08);
    const distance = Math.max(1, profilePoints.at(-1)[0]);
    scaledPoints = profilePoints.map(([d, z]) => [16 + 768 * d / distance, 116 - 92 * (z - low) / (high - low)]);
    const line = scaledPoints.map(([x, y], index) => `${index ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
    document.getElementById("profileLine").setAttribute("d", line);
    document.getElementById("profileArea").setAttribute("d", `${line} L784 116 L16 116 Z`);
    document.getElementById("elevationRange").textContent = `${data.altitude_min_m} – ${data.altitude_max_m} m`;
    profileSource.textContent = `gpx2elev · ${data.modele} · D+ ${data.montee_m} m · D− ${data.descente_m} m`;
    document.getElementById("profileMid").textContent = `${(distance / 2000).toFixed(2).replace(".", ",")} km`;
    document.getElementById("profileEnd").textContent = `${(distance / 1000).toFixed(2).replace(".", ",")} km`;
    profileSvg.setAttribute("aria-label", `Profil gpx2elev : de ${data.altitude_min_m} à ${data.altitude_max_m} mètres sur ${(distance / 1000).toFixed(2)} kilomètres. Flèches gauche et droite pour explorer.`);
    profileSvg.removeAttribute("hidden");
    profileAxis.hidden = false;
  });
  syncRoute();
  const grip = document.querySelector(".sheet-grip");
  const showKey = document.getElementById("afficherCle");
  const keyInput = document.getElementById("cleIgn");
  function updateShowKey() {
    const visible = keyInput.type === "text";
    const english = document.documentElement.lang === "en";
    const label = english ? (visible ? "Hide IGN key" : "Show IGN key")
      : (visible ? "Masquer la clé IGN" : "Afficher la clé IGN");
    showKey.setAttribute("aria-pressed", String(visible));
    showKey.setAttribute("aria-label", label);
    showKey.title = label;
  }
  showKey.addEventListener("click", () => {
    keyInput.type = keyInput.type === "password" ? "text" : "password";
    updateShowKey();
  });
  document.addEventListener("nico579-langue", updateShowKey);
  updateShowKey();
  grip.addEventListener("click", () => {
    document.body.classList.toggle("sheet-expanded");
    setTimeout(() => window.dispatchEvent(new Event("resize")), 280);
  });
  document.getElementById("carte").addEventListener("click", () => {
    if (innerWidth <= 700) document.body.classList.remove("sheet-expanded");
  });
  // Le contrôle Leaflet des fonds et des calques s'affiche dans la page
  // « Gestion des cartes », comme sur le téléphone. app.js le gère toujours,
  // y compris lorsqu'une langue ou un pays le recrée : on le replace alors.
  const toolbar = document.querySelector(".map-widget-toolbar");
  const providersInfoLink = document.getElementById("providersInfoButton");
  function updateProvidersInfoLink() {
    const english = document.documentElement.lang === "en";
    providersInfoLink.href = lienCouverturePays(english ? "en" : "fr");
    providersInfoLink.setAttribute("aria-label", english
      ? "Open supported countries on GitHub" : "Ouvrir les pays pris en charge sur GitHub");
    providersInfoLink.title = english ? "Supported countries on GitHub" : "Pays pris en charge sur GitHub";
  }
  document.addEventListener("nico579-langue", updateProvidersInfoLink);
  updateProvidersInfoLink();
  const expandButton = document.getElementById("expandMapButton");
  const map = document.getElementById("carte");
  const legend = document.getElementById("mapLegend");
  const leafletControls = document.querySelector(".leaflet-top.leaflet-right");
  const layersHost = document.getElementById("cartesCalques");
  document.querySelector(".leaflet-control-zoom").after(expandButton);
  for (const eventName of ["click", "mousedown", "dblclick"]) {
    expandButton.addEventListener(eventName, event => event.stopPropagation());
  }
  function syncLayers() {
    const control = leafletControls.querySelector(".leaflet-control-layers")
      || layersHost.querySelector(".leaflet-control-layers");
    if (!control) return;
    if (control.parentElement !== layersHost) layersHost.replaceChildren(control);
    // Le titre de la superposition, au-dessus des coches ; un contrôle recréé
    // (langue, pays) le perd : il se repose à chaque passage.
    const overlays = control.querySelector(".leaflet-control-layers-overlays");
    if (overlays && !control.querySelector(".cartes-calques-titre")) {
      const title = document.createElement("h3");
      title.className = "cartes-calques-titre";
      title.dataset.i18n = "cartes.calquesTitre";
      title.textContent = t("cartes.calquesTitre");
      overlays.before(title);
    }
  }
  syncLayers();
  new MutationObserver(syncLayers).observe(leafletControls, { childList: true });
  // La légende est un bandeau de la carte, comme sur le téléphone ; « Afficher
  // la légende », dans les réglages, la montre ou la cache.
  const showLegend = document.getElementById("showLegend");
  const legendPreference = "hike2gpx.showLegend";
  try { showLegend.checked = localStorage.getItem(legendPreference) !== "false"; } catch (error) {}
  function syncLegend() {
    legend.hidden = !showLegend.checked;
  }
  showLegend.addEventListener("change", () => {
    try { localStorage.setItem(legendPreference, String(showLegend.checked)); } catch (error) {}
    syncLegend();
  });
  syncLegend();
  // L'aide des tuiles hors ligne et la légende restent posées sur la carte.
  toolbar.addEventListener("mousedown", event => event.stopPropagation());
  toolbar.addEventListener("dblclick", event => event.stopPropagation());
  toolbar.addEventListener("click", event => event.stopPropagation());
  function syncFullscreen() {
    const expanded = document.fullscreenElement === map;
    document.body.classList.toggle("plein-ecran", expanded);
    const label = expanded ? "Quitter le plein écran" : "Mettre la carte en plein écran";
    expandButton.setAttribute("aria-pressed", String(expanded));
    expandButton.setAttribute("aria-label", label);
    expandButton.title = label;
    setTimeout(() => window.dispatchEvent(new Event("resize")), 60);
  }
  document.addEventListener("fullscreenchange", syncFullscreen);
  expandButton.addEventListener("click", async () => {
    try {
      if (document.fullscreenElement === map) await document.exitFullscreen();
      else await map.requestFullscreen();
    } catch (error) {
      console.warn("Plein écran indisponible", error);
      document.getElementById("statut").textContent = "Le navigateur a refusé le plein écran.";
      syncFullscreen();
    }
  });
})();
