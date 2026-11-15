/*###########################################################################
# TWINSITE - INTERACTIVE GLOBES (Mission Control, top of the page)
#
# Two CesiumJS viewers (WebGL):
#   - TARGET : the Moon or Mars (user switch). Click = select a square region
#              (25 / 50 / 100 km). The backend checks the data inside it
#              (GET /api/region-info); "Analyse this region" runs the full
#              analysis with that region as the target.
#   - EARTH  : the analogue zones. After an analysis: similarity overlay of
#              both zones, numbered best matches; clicking one selects it
#              everywhere in the dashboard and zooms the map onto it.
# Both globes are 3D when zoomed out and switch to a flat 2D map when you zoom
# in (and back). Each has a Layers menu: basemaps (NASA Trek / GIBS, Esri
# satellite imagery), NASA overlays (MODIS land surface temperature) and the
# project's own harmonized data layers (temperature, albedo, slope, ...).
#
# Uses app.js globals (classic scripts share the global scope): result, results,
# activeZone, selected, selectRegion, selectCell, setActiveZone, els, ...
# Everything is guarded: without WebGL the dashboard keeps working.
###########################################################################*/
"use strict";

const TwinMap = (() => {
  const TREK = "https://trek.nasa.gov/tiles";
  const GIBS = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best";
  const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services";
  const BASEMAPS = {
    moon: [
      { id: "wac", label: "LRO WAC mosaic", src: "NASA Moon Trek · LRO", url: `${TREK}/Moon/EQ/LRO_WAC_Mosaic_Global_303ppd_v02/1.0.0/default/default028mm/{z}/{y}/{x}.jpg`, max: 7, geo: true },
    ],
    mars: [
      { id: "viking", label: "Viking colour mosaic", src: "NASA Mars Trek · Viking", url: `${TREK}/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg`, max: 7, geo: true },
      { id: "mola", label: "MOLA colour relief", src: "NASA Mars Trek · MGS MOLA", url: `${TREK}/Mars/EQ/Mars_MGS_MOLA_ClrShade_merge_global_463m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg`, max: 6, geo: true },
    ],
    earth: [
      { id: "esri", label: "Satellite imagery", src: "Esri World Imagery", url: `${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`, max: 19 },
      { id: "bluemarble", label: "NASA Blue Marble", src: "NASA GIBS", url: `${GIBS}/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg`, max: 8 },
    ],
  };
  const EARTH_OVERLAYS = [
    { id: "labels", label: "Place names & borders", url: `${ESRI}/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}`, max: 13, on: true },
    { id: "lst", label: "MODIS land surface temperature (day, 15 Jan 2024)", url: `${GIBS}/MODIS_Terra_Land_Surface_Temp_Day/default/2024-01-15/GoogleMapsCompatible_Level7/{z}/{y}/{x}.png`, max: 7, alpha: 0.75 },
    { id: "similarity", label: "Similarity to the target (this analysis)", local: true, on: true },
  ];
  const ORANGE = "#ff7a2f", BLUE = "#3b82f6";
  const P = { target: null, earth: null };
  const state = { body: "moon", radius: 50, selection: null, info: null, lastResult: null, lastRegionKey: null,
                  radii: [25, 50, 100], catalogues: {}, snaps: {} };
  const deg = (r) => r * 180 / Math.PI;
  const q = (id) => document.getElementById(id);

  /* ---------------- viewer creation ---------------- */
  function ellipsoidOf(body) {
    return body === "moon" ? Cesium.Ellipsoid.MOON : body === "mars" ? Cesium.Ellipsoid.MARS : Cesium.Ellipsoid.WGS84;
  }

  function createPanel(key, body) {
    const el = q(key === "target" ? "globe-target" : "globe-earth");
    const host = el.querySelector(".gp-cesium");
    const ell = ellipsoidOf(body);
    const viewer = new Cesium.Viewer(host, {
      ellipsoid: ell, baseLayer: false, baseLayerPicker: false, geocoder: false, homeButton: false,
      sceneModePicker: false, navigationHelpButton: false, animation: false, timeline: false,
      fullscreenButton: false, infoBox: false, selectionIndicator: false,
      terrainProvider: new Cesium.EllipsoidTerrainProvider({ ellipsoid: ell }),
      mapProjection: new Cesium.GeographicProjection(ell),
      skyBox: false, skyAtmosphere: body === "earth" ? undefined : false,
      contextOptions: { webgl: { preserveDrawingBuffer: true } },
      requestRenderMode: true, maximumRenderTimeChange: Infinity,
    });
    const s = viewer.scene;
    s.backgroundColor = Cesium.Color.fromCssColorString("#05070c");
    s.globe.baseColor = Cesium.Color.fromCssColorString("#151515");
    s.globe.showGroundAtmosphere = body === "earth";
    s.globe.enableLighting = false;
    if (s.sun) s.sun.show = false;
    if (s.moon) s.moon.show = false;
    s.fog.enabled = body === "earth";
    const R = ell.maximumRadius;
    s.screenSpaceCameraController.minimumZoomDistance = 800;
    s.screenSpaceCameraController.maximumZoomDistance = R * 6;
    const panel = { key, body, el, viewer, ell, R, base: null, overlays: {}, data: null, dataMeta: null,
                    morphing: false, after: null, cool: 0, opacity: 0.8 };
    viewer.camera.percentageChanged = 0.02;
    viewer.camera.changed.addEventListener(() => autoMode(panel));
    s.morphComplete.addEventListener(() => {
      panel.morphing = false;
      panel.cool = Date.now() + 1200;
      const a = panel.after; panel.after = null;
      if (a) a();
      updateModeButton(panel);
      s.requestRender();
    });
    viewer.camera.moveEnd.addEventListener(() => scheduleSnap(panel));
    new Cesium.ScreenSpaceEventHandler(s.canvas).setInputAction((e) => onClick(panel, e.position),
      Cesium.ScreenSpaceEventType.LEFT_CLICK);
    setBasemap(panel, BASEMAPS[body === "earth" ? "earth" : body][0].id);
    return panel;
  }

  function tileProvider(panel, def) {
    const tilingScheme = def.geo ? new Cesium.GeographicTilingScheme({ ellipsoid: panel.ell })
      : new Cesium.WebMercatorTilingScheme({ ellipsoid: panel.ell });
    return new Cesium.UrlTemplateImageryProvider({ url: def.url, tilingScheme, maximumLevel: def.max,
      credit: new Cesium.Credit(def.src || def.label) });
  }

  /* ---------------- layers ---------------- */
  function setBasemap(panel, id) {
    const list = BASEMAPS[panel.body === "earth" ? "earth" : panel.body];
    const def = list.find((d) => d.id === id) || list[0];
    const layers = panel.viewer.imageryLayers;
    if (panel.base) layers.remove(panel.base, true);
    panel.base = layers.addImageryProvider(tileProvider(panel, def), 0);
    panel.baseId = def.id;
    const src = q(panel.key === "target" ? "gp-target-src" : "gp-earth-src");
    if (src) src.textContent = def.src;
    panel.viewer.scene.requestRender();
  }

  async function setOverlay(panel, id, on) {
    const layers = panel.viewer.imageryLayers;
    if (panel.overlays[id]) {
      (Array.isArray(panel.overlays[id]) ? panel.overlays[id] : [panel.overlays[id]]).forEach((l) => layers.remove(l, true));
      delete panel.overlays[id];
    }
    if (!on) { panel.viewer.scene.requestRender(); return; }
    const def = EARTH_OVERLAYS.find((d) => d.id === id);
    if (def.local) {
      panel.overlays[id] = await similarityLayers(panel);
    } else {
      const l = layers.addImageryProvider(tileProvider(panel, def));
      l.alpha = def.alpha ?? 1;
      panel.overlays[id] = l;
    }
    raiseLabels(panel);
    panel.viewer.scene.requestRender();
  }

  function raiseLabels(panel) {
    const l = panel.overlays.labels;
    if (l) panel.viewer.imageryLayers.raiseToTop(l);
  }

  // project data layer(s): one PNG for a body, one per Earth zone
  async function setDataLayer(panel, featureId) {
    const layers = panel.viewer.imageryLayers;
    (panel.data || []).forEach((l) => layers.remove(l, true));
    panel.data = null; panel.dataMeta = null;
    if (featureId && featureId !== "none") {
      const bodies = panel.body === "earth" ? Object.keys(ZONE_MAPS) : [panel.body];
      panel.data = [];
      for (const b of bodies) {
        const meta = (await catalogue(b)).find((x) => x.id === featureId);
        if (!meta) continue;
        const [w, s, e, n] = meta.rectangle;
        const prov = await Cesium.SingleTileImageryProvider.fromUrl(meta.url,
          { rectangle: Cesium.Rectangle.fromDegrees(w, s, e, n), credit: "TWINSITE harmonized NASA data" });
        const l = layers.addImageryProvider(prov);
        l.alpha = panel.opacity;
        panel.data.push(l);
        panel.dataMeta = panel.dataMeta || meta;
      }
      raiseLabels(panel);
    }
    renderLegend(panel);
    panel.viewer.scene.requestRender();
  }

  async function catalogue(body) {
    if (!state.catalogues[body]) {
      const r = await fetch(`/api/layers?body=${encodeURIComponent(body)}`).then((x) => x.json());
      state.catalogues[body] = r.status === "ok" ? r.layers : [];
      if (r.radius_km_choices) state.radii = r.radius_km_choices;
    }
    return state.catalogues[body];
  }

  function renderLegend(panel) {
    const box = q(panel.key === "target" ? "gp-target-legend" : "gp-earth-legend");
    const m = panel.dataMeta;
    if (!m) { box.hidden = true; return; }
    const u = m.units ? ` ${m.units}` : "";
    box.innerHTML = `<span class="gp-legend__title">${escapeHtml(m.label)}</span>
      <span class="gp-legend__ramp" style="background:linear-gradient(90deg,${m.colors.join(",")})"></span>
      <span class="gp-legend__scale"><span>${physical(m.min, "")}${u}</span><span>${physical(m.max, "")}${u}</span></span>`;
    box.hidden = false;
  }

  async function buildLayerMenu(panel) {
    const box = q(panel.key === "target" ? "gp-target-layers" : "gp-earth-layers");
    const isEarth = panel.body === "earth";
    const bases = BASEMAPS[isEarth ? "earth" : panel.body];
    const dataBodies = isEarth ? ["atacama"] : [panel.body];
    const data = (await catalogue(dataBodies[0])).filter((x) => x.id !== "coverage" || !isEarth);
    const name = `${panel.key}-base`, dname = `${panel.key}-data`;
    box.innerHTML = `
      <p class="gp-layers__h">Base map</p>
      ${bases.map((b) => `<label><input type="radio" name="${name}" value="${b.id}" ${b.id === panel.baseId ? "checked" : ""}> ${escapeHtml(b.label)} <small>${escapeHtml(b.src)}</small></label>`).join("")}
      ${isEarth ? `<p class="gp-layers__h">NASA overlays</p>
        ${EARTH_OVERLAYS.map((o) => `<label><input type="checkbox" data-overlay="${o.id}" ${panel.overlays[o.id] || (o.on && !panel.menuBuilt) ? "checked" : ""}> ${escapeHtml(o.label)}</label>`).join("")}` : ""}
      <p class="gp-layers__h">Harmonized data (${isEarth ? "Earth zones" : panel.body === "moon" ? "LRO" : "MGS / Odyssey"})</p>
      <label><input type="radio" name="${dname}" value="none" ${!panel.dataMeta ? "checked" : ""}> None</label>
      ${data.map((d) => `<label><input type="radio" name="${dname}" value="${d.id}" ${panel.dataMeta && panel.dataMeta.id === d.id ? "checked" : ""}> ${escapeHtml(d.label)}</label>`).join("")}
      <label class="gp-layers__opacity">Opacity <input type="range" min="0.2" max="1" step="0.05" value="${panel.opacity}"></label>`;
    panel.menuBuilt = true;
    box.onchange = (e) => {
      const t = e.target;
      if (t.name === name) setBasemap(panel, t.value);
      else if (t.name === dname) setDataLayer(panel, t.value);
      else if (t.dataset.overlay) setOverlay(panel, t.dataset.overlay, t.checked);
    };
    box.oninput = (e) => {
      if (e.target.type !== "range") return;
      panel.opacity = Number(e.target.value);
      (panel.data || []).forEach((l) => { l.alpha = panel.opacity; });
      panel.viewer.scene.requestRender();
    };
  }

  /* ---------------- 3D <-> 2D ---------------- */
  function viewCenter(panel) {
    const v = panel.viewer;
    const c = new Cesium.Cartesian2(v.canvas.clientWidth / 2, v.canvas.clientHeight / 2);
    const p = v.camera.pickEllipsoid(c, panel.ell);
    if (!p) return null;
    const g = panel.ell.cartesianToCartographic(p);
    return { lat: deg(g.latitude), lon: deg(g.longitude) };
  }

  function widthDeg2D(panel) {
    const f = panel.viewer.camera.frustum;
    return (f.right - f.left) / (panel.R * Math.PI / 180);
  }

  function autoMode(panel) {
    if (panel.morphing || Date.now() < panel.cool) return;
    const v = panel.viewer, mode = v.scene.mode;
    if (mode === Cesium.SceneMode.SCENE3D) {
      const alt = Cesium.Cartesian3.magnitude(v.camera.positionWC) - panel.R;
      if (alt < panel.R * 0.42) {
        const c = viewCenter(panel);
        if (c) to2D(panel, c, alt);
      }
    } else if (mode === Cesium.SceneMode.SCENE2D) {
      if (widthDeg2D(panel) > 150) to3D(panel, viewCenter(panel));
    }
  }

  function to2D(panel, center, alt, then) {
    const v = panel.viewer;
    panel.morphing = true;
    panel.after = () => {
      v.camera.setView({ destination: Cesium.Cartesian3.fromDegrees(center.lon, center.lat, alt, panel.ell) });
      if (then) then();
    };
    v.scene.morphTo2D(0.9);
  }

  function to3D(panel, center, then) {
    const v = panel.viewer;
    panel.morphing = true;
    panel.after = () => {
      const c = center || { lat: 0, lon: 0 };
      v.camera.setView({ destination: Cesium.Cartesian3.fromDegrees(c.lon, c.lat, panel.R * 1.9, panel.ell) });
      if (then) then();
    };
    v.scene.morphTo3D(0.9);
  }

  function updateModeButton(panel) {
    const b = q(panel.key === "target" ? "gp-target-mode" : "gp-earth-mode");
    if (!b) return;
    const is2D = panel.viewer.scene.mode === Cesium.SceneMode.SCENE2D;
    b.textContent = is2D ? "3D" : "2D";
    b.title = is2D ? "Back to the 3D globe" : "Flat 2D map";
    panel.el.classList.toggle("is-2d", is2D);
  }

  function toggleMode(panel) {
    if (panel.morphing) return;
    const c = viewCenter(panel) || state.selection || { lat: 0, lon: 0 };
    if (panel.viewer.scene.mode === Cesium.SceneMode.SCENE2D) to3D(panel, c);
    else to2D(panel, c, panel.R * 0.3);
  }

  // fly to a rectangle [w,s,e,n]; switch to 2D first when asked
  function goTo(panel, rect, want2D) {
    const v = panel.viewer;
    const fly = () => v.camera.flyTo({ destination: Cesium.Rectangle.fromDegrees(...rect), duration: 1.2 });
    const is2D = v.scene.mode === Cesium.SceneMode.SCENE2D;
    if (want2D && !is2D && !panel.morphing) {
      const c = { lat: (rect[1] + rect[3]) / 2, lon: (rect[0] + rect[2]) / 2 };
      to2D(panel, c, panel.R * 0.2, fly);
    } else if (!want2D && is2D && !panel.morphing) {
      to3D(panel, { lat: (rect[1] + rect[3]) / 2, lon: (rect[0] + rect[2]) / 2 }, () => {
        panel.cool = Date.now() + 2500;
        fly();
      });
    } else {
      panel.cool = Date.now() + 2500;
      fly();
    }
  }

  /* ---------------- drawing helpers ---------------- */
  function squarePositions(panel, lat, lon, halfLatDeg, halfLonDeg, h) {
    const pts = [];
    const corners = [[lat + halfLatDeg, lon - halfLonDeg], [lat + halfLatDeg, lon + halfLonDeg],
                     [lat - halfLatDeg, lon + halfLonDeg], [lat - halfLatDeg, lon - halfLonDeg]];
    for (let k = 0; k < 4; k++) {
      const [a, b] = [corners[k], corners[(k + 1) % 4]];
      for (let i = 0; i < 16; i++) {
        const t = i / 16;
        pts.push(Cesium.Cartesian3.fromDegrees(a[1] + (b[1] - a[1]) * t, a[0] + (b[0] - a[0]) * t, h, panel.ell));
      }
    }
    pts.push(pts[0]);
    return pts;
  }

  function regionHalfDeg(panel, lat, radiusKm) {
    const dLat = radiusKm * 1000 / panel.R * 180 / Math.PI;
    const dLon = dLat / Math.max(Math.cos(lat * Math.PI / 180), 0.05);
    return [dLat, Math.min(dLon, 179)];
  }

  function pointEntity(panel, lat, lon, color, size, text, extra = {}) {
    return panel.viewer.entities.add({
      position: Cesium.Cartesian3.fromDegrees(lon, lat, 50, panel.ell),
      point: { pixelSize: size, color: Cesium.Color.fromCssColorString(color), outlineColor: Cesium.Color.WHITE,
               outlineWidth: 2.5, disableDepthTestDistance: Number.POSITIVE_INFINITY },
      label: text ? { text, font: "600 12px Inter, sans-serif", fillColor: Cesium.Color.WHITE,
                      outlineColor: Cesium.Color.BLACK, outlineWidth: 3, style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                      pixelOffset: new Cesium.Cartesian2(0, -16), disableDepthTestDistance: Number.POSITIVE_INFINITY,
                      showBackground: false } : undefined,
      ...extra,
    });
  }

  /* ---------------- TARGET: catalogue pins + region selection ---------------- */
  function drawTargetMarks() {
    const panel = P.target;
    if (!panel) return;
    const ents = panel.viewer.entities;
    ents.removeAll();
    const cat = (window.TWIN_TARGETS || {})[panel.body] || {};
    for (const [name, t] of Object.entries(cat)) {
      pointEntity(panel, t.lat, t.lon, "#ffffff", 9, name, { twinCatalogue: name });
    }
    const sel = state.selection;
    if (sel) {
      const [hLat, hLon] = regionHalfDeg(panel, sel.lat, sel.radius);
      ents.add({ polyline: { positions: squarePositions(panel, sel.lat, sel.lon, hLat, hLon, 200), width: 3,
        material: Cesium.Color.fromCssColorString(ORANGE), arcType: Cesium.ArcType.NONE } });
      pointEntity(panel, sel.lat, sel.lon, ORANGE, 15, null);
    }
    panel.viewer.scene.requestRender();
  }

  async function selectTargetRegion(lat, lon, opts = {}) {
    state.selection = { lat, lon, radius: opts.radius || state.radius, catalogue: opts.catalogue || null };
    drawTargetMarks();
    const box = q("gp-target-info");
    box.innerHTML = `<p class="gp-info__title">Selected region</p><p>Checking NASA data in this region…</p>`;
    let info;
    try {
      info = await fetch(`/api/region-info?planet=${state.body}&lat=${lat}&lon=${lon}&radius=${state.selection.radius}`).then((r) => r.json());
      if (info.status !== "ok") throw new Error(info.message);
    } catch (err) {
      box.innerHTML = `<p class="gp-info__title">Selected region</p><p class="gp-warn">${escapeHtml(err.message)}</p>`;
      return;
    }
    state.info = info;
    renderTargetInfo();
  }

  function renderTargetInfo() {
    const info = state.info, sel = state.selection, box = q("gp-target-info");
    if (!info || !sel) return;
    const pp = info.profile_physical || {};
    const val = (f, u, d) => (isNum(pp[f]) ? `${Number(pp[f]).toFixed(d)}${u}` : "—");
    const nComp = info.features_comparable.length, nOk = info.features_available.length;
    const name = sel.catalogue || "Selected region";
    box.innerHTML = `
      <p class="gp-info__title">${escapeHtml(name)}</p>
      <p>Lat: ${sel.lat.toFixed(2)}° · Lon: ${sel.lon.toFixed(2)}°</p>
      <p>Area: ~${info.area_km2.toLocaleString("en")} km²
        <select class="gp-radius" aria-label="Region size">${state.radii.map((r) =>
          `<option value="${r}" ${r === sel.radius ? "selected" : ""}>${2 * r} km square</option>`).join("")}</select></p>
      <p class="${info.analysable ? "gp-ok" : "gp-warn"}">${info.analysable ? "✓" : "⚠"} ${info.cells} data cells ·
        ${nOk}/${nComp} comparable parameters${info.reason ? ` — ${escapeHtml(info.reason)}` : ""}</p>
      <p class="gp-info__vals">Day ${val("temperature_day", " K", 0)} · Night ${val("temperature_night", " K", 0)} ·
        Albedo ${val("albedo", "", 2)} · Slope ${val("slope", "°", 1)}</p>
      <button type="button" class="gp-analyse" ${info.analysable ? "" : "disabled"}>Find Earth analogues for this region</button>`;
    box.querySelector(".gp-radius").onchange = (e) => {
      state.radius = Number(e.target.value);
      selectTargetRegion(sel.lat, sel.lon, { radius: state.radius, catalogue: null });
    };
    box.querySelector(".gp-analyse").onclick = analyseSelection;
  }

  function analyseSelection() {
    const sel = state.selection, info = state.info;
    if (!sel || !info || !info.analysable) return;
    els.planet.value = state.body;
    updateLocations();
    let loc = sel.catalogue;
    if (!loc) {
      loc = info.location;
      const opt = document.createElement("option");
      opt.value = loc; opt.textContent = `Selected region (${sel.lat.toFixed(2)}°, ${sel.lon.toFixed(2)}°)`;
      els.location.appendChild(opt);
    }
    els.location.value = loc;
    setScenario(null);
    els.form.requestSubmit();
  }

  /* ---------------- EARTH: similarity overlay + best matches ---------------- */
  async function similarityLayers(panel) {
    const out = [];
    for (const zone of Object.keys(ZONE_MAPS)) {
      const res = results[zone];
      if (!res || !res.map || !res.map.length) continue;
      const step = res.map_cell_deg, h = step / 2;
      const lats = res.map.map((c) => c.lat), lons = res.map.map((c) => c.lon);
      const w = Math.min(...lons) - h, e = Math.max(...lons) + h, s = Math.min(...lats) - h, n = Math.max(...lats) + h;
      const cols = Math.round((e - w) / step), rows = Math.round((n - s) / step);
      const cv = document.createElement("canvas");
      cv.width = cols; cv.height = rows;
      const ctx = cv.getContext("2d");
      const sorted = res.map.map((c) => c.score).filter(isNum).sort((a, b) => a - b);
      const rankOf = (sc) => {
        let lo = 0, hi = sorted.length;
        while (lo < hi) { const mid = (lo + hi) >> 1; if (sorted[mid] < sc) lo = mid + 1; else hi = mid; }
        return sorted.length > 1 ? lo / (sorted.length - 1) : 1;
      };
      for (const c of res.map) {
        if (!isNum(c.score)) continue;
        ctx.fillStyle = simColor(rankOf(c.score));
        ctx.fillRect(Math.floor((c.lon - w) / step), Math.floor((n - c.lat) / step), 1, 1);
      }
      const prov = await Cesium.SingleTileImageryProvider.fromUrl(cv.toDataURL("image/png"),
        { rectangle: Cesium.Rectangle.fromDegrees(w, s, e, n), credit: "TWINSITE similarity" });
      const l = panel.viewer.imageryLayers.addImageryProvider(prov);
      l.alpha = 0.62;
      l.magnificationFilter = Cesium.TextureMagnificationFilter.NEAREST;
      out.push(l);
    }
    return out;
  }

  function drawEarthMarks(r) {
    const panel = P.earth;
    if (!panel || !result) return;
    const ents = panel.viewer.entities;
    ents.removeAll();
    result.ranking.forEach((reg, i) => {
      const on = i === selected;
      pointEntity(panel, reg.lat, reg.lon, on ? ORANGE : BLUE, on ? 16 : 11, `#${reg.rank}`, { twinRank: i });
    });
    if (r) {
      const h = result.map_cell_deg / 2;
      ents.add({ polyline: { positions: squarePositions(panel, r.lat, r.lon, h, h, 100), width: 3,
        material: Cesium.Color.fromCssColorString(ORANGE), arcType: Cesium.ArcType.NONE } });
      if (r.refined) {
        ents.add({ position: Cesium.Cartesian3.fromDegrees(r.refined.lon, r.refined.lat, 60, panel.ell),
          label: { text: "★", font: "22px sans-serif", fillColor: Cesium.Color.WHITE, outlineColor: Cesium.Color.BLACK,
                   outlineWidth: 3, style: Cesium.LabelStyle.FILL_AND_OUTLINE, disableDepthTestDistance: Number.POSITIVE_INFINITY } });
      }
    }
    for (const v of ((result.validation || {}).sites || [])) {
      pointEntity(panel, v.lat, v.lon, "#ffffff", 7, `▲ ${v.name}`);
    }
    panel.viewer.scene.requestRender();
  }

  function renderMatches() {
    const box = q("gp-matches");
    if (!result || !result.ranking.length) { box.hidden = true; return; }
    const zones = Object.keys(ZONE_MAPS).filter((z) => results[z]);
    box.innerHTML = `<p class="gp-matches__h">Best matches</p>
      <div class="gp-zones">${zones.map((z) => `<button type="button" data-zone="${z}" class="${z === activeZone ? "is-on" : ""}">
        ${escapeHtml(results[z].zone.name)} <b>${fmt(results[z].score, 1)}</b></button>`).join("")}</div>
      <ol>${result.ranking.slice(0, 5).map((reg, i) => `<li><button type="button" data-rank="${i}" class="${i === selected ? "is-on" : ""}">
        <span>#${reg.rank}</span> ${coord(reg.lat, reg.lon, 2)} <b>${fmt(reg.score, 1)}</b></button></li>`).join("")}</ol>`;
    box.hidden = false;
  }

  function renderEarthInfo(r) {
    const box = q("gp-earth-info");
    q("vc-earth-name").textContent = zfull();
    q("vc-earth-zone-name").textContent = `${zfull()} · `;
    q("vc-earth-score").textContent = `Similarity ${fmt(r.score, 1)} %`;
    q("gp-earth-region").textContent = `Region #${r.rank} · ${coord(r.lat, r.lon, 2)}` +
      (r.refined ? ` · exact point ${coord(r.refined.lat, r.refined.lon, 3)}` : "") +
      (isNum(r.accessible_pct) ? ` · ${r.accessible_pct} % drivable` : "");
    box.hidden = false;
  }

  /* ---------------- clicks ---------------- */
  function onClick(panel, pos) {
    const v = panel.viewer;
    const picked = v.scene.pick(pos);
    const ent = picked && picked.id;
    if (panel.key === "target") {
      if (ent && ent.twinCatalogue) {
        const t = window.TWIN_TARGETS[panel.body][ent.twinCatalogue];
        selectTargetRegion(t.lat, t.lon, { radius: t.window_km, catalogue: ent.twinCatalogue });
        return;
      }
      const p = v.camera.pickEllipsoid(pos, panel.ell);
      if (!p) return;
      const g = panel.ell.cartesianToCartographic(p);
      selectTargetRegion(+deg(g.latitude).toFixed(3), +deg(g.longitude).toFixed(3), { radius: state.radius });
      return;
    }
    if (ent && Number.isInteger(ent.twinRank)) { selectRegion(ent.twinRank); return; }
    if (!result) return;
    const p = v.camera.pickEllipsoid(pos, panel.ell);
    if (!p) return;
    const g = panel.ell.cartesianToCartographic(p), lat = deg(g.latitude), lon = deg(g.longitude);
    const h = result.map_cell_deg / 2;
    const c = result.map.find((x) => Math.abs(x.lat - lat) <= h && Math.abs(x.lon - lon) <= h);
    if (c) selectCell(c);
  }

  /* ---------------- body switch ---------------- */
  function setBody(body, keepSelection) {
    if (!window.Cesium || (P.target && P.target.body === body)) return;
    state.body = body;
    if (!keepSelection) { state.selection = null; state.info = null; }
    if (P.target) { P.target.viewer.destroy(); P.target = null; }
    q("globe-target").querySelector(".gp-cesium").innerHTML = "";
    P.target = createPanel("target", body);
    P.target.viewer.camera.setView({ destination: Cesium.Cartesian3.fromDegrees(20, 15, P.target.R * 2.1, P.target.ell) });
    document.querySelectorAll("#gp-body button").forEach((b) => b.classList.toggle("is-on", b.dataset.body === body));
    q("vc-target-title").textContent = `${body === "moon" ? "Moon" : "Mars"} target`;
    q("gp-target-dot").className = `gp-dot gp-dot--${body}`;
    buildLayerMenu(P.target);
    drawTargetMarks();
    updateModeButton(P.target);
    if (!state.selection) {
      q("gp-target-info").innerHTML = `<p class="gp-info__title">Select a region</p>
        <p>Click anywhere on ${body === "moon" ? "the Moon" : "Mars"} to draw a square region, or click a white NASA landing site.
        The data inside is checked before the analysis.</p>`;
    }
  }

  /* ---------------- snapshots (report) ---------------- */
  function scheduleSnap(panel) {
    clearTimeout(panel.snapTimer);
    panel.snapTimer = setTimeout(() => snap(panel), 900);
  }
  function snap(panel) {
    const v = panel.viewer;
    if (!v || v.isDestroyed() || !v.canvas.clientWidth) return;
    if (!v.scene.globe.tilesLoaded) { scheduleSnap(panel); return; }
    v.render();
    try { state.snaps[panel.key] = v.canvas.toDataURL("image/jpeg", 0.88); } catch { /* tainted: skip */ }
  }

  /* ---------------- public API ---------------- */
  function init() {
    if (!window.Cesium) {
      document.querySelectorAll(".gp-fallback").forEach((e) => { e.hidden = false; });
      return;
    }
    try {
      setBody(els.planet.value === "mars" ? "mars" : "moon");
      P.earth = createPanel("earth", "earth");
      P.earth.viewer.camera.setView({ destination: Cesium.Cartesian3.fromDegrees(-35, 5, P.earth.R * 2.2, P.earth.ell) });
      EARTH_OVERLAYS.filter((o) => o.on && !o.local).forEach((o) => setOverlay(P.earth, o.id, true));
      buildLayerMenu(P.earth);
      updateModeButton(P.earth);
    } catch (err) {
      console.warn("TwinMap disabled:", err);
      document.querySelectorAll(".gp-fallback").forEach((e) => { e.hidden = false; e.textContent = `3D globe unavailable (${err.message}).`; });
      return;
    }
    document.querySelectorAll("#gp-body button").forEach((b) => b.addEventListener("click", () => setBody(b.dataset.body)));
    q("gp-target-mode").addEventListener("click", () => P.target && toggleMode(P.target));
    q("gp-earth-mode").addEventListener("click", () => P.earth && toggleMode(P.earth));
    ["target", "earth"].forEach((k) => q(`gp-${k}-layers-btn`).addEventListener("click", () => {
      const box = q(`gp-${k}-layers`); box.hidden = !box.hidden;
    }));
    q("gp-matches").addEventListener("click", (e) => {
      const z = e.target.closest("button[data-zone]");
      if (z && z.dataset.zone !== activeZone) { setActiveZone(z.dataset.zone); return; }
      const b = e.target.closest("button[data-rank]");
      if (b) selectRegion(Number(b.dataset.rank));
    });
    els.planet.addEventListener("change", () => setBody(els.planet.value));
  }

  // called by app.js every time a region is selected (new analysis, zone switch, click)
  async function update(r) {
    if (!P.earth || !result) return;
    const t = result.target;
    const newResult = result !== state.lastResult;
    if (newResult) {
      state.lastResult = result;
      if (t.planet !== state.body) setBody(t.planet, false);
      if (!state.selection || Math.abs(state.selection.lat - t.lat) > 1e-3 || Math.abs(state.selection.lon - t.lon) > 1e-3) {
        state.selection = { lat: t.lat, lon: t.lon, radius: t.window_km, catalogue: t.custom ? null : t.location };
        selectTargetRegion(t.lat, t.lon, { radius: t.window_km, catalogue: state.selection.catalogue });
      }
      const [hLat, hLon] = regionHalfDeg(P.target, t.lat, t.window_km);
      goTo(P.target, [t.lon - hLon * 12, t.lat - hLat * 12, t.lon + hLon * 12, t.lat + hLat * 12], false);
      // similarity overlay in the background: markers and best matches never wait for it
      const on = q("gp-earth-layers").querySelector('[data-overlay="similarity"]');
      setOverlay(P.earth, "similarity", on ? on.checked : true)
        .catch((err) => console.warn("similarity overlay:", err));
    }
    drawEarthMarks(r);
    renderMatches();
    renderEarthInfo(r);
    const key = `${activeZone}:${r.rank}:${r.lat}:${r.lon}`;
    if (key !== state.lastRegionKey) {
      state.lastRegionKey = key;
      const span = 0.9;
      goTo(P.earth, [r.lon - span, r.lat - span * 0.7, r.lon + span, r.lat + span * 0.7], true);
    }
  }

  function snapshots() {
    ["target", "earth"].forEach((k) => { if (P[k]) snap(P[k]); });
    return { target: state.snaps.target || null, earth: state.snaps.earth || null,
             selection: state.selection, info: state.info };
  }

  function refresh() {
    ["target", "earth"].forEach((k) => { if (P[k]) { P[k].viewer.resize(); P[k].viewer.scene.requestRender(); } });
  }

  return { init, update, snapshots, refresh, setBody, state, panels: P };
})();

window.TwinMap = TwinMap;   // app.js checks window.TwinMap (top-level const is not a window property)
document.addEventListener("DOMContentLoaded", () => TwinMap.init());
