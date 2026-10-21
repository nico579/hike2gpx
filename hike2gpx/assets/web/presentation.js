/* Présentation de la page ; le moteur de tracé reste app.js. */
(() => {
  const tabs = [...document.querySelectorAll("[data-pane]")];
  const panel = document.getElementById("panneau");
  const panelToggle = document.getElementById("panelToggle");
  const panelPreference = "hike2gpx.panelCollapsed";
  function setPanelCollapsed(collapsed, remember = false) {
    document.body.classList.toggle("panel-collapsed", collapsed);
    panel.toggleAttribute("inert", collapsed);
    panel.setAttribute("aria-hidden", String(collapsed));
    panelToggle.setAttribute("aria-expanded", String(!collapsed));
    const label = collapsed ? "Afficher le panneau du parcours" : "Replier le panneau du parcours";
    panelToggle.setAttribute("aria-label", label);
    panelToggle.title = label;
    if (remember) {
      try { localStorage.setItem(panelPreference, String(collapsed)); } catch (error) {}
    }
    setTimeout(() => window.dispatchEvent(new Event("resize")), 260);
  }
  try { setPanelCollapsed(localStorage.getItem(panelPreference) === "true"); }
  catch (error) { setPanelCollapsed(false); }
  panelToggle.addEventListener("click", () => setPanelCollapsed(!document.body.classList.contains("panel-collapsed"), true));
  // Les états réels de app.js restent visibles sur la carte dans tous les onglets.
  const activity = document.getElementById("mapActivity");
  const activityRows = document.getElementById("mapActivityRows");
  const jobs = [
    ["Chemins de la carte", "noteCalques", "noteCalquesTexte", "noteCalquesPiste", "noteCalquesBarre"],
    ["Extrait OSM", "extraitOsm", "extraitTexte", "extraitPiste", "extraitBarre"],
    ["BRouter", "brouterEnCours", "brouterTexte", "brouterPiste", "brouterBarre"],
    ["Calcul du parcours", "progression", "progressionTexte", "progression", "progressionBarre"],
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
  function selectPane(name, focus = false) {
    for (const tab of tabs) {
      const selected = tab.dataset.pane === name;
      tab.setAttribute("aria-selected", String(selected));
      tab.tabIndex = selected ? 0 : -1;
      document.getElementById(`pane-${tab.dataset.pane}`).hidden = !selected;
      if (selected && focus) tab.focus();
    }
    panel.querySelector(".panel-scroll").scrollTop = 0;
    if (name === "reglages") chargerDonnees();
    if (name === "journal") chargerJournal();
    if (innerWidth <= 700 && name !== "trace") document.body.classList.add("sheet-expanded");
    setTimeout(() => window.dispatchEvent(new Event("resize")), 280);
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => selectPane(tab.dataset.pane));
    tab.addEventListener("keydown", event => {
      const next = { ArrowRight: (index + 1) % tabs.length, ArrowLeft: (index + tabs.length - 1) % tabs.length, Home: 0, End: tabs.length - 1 }[event.key];
      if (next === undefined) return;
      event.preventDefault();
      selectPane(tabs[next].dataset.pane, true);
    });
  });
  const routeSummary = document.getElementById("routeSummary");
  const result = document.getElementById("resultat");
  const exporter = document.getElementById("exporter");
  const elevationPanel = document.getElementById("elevationPanel");
  const elevationToggle = document.getElementById("elevationToggle");
  const elevationContent = document.getElementById("elevationContent");
  const profileSvg = document.getElementById("elevationProfile");
  const profileSource = document.getElementById("profileSource");
  const profileReadout = document.getElementById("profileReadout");
  const profileAxis = document.getElementById("profileAxis");
  const profileCursor = document.getElementById("profileCursor");
  const profileCursorPoint = document.getElementById("profileCursorPoint");
  let profilePoints = [];
  let scaledPoints = [];
  let cursorIndex = 0;
  function syncProfileHeight() {
    const visible = !elevationPanel.hidden;
    document.body.classList.toggle("profile-open", visible && !elevationContent.hidden);
    document.body.classList.toggle("profile-collapsed", visible && elevationContent.hidden);
  }
  function syncRoute() {
    const ready = !result.hidden && !exporter.disabled;
    const wasVisible = !elevationPanel.hidden;
    routeSummary.hidden = !ready;
    elevationPanel.hidden = !ready;
    if (!ready) {
      profilePoints = [];
      profileSvg.setAttribute("hidden", "");
      profileAxis.hidden = true;
      profileCursor.setAttribute("hidden", "");
      profileCursorPoint.setAttribute("hidden", "");
    } else if (!wasVisible) {
      profileSource.textContent = t("profil.attente");
      profileReadout.textContent = "";
      document.getElementById("elevationRange").textContent = "";
    }
    syncProfileHeight();
  }
  new MutationObserver(syncRoute).observe(result, { attributes: true, attributeFilter: ["hidden"] });
  new MutationObserver(syncRoute).observe(exporter, { attributes: true, attributeFilter: ["disabled"] });
  elevationToggle.addEventListener("click", () => {
    elevationContent.hidden = !elevationContent.hidden;
    elevationToggle.setAttribute("aria-expanded", String(!elevationContent.hidden));
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
  profileSvg.addEventListener("pointerleave", () => {
    profileCursor.setAttribute("hidden", "");
    profileCursorPoint.setAttribute("hidden", "");
    profileReadout.textContent = "";
  });
  profileSvg.addEventListener("keydown", event => {
    const next = { ArrowLeft: cursorIndex - 1, ArrowRight: cursorIndex + 1,
      Home: 0, End: scaledPoints.length - 1 }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    showCursor(next);
  });
  document.addEventListener("hike2gpx:denivele", event => {
    if (elevationPanel.hidden) return;
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
  showKey.addEventListener("click", () => {
    const input = document.getElementById("cleIgn");
    const visible = input.type !== "text";
    input.type = visible ? "text" : "password";
    showKey.textContent = visible ? "Masquer" : "Afficher";
    showKey.setAttribute("aria-label", visible ? "Masquer la clé IGN" : "Afficher la clé IGN");
  });
  grip.addEventListener("click", () => {
    document.body.classList.toggle("sheet-expanded");
    setTimeout(() => window.dispatchEvent(new Event("resize")), 280);
  });
  document.getElementById("carte").addEventListener("click", () => {
    if (innerWidth <= 700) document.body.classList.remove("sheet-expanded");
  });
  // Habillage de la commande Leaflet existante : les vrais fonds et calques
  // restent gérés par app.js, y compris lorsqu'une langue les recrée.
  const toolbar = document.querySelector(".map-widget-toolbar");
  const layersButton = document.getElementById("layersButton");
  const baseLabel = document.getElementById("baseLabel");
  const expandButton = document.getElementById("expandMapButton");
  const map = document.getElementById("carte");
  const legend = document.getElementById("mapLegend");
  const leafletControls = document.querySelector(".leaflet-top.leaflet-right");
  document.querySelector(".leaflet-control-zoom").after(expandButton);
  for (const eventName of ["click", "mousedown", "dblclick"]) {
    expandButton.addEventListener(eventName, event => event.stopPropagation());
  }
  function closeLayers() {
    toolbar.classList.remove("layers-open");
    layersButton.setAttribute("aria-expanded", "false");
  }
  function syncLayers() {
    const control = leafletControls.querySelector(".leaflet-control-layers") || toolbar.querySelector(".leaflet-control-layers");
    if (!control) return;
    if (control.parentElement !== toolbar) {
      closeLayers();
      toolbar.append(control);
    }
    const list = control.querySelector(".leaflet-control-layers-list");
    if (list) {
      list.id = "mapLayersMenu";
      if (legend.parentElement !== list) list.append(legend);
      legend.hidden = false;
    }
    const selected = control.querySelector(".leaflet-control-layers-base input:checked");
    if (selected) baseLabel.textContent = selected.closest("label").textContent.trim();
  }
  syncLayers();
  new MutationObserver(syncLayers).observe(leafletControls, { childList: true });
  toolbar.addEventListener("mousedown", event => event.stopPropagation());
  toolbar.addEventListener("dblclick", event => event.stopPropagation());
  toolbar.addEventListener("click", event => event.stopPropagation());
  // Leaflet interrompt la propagation sur ses champs : capter le changement
  // avant lui pour actualiser le nom du fond choisi.
  toolbar.addEventListener("change", () => setTimeout(syncLayers, 0), true);
  layersButton.addEventListener("click", () => {
    const open = toolbar.classList.toggle("layers-open");
    layersButton.setAttribute("aria-expanded", String(open));
  });
  document.addEventListener("click", event => {
    if (!toolbar.contains(event.target)) closeLayers();
  });
  document.addEventListener("keydown", event => {
    if (event.key === "Escape") closeLayers();
  });
  function syncFullscreen() {
    const expanded = document.fullscreenElement === map;
    document.body.classList.toggle("plein-ecran", expanded);
    const label = expanded ? "Quitter le plein écran" : "Mettre la carte en plein écran";
    expandButton.setAttribute("aria-pressed", String(expanded));
    expandButton.setAttribute("aria-label", label);
    expandButton.title = label;
    closeLayers();
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
