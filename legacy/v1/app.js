/*###########################################################################
# FRONTEND LOGIC - Planetary Analog Discovery System (vanilla JavaScript)
#
# Why this file exists:
#   Connects the interface (templates/index.html) to the Flask API:
#     GET  /api/status      -> dataset badges in the header
#     GET  /api/targets     -> location dropdown for the chosen planet
#     POST /api/similarity  -> run the analysis and fill the dashboard
#
# Libraries (loaded in index.html, pinned versions from cdnjs):
#   Leaflet 1.9.4  -> interactive maps
#   Chart.js 4.4.1 -> radar chart
#
# Map sources (official NASA tile services, no API key):
#   Earth : NASA GIBS  Blue Marble shaded relief (Web Mercator)
#   Mars  : NASA Trek  Viking MDIM 2.1 colour mosaic / MGS MOLA colour relief
#   Moon  : NASA Trek  LRO WAC global mosaic
#   Trek tiles are equirectangular -> Leaflet CRS EPSG:4326.
#
# Data roles respected in the display:
#   colours, radar axes  -> normalized values (same scale as the score)
#   tooltips, text       -> physical values (K, degrees, m)
#
# Mission planner (step 4):
#   - one-click scenarios (.scenario buttons) run a full analysis
#   - "rover-accessible only" + max slope are sent to the API; the backend
#     only proposes regions a rover can drive (scores are unchanged)
#   - the Mission brief card turns the result into an actionable answer
###########################################################################*/
"use strict";

/* ------------------------------------------------------------------
   DOM REFERENCES + STATE
------------------------------------------------------------------ */
const $ = (id) => document.getElementById(id);
const els = {
  status: $("dataset-status"), form: $("search-form"), planet: $("planet-select"),
  location: $("location-select"), button: $("search-button"), note: $("target-note"),
  message: $("message"), score: $("score-value"), confFill: $("confidence-fill"),
  confText: $("confidence-text"), factRegion: $("fact-region"), factPoint: $("fact-point"),
  matches: $("why-matches"), differs: $("why-differs"), whyRefine: $("why-refinement"),
  whySkipped: $("why-skipped"), ranking: $("ranking-body"), bars: $("feature-bars"),
  mapEmpty: $("map-empty"), legendMin: $("legend-min"), legendMax: $("legend-max"),
  targetTitle: $("target-map-title"), targetHint: $("target-map-hint"),
  radarCanvas: $("radar-canvas"), radarHint: $("radar-hint"),
  method: $("method"), methodText: $("method-text"),
  zone: $("zone-select"),
  roverMode: $("rover-mode"), maxSlope: $("max-slope"), maxSlopeValue: $("max-slope-value"),
  scenarios: document.querySelectorAll(".scenario"),
  brief: $("brief"), briefQuestion: $("brief-question"), briefAnswer: $("brief-answer"),
  briefEvidence: $("brief-evidence"), briefLimits: $("brief-limits"),
  briefWorldview: $("brief-worldview"), briefGmaps: $("brief-gmaps"), briefCopy: $("brief-copy"),
};
let activeScenario = null; // title of the clicked scenario (null = manual search)
let targets = {};          // GET /api/targets
let result = null;         // last POST /api/similarity answer
let selected = 0;          // index in result.ranking

/* ------------------------------------------------------------------
   API + FORMAT HELPERS
------------------------------------------------------------------ */
async function api(url, options = {}) {
  const res = await fetch(url, { headers: { "Content-Type": "application/json" }, ...options });
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.status === "error") throw new Error(data.message || `Request failed (${res.status})`);
  return data;
}

const isNum = (v) => typeof v === "number" && Number.isFinite(v);
const fmt = (v, d = 2) => (isNum(v) ? Number(v).toFixed(d) : "—");
const coord = (lat, lon, d = 3) =>
  `${Math.abs(lat).toFixed(d)}° ${lat < 0 ? "S" : "N"}, ${Math.abs(lon).toFixed(d)}° ${lon < 0 ? "W" : "E"}`;
const label = (f) => f.replace(/_/g, " ");
function physical(v, units) {
  if (!isNum(v)) return "—";
  const d = Math.abs(v) >= 100 ? 0 : Math.abs(v) >= 10 ? 1 : 2;
  return `${v.toFixed(d)}${units ? " " + units : ""}`;
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function showMessage(text, isError = false) {
  els.message.textContent = text;
  els.message.classList.toggle("message--error", isError);
  els.message.hidden = !text;
}
const unitsOf = (f) => {
  const c = result && result.comparison.find((x) => x.feature === f);
  return c ? c.units : "";
};

/* ------------------------------------------------------------------
   DATASET STATUS (header badges)
------------------------------------------------------------------ */
async function loadStatus() {
  try {
    const s = await api("/api/status");
    els.status.innerHTML = "";
    for (const [body, d] of Object.entries(s.datasets)) {
      const li = document.createElement("li");
      li.className = `status__item status__item--${d.loaded ? "ok" : "error"}`;
      li.textContent = d.loaded
        ? `${body}: ${d.rows.toLocaleString()} cells · ${d.available_features.length}/${s.features.length} features`
        : `${body}: not loaded`;
      li.title = d.loaded ? `Missing: ${d.missing_features.join(", ") || "none"}` : d.error;
      els.status.appendChild(li);
    }
  } catch {
    els.status.innerHTML = `<li class="status__item status__item--error">API unreachable</li>`;
  }
}

/* ------------------------------------------------------------------
   TARGET DROPDOWNS
------------------------------------------------------------------ */
async function loadTargets() {
  targets = await api("/api/targets");
  updateLocations();
}
function updateLocations() {
  const list = targets[els.planet.value] || [];
  els.location.innerHTML = list.map((n) => `<option value="${escapeHtml(n)}">${escapeHtml(n)}</option>`).join("");
  els.note.textContent = "";
}

/* ------------------------------------------------------------------
   RENDER: SCORE CARD
------------------------------------------------------------------ */
function renderScore(r) {
  els.score.textContent = isNum(r.score) ? Math.round(r.score) : "—";
  const conf = isNum(r.confidence) ? r.confidence : 0;
  els.confFill.style.width = `${conf * 100}%`;
  els.confText.textContent = `Confidence: ${Math.round(conf * 100)} % of the planned evidence was available and reliable`;
  els.factRegion.textContent = coord(r.lat, r.lon, 2);
  els.factPoint.textContent = r.refined ? coord(r.refined.lat, r.refined.lon, 3) : "no accessible cell";
}

/* ------------------------------------------------------------------
   RENDER: WHY THIS SITE?
------------------------------------------------------------------ */
function renderWhy(r) {
  const li = (items) => (items && items.length ? items.map((t) => `<li>${escapeHtml(t)}</li>`).join("")
    : `<li class="muted">—</li>`);
  els.matches.innerHTML = li(r.explanation.matches);
  els.differs.innerHTML = li(r.explanation.differs);
  const p = r.refined;
  els.whyRefine.textContent = p
    ? `Exact point chosen among ${p.candidates} accessible 1 km cells (${p.criteria}): ` +
      `elevation ${physical(p.elevation_m, "m")}, slope ${physical(p.slope_deg, "°")}, ` +
      `day ${physical(p.temperature_day_K, "K")}, night ${physical(p.temperature_night_K, "K")}.`
    : "No accessible 1 km cell (water or slope > 15°) in this region.";
  els.whySkipped.textContent = r.explanation.not_compared.length
    ? `Not compared: ${r.explanation.not_compared.join(" · ")}.` : "";
}

/* ------------------------------------------------------------------
   RENDER: RANKING TABLE (rows clickable)
------------------------------------------------------------------ */
function renderRanking(ranking) {
  if (!ranking.length) {
    els.ranking.innerHTML = `<tr><td colspan="6" class="table__empty">No ${escapeHtml(zn())} region matches (try a higher slope limit).</td></tr>`;
    return;
  }
  els.ranking.innerHTML = ranking.map((r, i) => `
    <tr data-rank="${i}" class="${i === selected ? "is-selected" : ""}" tabindex="0">
      <td>${r.rank}</td>
      <td>${coord(r.lat, r.lon, 2)}</td>
      <td>${fmt(r.score, 1)}</td>
      <td>${isNum(r.confidence) ? Math.round(r.confidence * 100) + "%" : "—"}</td>
      <td>${isNum(r.accessible_pct) ? r.accessible_pct + "%" : "—"}</td>
      <td>${r.refined ? coord(r.refined.lat, r.refined.lon, 3) : "—"}</td>
    </tr>`).join("");
}

/* ------------------------------------------------------------------
   RENDER: FEATURE COMPARISON (bars normalized, text physical)
------------------------------------------------------------------ */
function renderFeatures(comparison) {
  const byFeature = Object.fromEntries(comparison.map((c) => [c.feature, c]));
  for (const row of els.bars.querySelectorAll(".bars__row")) {
    const c = byFeature[row.dataset.feature];
    const used = c && c.status === "used";
    const t = c ? c.target_normalized : null, e = c ? c.earth_normalized : null;
    row.querySelector(".bars__fill--target").style.width = isNum(t) ? `${t * 100}%` : "0";
    row.querySelector(".bars__fill--earth").style.width = isNum(e) ? `${e * 100}%` : "0";
    row.querySelector(".bars__value").textContent =
      c ? `${physical(c.target_value, c.units)} · ${physical(c.earth_value, c.units)}` : "—";
    row.title = c ? (used ? `Used for scoring · ${fmt(c.share_of_distance_pct, 1)} % of the distance` : c.status) : "";
    row.classList.toggle("bars__row--missing", !used);
  }
}

/*###########################################################################
# EARTH MAP (Leaflet + NASA GIBS)
#   one rectangle per ~11 km cell, colour = similarity (blue -> red)
###########################################################################*/
const GIBS_URL = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/" +
  "GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg";
const SIM_RAMP = [[44, 123, 182], [171, 217, 233], [255, 255, 191], [253, 174, 97], [215, 25, 28]];
function simColor(t) {
  const x = Math.min(Math.max(t, 0), 1) * (SIM_RAMP.length - 1);
  const i = Math.min(Math.floor(x), SIM_RAMP.length - 2), f = x - i;
  const c = SIM_RAMP[i].map((v, k) => Math.round(v + (SIM_RAMP[i + 1][k] - v) * f));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}

/*---------------------------------------------------------------------------
  EARTH ZONES: one Leaflet map per zone (Atacama = default, Merzouga = second zone).
  Both zones are analysed at every search; `activeZone` decides which one drives the
  ranking, brief, radar, use cases, validation, ML and assistant. `result` always points
  to the active zone's analysis, so every other renderer works unchanged.
---------------------------------------------------------------------------*/
const results = {};            // zone id -> POST /api/similarity answer
let activeZone = "atacama";
const ZONE_MAPS = {
  atacama: { el: "earth-map", empty: "map-empty", legendMin: "legend-min", legendMax: "legend-max",
             badge: "badge-atacama", view: [[-23.5, -68], 7] },
  merzouga: { el: "merzouga-map", empty: "mz-map-empty", legendMin: "mz-legend-min", legendMax: "mz-legend-max",
              badge: "badge-merzouga", view: [[31, -4], 7.5] },
};
const earth = ZONE_MAPS.atacama;      // the original Atacama map object (kept for compatibility)
const zn = () => (result && result.zone ? result.zone.name : "Atacama");
const zfull = () => (result && result.zone ? result.zone.full_name : "Atacama Desert (Chile)");

function ensureZoneMap(zone) {
  const z = ZONE_MAPS[zone];
  if (z.map || !window.L) return !!z.map;
  z.map = L.map(z.el, { zoomSnap: 0.5, worldCopyJump: false }).setView(z.view[0], z.view[1]);
  L.tileLayer(GIBS_URL, {
    maxNativeZoom: 8, maxZoom: 12,
    attribution: 'Imagery <a href="https://earthdata.nasa.gov/gibs">NASA GIBS</a> · Blue Marble',
  }).addTo(z.map);
  z.renderer = L.canvas({ padding: 0.5 });
  z.cells = L.layerGroup().addTo(z.map);
  z.markers = L.layerGroup().addTo(z.map);
  return true;
}

function drawZoneMap(zone, fit) {
  const z = ZONE_MAPS[zone], res = results[zone];
  if (!res || !res.map) return;
  if (!ensureZoneMap(zone)) {
    $(z.empty).textContent = "The interactive map needs an internet connection (Leaflet + NASA tiles).";
    return;
  }
  z.cells.clearLayers();
  const step = res.map_cell_deg, h = step / 2;
  // Colour = RANK of the score among the zone's cells (quantile stretch). Scores are
  // often packed in a narrow band (e.g. 80-87 for Mars); a linear stretch would
  // paint almost everything red. Red = top of the ranking, blue = bottom.
  const sorted = res.map.map((c) => c.score).filter(isNum).sort((a, b) => a - b);
  const sMin = sorted[0], sMax = sorted[sorted.length - 1];
  const rankOf = (s) => {
    let lo = 0, hi = sorted.length;
    while (lo < hi) { const mid = (lo + hi) >> 1; if (sorted[mid] < s) lo = mid + 1; else hi = mid; }
    return sorted.length > 1 ? lo / (sorted.length - 1) : 1;
  };
  const rover = res.method.rover || {};
  const typeMode = zone === activeZone && ml.data && ml.mapType !== null;
  for (const c of res.map) {
    const has = isNum(c.score);
    const blocked = rover.enabled && isNum(c.accessible) && c.accessible < rover.min_accessible_fraction;
    const rect = L.rectangle([[c.lat - h, c.lon - h], [c.lat + h, c.lon + h]], {
      renderer: z.renderer, weight: 0,
      fillOpacity: typeMode ? (mlTypeOf(c) === ml.mapType ? 0.78 : 0.3) : !has ? 0.45 : blocked ? 0.55 : 0.62,
      fillColor: typeMode
        ? (mlTypeOf(c) === ml.mapType ? ml.data.clustering.types[ml.mapType].color : "#3a4258")
        : !has ? "#2a3350" : blocked ? "#4a5068" : simColor(rankOf(c.score)),
    });
    const drive = isNum(c.accessible) ? `<br>drivable: ${Math.round(c.accessible * 100)} % (≤ ${rover.max_slope_deg}°)` : "";
    rect.bindTooltip(`${coord(c.lat, c.lon, 2)}<br>${has ? `score <b>${fmt(c.score, 1)}</b>` : "insufficient data"}` +
      drive + (blocked ? "<br><i>not proposed: too steep for a rover</i>" : ""),
      { sticky: true, direction: "top", opacity: 0.95 });
    rect.on("click", () => onZoneCellClick(zone, c));
    z.cells.addLayer(rect);
  }
  $(z.legendMin).textContent = fmt(sMin, 0);
  $(z.legendMax).textContent = fmt(sMax, 0);
  $(z.empty).hidden = true;
  $(z.badge).hidden = zone !== activeZone;
  if (fit) {
    const lats = res.map.map((c) => c.lat), lons = res.map.map((c) => c.lon);
    z.map.fitBounds([[Math.min(...lats) - h, Math.min(...lons) - h], [Math.max(...lats) + h, Math.max(...lons) + h]]);
  }
}

function drawZoneMarkers(zone, activeCell) {
  const z = ZONE_MAPS[zone], res = results[zone];
  if (!z.map || !res) return;
  const isActive = zone === activeZone;
  const sel = isActive ? selected : -1;
  z.markers.clearLayers();
  const h = res.map_cell_deg / 2;
  res.ranking.forEach((r, i) => {
    const on = i === sel;
    const m = L.marker([r.lat, r.lon], {
      icon: L.divIcon({ className: "", iconSize: on ? [26, 26] : [22, 22],
        html: `<div class="rank-marker${on ? " rank-marker--selected" : ""}">${r.rank}</div>` }),
      zIndexOffset: on ? 1000 : 0, keyboard: false,
    });
    m.on("click", () => { if (zone !== activeZone) setActiveZone(zone); selectRegion(i); });
    m.bindTooltip(`#${r.rank} · score ${fmt(r.score, 1)}`, { direction: "top" });
    z.markers.addLayer(m);
  });
  // Reference analog sites used for validation (never used in the score)
  for (const v of ((res.validation || {}).sites || [])) {
    const pct = isNum(v.percentile) ? ` · our percentile ${Math.round(v.percentile)} %` : "";
    z.markers.addLayer(L.marker([v.lat, v.lon], {
      icon: L.divIcon({ className: "", html: '<div class="site-marker">▲</div>', iconSize: [16, 16], iconAnchor: [8, 8] }),
      zIndexOffset: 1200, keyboard: false,
    }).bindTooltip(`<b>${escapeHtml(v.name)}</b><br>${escapeHtml(v.program)}${pct}`, { direction: "top" }));
  }
  const pr = res.ranking[isActive ? selected : 0];
  const p = pr && pr.refined;
  if (p) {
    z.markers.addLayer(L.marker([p.lat, p.lon], {
      icon: L.divIcon({ className: "", html: '<div class="star-marker">★</div>', iconSize: [20, 20], iconAnchor: [10, 10] }),
      zIndexOffset: 1500,
    }).bindPopup(`<b>Exact point (≈1 km)</b><br>${coord(p.lat, p.lon, 3)}<br>elevation ${physical(p.elevation_m, "m")}, ` +
      `slope ${physical(p.slope_deg, "°")}<br>day ${physical(p.temperature_day_K, "K")}, night ${physical(p.temperature_night_K, "K")}`));
  }
  if (activeCell) {
    z.markers.addLayer(L.rectangle(
      [[activeCell.lat - h, activeCell.lon - h], [activeCell.lat + h, activeCell.lon + h]],
      { color: "#ffffff", weight: 2, fill: false, interactive: false }));
  }
}

// Original entry points, now drawing every zone map (names kept: used across the file)
function drawEarthMap(fit) { Object.keys(ZONE_MAPS).forEach((zone) => drawZoneMap(zone, fit)); }
function drawEarthMarkers(activeCell) {
  Object.keys(ZONE_MAPS).forEach((zone) => drawZoneMarkers(zone, zone === activeZone ? activeCell : null));
}

function onZoneCellClick(zone, c) {
  if (zone !== activeZone) setActiveZone(zone);
  selectCell(c);
}

/*###########################################################################
# TARGET MAP (Leaflet + NASA Trek, equirectangular -> EPSG:4326)
###########################################################################*/
const TREK = "https://trek.nasa.gov/tiles";
const TARGET_LAYERS = {
  mars: [
    { name: "Viking colour mosaic", url: `${TREK}/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg`, native: 7 },
    { name: "MOLA colour relief", url: `${TREK}/Mars/EQ/Mars_MGS_MOLA_ClrShade_merge_global_463m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg`, native: 6 },
  ],
  moon: [
    { name: "LRO WAC mosaic", url: `${TREK}/Moon/EQ/LRO_WAC_Mosaic_Global_303ppd_v02/1.0.0/default/default028mm/{z}/{y}/{x}.jpg`, native: 7 },
  ],
};
const BODY_RADIUS_KM = { mars: 3396.0, moon: 1737.4 };
const tmap = { map: null, body: null };

function drawTargetMap(t) {
  if (!window.L) return;
  if (tmap.map && tmap.body !== t.planet) { tmap.map.remove(); tmap.map = null; }
  if (!tmap.map) {
    tmap.map = L.map("target-map", { crs: L.CRS.EPSG4326, zoomSnap: 0.5, minZoom: 1, maxZoom: 9 });
    const layers = {};
    TARGET_LAYERS[t.planet].forEach((d, i) => {
      const layer = L.tileLayer(d.url, { maxNativeZoom: d.native, maxZoom: 9, noWrap: true,
        attribution: '<a href="https://trek.nasa.gov">NASA Trek</a>' });
      layers[d.name] = layer;
      if (i === 0) layer.addTo(tmap.map);
    });
    if (Object.keys(layers).length > 1) L.control.layers(layers, null, { collapsed: true }).addTo(tmap.map);
    tmap.map.overlay = L.layerGroup().addTo(tmap.map);
    tmap.body = t.planet;
    const empty = $("target-map").querySelector(".map-empty");
    if (empty) empty.hidden = true;
  }
  // circle of window_km drawn in degrees (body radius, not Earth's)
  const dLat = (t.window_km / BODY_RADIUS_KM[t.planet]) * 180 / Math.PI;
  const ring = [];
  for (let a = 0; a <= 360; a += 6) {
    const r = a * Math.PI / 180;
    ring.push([t.lat + dLat * Math.sin(r), t.lon + dLat * Math.cos(r) / Math.cos(t.lat * Math.PI / 180)]);
  }
  tmap.map.overlay.clearLayers();
  tmap.map.overlay.addLayer(L.polygon(ring, { color: "#ff7a45", weight: 2, fillOpacity: 0.08 }));
  tmap.map.overlay.addLayer(L.circleMarker([t.lat, t.lon], { radius: 5, color: "#fff", fillColor: "#ff7a45", fillOpacity: 1, weight: 2 })
    .bindTooltip(`${t.location} · ${coord(t.lat, t.lon, 2)}`, { direction: "top" }));
  tmap.map.setView([t.lat, t.lon], 5.5);
  els.targetTitle.textContent = `${t.planet === "mars" ? "Mars" : "Moon"} · ${t.location}`;
  els.targetHint.textContent = `${t.note}. Circle = ${t.window_km} km area (${t.cells_in_window} cells) averaged into the target profile. Basemap: NASA Trek.`;
}

/*###########################################################################
# RADAR (Chart.js): target vs one Atacama cell
#   axes: normalized values (same scale as the score); tooltips: physical units
###########################################################################*/
let radar = null;

function renderRadar(cell) {
  if (!window.Chart || !result) return;
  const feats = result.method.features_used;
  const labels = feats.map(label);
  const tVals = feats.map((f) => result.target_values[f]);
  const eVals = feats.map((f) => (cell.values ? cell.values[f] : null));
  const targetName = result.target.location;
  const cellName = `${zn()} ${coord(cell.lat, cell.lon, 2)}`;
  const tooltip = (ctx) => {
    const f = feats[ctx.dataIndex];
    const phys = ctx.datasetIndex === 0 ? result.target_physical[f] : (cell.physical || {})[f];
    return `${ctx.dataset.label}: ${physical(phys, unitsOf(f))} (normalized ${fmt(ctx.raw, 2)})`;
  };
  if (!radar) {
    Chart.defaults.color = "#9aa6c2";
    radar = new Chart(els.radarCanvas, {
      type: "radar",
      data: {
        labels,
        datasets: [
          { label: targetName, data: tVals, borderColor: "#ff7a45", backgroundColor: "rgba(255,122,69,.18)", pointBackgroundColor: "#ff7a45", borderWidth: 2 },
          { label: cellName, data: eVals, borderColor: "#8fb3ff", backgroundColor: "rgba(143,179,255,.18)", pointBackgroundColor: "#8fb3ff", borderWidth: 2 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false, animation: { duration: 400 },
        scales: { r: { min: 0, max: 1, ticks: { display: false, stepSize: 0.25 },
          grid: { color: "rgba(255,255,255,.08)" }, angleLines: { color: "rgba(255,255,255,.1)" },
          pointLabels: { color: "#c9d2e6", font: { size: 11 } } } },
        plugins: { legend: { position: "bottom", labels: { color: "#e8ecf5", boxWidth: 12 } },
          tooltip: { callbacks: { label: tooltip } } },
      },
    });
  } else {
    radar.data.labels = labels;
    radar.data.datasets[0].label = targetName;
    radar.data.datasets[0].data = tVals;
    radar.data.datasets[1].label = cellName;
    radar.data.datasets[1].data = eVals;
    radar.options.plugins.tooltip.callbacks.label = tooltip;
    radar.update();
  }
  els.radarHint.textContent = isNum(cell.score)
    ? `Similarity of this cell: ${fmt(cell.score, 1)} / 100. Axes on the normalized scale; hover for physical values.`
    : "This cell lacks some features, so it is not scored.";
}

/*###########################################################################
# MISSION BRIEF - the actionable answer (question -> site -> evidence -> limits)
###########################################################################*/
const DATASETS = {
  mars: "Mars: MGS MOLA topography, MGS TES albedo & thermal inertia",
  moon: "Moon: LRO LOLA topography, LRO Diviner temperatures, LROC WAC albedo",
};

function renderBrief(r) {
  const t = result.target, rover = result.method.rover || {}, p = r.refined;
  const body = t.planet === "mars" ? "Mars" : "the Moon";
  const what = activeScenario || "A field test";
  els.briefQuestion.textContent = `${what} for ${t.location} (${body}): where should the team test on Earth?`;

  const site = p || { lat: r.lat, lon: r.lon };
  let answer = `Go to <strong>${coord(site.lat, site.lon, 3)}</strong> in ${escapeHtml(zfull())} ` +
    `(region #${r.rank}, centre ${coord(r.lat, r.lon, 2)}): similarity <strong>${fmt(r.score, 1)} / 100</strong>, ` +
    `confidence ${Math.round((r.confidence || 0) * 100)} %.`;
  if (rover.enabled && isNum(r.accessible_pct)) {
    answer += ` ${r.accessible_pct} % of the region is drivable below ${rover.max_slope_deg}°`;
    answer += p && isNum(p.slope_deg)
      ? `; the exact point has a ${p.slope_deg.toFixed(1)}° slope at ${Math.round(p.elevation_m).toLocaleString("en")} m.`
      : ".";
  }
  els.briefAnswer.innerHTML = answer;

  const scored = result.method.cells_scored, dist = result.method.score_distribution;
  const evidence = [
    ...r.explanation.matches.map((m) => `Close match — ${m}`),
    `Ranked #${r.rank} of ${scored.toLocaleString()} scored ${zn()} cells (scores ${fmt(dist.min, 0)}–${fmt(dist.max, 0)}).`,
    `NASA data — Earth: NASADEM, MODIS land surface temperature, NASA POWER albedo · ${DATASETS[t.planet]}.`,
  ];
  const limits = [
    ...r.explanation.differs.map((d) => `Differs — ${d}`),
    ...r.explanation.not_compared.filter((n) => !n.startsWith("elevation")).map((n) => `Not compared — ${n}`),
    "Exact point at ~1 km resolution: check access, permits and local terrain on site.",
  ];
  const li = (a) => a.map((x) => `<li>${escapeHtml(x)}</li>`).join("");
  els.briefEvidence.innerHTML = li(evidence);
  els.briefLimits.innerHTML = li(limits);

  els.briefWorldview.href = `https://worldview.earthdata.nasa.gov/?v=${(site.lon - 0.4).toFixed(3)},` +
    `${(site.lat - 0.3).toFixed(3)},${(site.lon + 0.4).toFixed(3)},${(site.lat + 0.3).toFixed(3)}`;
  els.briefGmaps.href = `https://www.google.com/maps/search/?api=1&query=${site.lat},${site.lon}`;
  els.brief.hidden = false;
  els.brief.dataset.text = [
    `MISSION BRIEF — ${els.briefQuestion.textContent}`, "",
    `ANSWER: ${els.briefAnswer.textContent}`, "",
    "EVIDENCE:", ...evidence.map((x) => `- ${x}`), "",
    "LIMITS:", ...limits.map((x) => `- ${x}`), "",
    `Coordinates: ${site.lat}, ${site.lon}`,
    `NASA Worldview: ${els.briefWorldview.href}`,
    "Generated by the Planetary Analog Discovery System (NASA Space Apps).",
  ].join("\n");
}

/*###########################################################################
# PROBLEMS THIS STUDY CAN SOLVE (bottom section)
#   Static questions; after each search every question gets an answer computed
#   for the selected target from PHYSICAL values (explanation role only).
#   status: "ok" = answered, "partial" = data missing on one body,
#           "na" = not applicable / no data for this target.
###########################################################################*/
const USE_CASES = [
  { id: "analogs", q: "Where on Earth (Atacama or Merzouga) should a Mars or Moon rover be tested?",
    features: "slope, roughness, relief, albedo, day/night temperature", example: "The 10 regions of the Earth zone closest to Jezero." },
  { id: "traverse", q: "Can a rover drive here?",
    features: "slope, roughness, relief (+ thermal inertia on Mars)", example: "Drivable / too steep map for the Earth zone." },
  { id: "thermal", q: "What temperatures must the hardware survive?",
    features: "day & night temperature, day–night swing", example: "Battery and electronics range at the target vs the test site." },
  { id: "soil", q: "Is the ground dust, sand or rock?",
    features: "thermal inertia + albedo (Mars only today)", example: "Dust / sand / rock class: sinking risk for the wheels." },
  { id: "ice", q: "Where could water ice survive on the Moon?",
    features: "day/night temperature, 80–90° S band", example: "Cold traps staying below ~110 K all day." },
  { id: "base", q: "Where to build a base?",
    features: "flat terrain, moderate temperatures, iron (Mars only)", example: "Ranking of zones for a habitat." },
  { id: "why", q: "Why does this Earth zone resemble Mars (education / outreach)?",
    features: "all features", example: "Charts comparing Earth, Mars and the Moon on the same axes." },
];
const BADGE = { ok: "✅", partial: "🟡", na: "⛔" };

const kToC = (k) => (isNum(k) ? `${Math.round(k - 273.15)} °C` : "—");
const num = (v, d = 0) => (isNum(v) ? Number(v).toFixed(d) : "—");

function useCaseAnswers(r) {
  const t = result.target, tp = t.profile_physical || {}, m = result.method, rover = m.rover || {};
  const earthVal = (f) => { const c = r.comparison.find((x) => x.feature === f); return c ? c.earth_value : null; };
  const isMars = t.planet === "mars";
  const estimated = (m.target_uncertainty || {}).temperature_day >= 0.5;
  const out = {};

  const top3 = result.ranking.slice(0, 3).map((x) => `#${x.rank} ${coord(x.lat, x.lon, 2)} (${fmt(x.score, 1)})`).join(", ");
  out.analogs = { status: "ok", text: `Top regions for <strong>${escapeHtml(t.location)}</strong>: ${top3}. ` +
    (r.refined ? `Recommended exact point: <strong>${coord(r.refined.lat, r.refined.lon, 3)}</strong>.` : "") };

  const acc = isNum(r.accessible_pct) ? `${r.accessible_pct} % of region #${r.rank} is drivable below ${rover.max_slope_deg}°` : "";
  const elig = rover.enabled && isNum(rover.eligible_regions)
    ? `${rover.eligible_regions.toLocaleString()} of ${m.cells_scored.toLocaleString()} ${zn()} regions pass the ${rover.max_slope_deg}° rover filter. ` : "";
  out.traverse = { status: "ok", text: `${elig}${acc}` +
    (r.refined && isNum(r.refined.slope_deg) ? `; the exact point has a ${r.refined.slope_deg.toFixed(1)}° slope. ` : ". ") +
    `Target terrain: mean slope ${num(tp.slope, 1)}°, relief ${num(tp.relief)} m (${zn()} site: ${num(earthVal("slope"), 1)}°, ${num(earthVal("relief"))} m).` };

  const tSwing = isNum(tp.temperature_day) && isNum(tp.temperature_night) ? tp.temperature_day - tp.temperature_night : null;
  out.thermal = { status: "ok", text: `At ${escapeHtml(t.location)}: <strong>${kToC(tp.temperature_night)} to ${kToC(tp.temperature_day)}</strong> ` +
    `(swing ${num(tSwing)} K${estimated ? ", estimated" : ""}). ${zn()} test site: ${kToC(earthVal("temperature_night"))} to ` +
    `${kToC(earthVal("temperature_day"))}. Hardware tested here still needs a thermal-vacuum test for the colder nights.` };

  if (isMars && isNum(tp.thermal_inertia)) {
    const ti = tp.thermal_inertia;
    const cls = ti < 100 ? "fine dust — high sinking risk for wheels" : ti < 350 ? "sand / loose fine material — moderate risk"
      : "rocky, crusted or bedrock — firm ground";
    out.soil = { status: "partial", text: `Thermal inertia <strong>${num(ti)}</strong> J m⁻² K⁻¹ s⁻½ with albedo ${num(tp.albedo, 2)}: ` +
      `<strong>${cls}</strong>. No Earth thermal-inertia map yet, so the ${zn()} site cannot be classified the same way.` };
  } else {
    out.soil = { status: "na", text: isMars ? "No thermal inertia available at this target."
      : "Not available for the Moon yet: needs the Diviner thermal-inertia (H-parameter) map." };
  }

  if (isMars) {
    out.ice = { status: "na", text: "Lunar question: select a Moon target. (Mars ice would need neutron / radar data.)" };
  } else {
    const dayMax = tp.temperature_day;
    out.ice = { status: "partial", text: isNum(dayMax) && dayMax < 110
      ? `Possible: the daytime maximum here is only ${num(dayMax)} K, below the ~110 K ice stability limit.`
      : `<strong>No</strong> at ${escapeHtml(t.location)}: the daytime maximum (${num(dayMax)} K) is far above ~110 K. ` +
        "Only permanently shadowed polar craters qualify (80–90° S Diviner band downloaded)." };
  }

  const flat = isNum(tp.slope) ? (tp.slope < 5 ? "flat enough" : "too steep for easy construction") : "—";
  const fe = isMars && isNum(tp.mineral_index)
    ? `Iron <strong>${num(tp.mineral_index, 1)} wt%</strong> (Mars average ≈ 14 %: ${tp.mineral_index > 14 ? "above" : "below"} average, a resource for construction).`
    : "Iron: no lunar map yet (Lunar Prospector Fe would fill this gap).";
  out.base = { status: isMars ? "ok" : "partial", text: `Terrain: mean slope ${num(tp.slope, 1)}° (${flat}), relief ${num(tp.relief)} m. ` +
    `Thermal swing ${num(tSwing)} K. ${fe}` };

  const ex = r.explanation || {};
  out.why = { status: "ok", text: `Similarity <strong>${fmt(r.score, 1)} / 100</strong>. Closest: ${escapeHtml((ex.matches || []).join("; "))}. ` +
    `Main difference: ${escapeHtml((ex.differs || [])[0] || "—")}.` };
  return out;
}

function renderUseCases(r) {
  const answers = result && r ? useCaseAnswers(r) : null;
  $("usecases-target").textContent = answers
    ? `Answers for ${result.target.location} (${result.target.planet === "mars" ? "Mars" : "Moon"}), region #${r.rank}.`
    : "Run a search: every answer below is then computed for the selected target.";
  $("usecases-list").innerHTML = USE_CASES.map((u) => {
    const a = answers && answers[u.id];
    const status = a ? a.status : null;
    return `<li class="usecase${status === "na" ? " usecase--na" : ""}">
      <p class="usecase__q">${status ? BADGE[status] + " " : ""}${escapeHtml(u.q)}</p>
      <p class="usecase__a">${a ? a.text : `<em>Example:</em> ${escapeHtml(u.example)}`}</p>
      <p class="usecase__meta">Features: ${escapeHtml(u.features)}</p>
    </li>`;
  }).join("");
}

/* ------------------------------------------------------------------
   SELECTION
   selectRegion(i): a ranked region -> every card + map + radar
   selectCell(c)  : any map cell -> radar + highlight (ranked -> full update)
------------------------------------------------------------------ */
const findCell = (lat, lon) => result.map.find((c) => Math.abs(c.lat - lat) < 1e-6 && Math.abs(c.lon - lon) < 1e-6);

function selectRegion(i) {
  if (!result || !result.ranking[i]) return;
  selected = i;
  const r = result.ranking[i];
  renderScore(r);
  renderWhy(r);
  renderBrief(r);
  renderUseCases(r);
  renderFeatures(r.comparison);
  renderRanking(result.ranking);
  const cell = findCell(r.lat, r.lon);
  drawEarthMarkers(cell);
  if (cell) renderRadar(cell);
  const zm = ZONE_MAPS[activeZone];
  if (zm && zm.map) zm.map.panTo([r.lat, r.lon], { animate: true });
}

function selectCell(c) {
  const i = result.ranking.findIndex((r) => Math.abs(r.lat - c.lat) < 1e-6 && Math.abs(r.lon - c.lon) < 1e-6);
  if (i >= 0) { selectRegion(i); return; }
  drawEarthMarkers(c);
  renderRadar(c);
}

/* ------------------------------------------------------------------
   SEARCH (form submit -> POST /api/similarity)
------------------------------------------------------------------ */
/* ------------------------------------------------------------------
   ZONE TEXTS (shared by a new search and a zone switch)
------------------------------------------------------------------ */
const VALIDATION_NOTE_DEFAULT = $("validation-note") ? $("validation-note").innerHTML : "";
const VALIDATION_NOTE_ZONE = {
  merzouga: "<strong>How to read it.</strong> MARS2013 (Austrian Space Forum, February 2013) ran a one-month crewed " +
    "Mars simulation near Erfoud: the base camp “Weyprecht” and the forward rover camp “Payer” are both inside the " +
    "Merzouga study area. A high percentile means our system independently points to the terrain that mission chose. " +
    "At ~3.7 km our features cannot see dune shapes, so the Erg Chebbi dunes themselves are not singled out.",
};

function renderZoneTexts() {
  const t = result.target, m = result.method;
  document.querySelectorAll(".zn").forEach((e) => { e.textContent = zn(); });
  els.note.textContent = `${t.location} (${coord(t.lat, t.lon, 2)}) — ${t.note}. ` +
    `Target profile = mean of ${t.cells_in_window} cells within ${t.window_km} km. Earth zone analysed: ${zfull()}.`;
  els.methodText.textContent =
    `Scored ${m.cells_scored.toLocaleString()} ${zn()} cells on ${m.features_used.length} shared features ` +
    `(${m.features_used.join(", ")}) with normalized harmonized data; weighted distance, uncertain values ` +
    `(estimated temperatures, proxy albedo) down-weighted by ${m.uncertainty_penalty * 100} %. ` +
    `Scores range ${fmt(m.score_distribution.min, 0)}–${fmt(m.score_distribution.max, 0)} ` +
    `(median ${fmt(m.score_distribution.median, 0)}). Physical values come from the non-normalized harmonized ` +
    `data; exact points from the 1 km Earth processed data. The Atacama and Merzouga share the same pipeline and ` +
    `the same 0–1 scale, so their scores can be compared.`;
  els.method.hidden = false;
  showMessage(result.ranking.length
    ? `Best ${zn()} analog for ${t.location}: ${fmt(result.score, 1)} / 100.`
    : `No ${zn()} cell has enough data for this target.`, !result.ranking.length);
  if ($("validation-note")) $("validation-note").innerHTML = VALIDATION_NOTE_ZONE[activeZone] || VALIDATION_NOTE_DEFAULT;
}

/* ------------------------------------------------------------------
   SEARCH (form submit -> POST /api/similarity for EVERY Earth zone)
------------------------------------------------------------------ */
async function runSearch(event) {
  event.preventDefault();
  els.button.disabled = true;
  els.button.textContent = "Analyzing…";
  showMessage("");
  try {
    const payload = { planet: els.planet.value, location: els.location.value,
      rover_mode: els.roverMode.checked, max_slope: Number(els.maxSlope.value) };
    const zones = Object.keys(ZONE_MAPS);
    const answers = await Promise.allSettled(zones.map((zone) => api("/api/similarity", {
      method: "POST", body: JSON.stringify({ ...payload, zone }) })));
    zones.forEach((zone, i) => {
      if (answers[i].status === "fulfilled") results[zone] = answers[i].value; else delete results[zone];
    });
    const wanted = els.zone.value;
    activeZone = results[wanted] ? wanted : zones.find((zone) => results[zone]);
    if (!activeZone) throw (answers.find((a) => a.status === "rejected") || {}).reason || new Error("Analysis failed");
    els.zone.value = activeZone;
    result = results[activeZone];
    renderZoneTexts();
    selected = 0;
    if (!result.ranking.length) { els.brief.hidden = true; renderUseCases(null); }
    ml.mapType = null;            // new search: map back to similarity colours
    drawEarthMap(true);
    drawTargetMap(result.target);
    renderValidation();
    loadML();
    selectRegion(0);
    renderComparison();
  } catch (err) {
    showMessage(err.message, true);
  } finally {
    els.button.disabled = false;
    els.button.textContent = "Find Earth Analogs";
  }
}

/* ------------------------------------------------------------------
   ZONE SWITCH (selector, comparison buttons, click on a zone map)
   No new request: both zones were analysed by the last search.
------------------------------------------------------------------ */
function setActiveZone(zone) {
  if (!results[zone]) { els.zone.value = activeZone; return; }
  activeZone = zone;
  result = results[zone];
  els.zone.value = zone;
  selected = 0;
  ml.mapType = null;
  renderZoneTexts();
  if (!result.ranking.length) { els.brief.hidden = true; renderUseCases(null); }
  drawEarthMap(false);
  renderValidation();
  loadML();
  selectRegion(0);
  renderComparison();
}

/* ------------------------------------------------------------------
   EARTH ZONES COMPARED (Atacama vs Merzouga for the same target)
   Scores come from the normalized data (same scale for both zones);
   the table shows physical values of each zone's best region.
------------------------------------------------------------------ */
function renderComparison() {
  const zones = Object.keys(ZONE_MAPS).filter((zone) => results[zone]);
  if (!zones.length) return;
  const t = results[zones[0]].target;
  $("compare-target").textContent = `Target: ${t.location} (${t.planet === "mars" ? "Mars" : "Moon"}). ` +
    `Same pipeline, same features, same 0–1 scale for both Earth zones.`;
  const scored = zones.filter((zone) => isNum(results[zone].score));
  const winner = scored.length ? scored.reduce((a, b) => (results[a].score >= results[b].score ? a : b)) : null;
  $("compare-scores").innerHTML = zones.map((zone) => {
    const r = results[zone], best = r.ranking[0], p = best && best.refined;
    return `<div class="zscore${zone === winner ? " is-winner" : ""}${zone === activeZone ? " is-active" : ""}">
      <span class="zscore__name">${escapeHtml(r.zone.full_name)}</span>
      <span class="zscore__value">${fmt(r.score, 1)} <small>/ 100</small></span>
      <span class="zscore__meta">confidence ${Math.round((r.confidence || 0) * 100)} %${best && isNum(best.accessible_pct) ? ` · ${best.accessible_pct} % drivable` : ""}</span>
      <span class="zscore__meta">${p ? `exact point ${coord(p.lat, p.lon, 3)}` : "no accessible point"}</span>
      <button type="button" class="zscore__btn" data-zone="${zone}" ${zone === activeZone ? "disabled" : ""}>
        ${zone === activeZone ? "Analysed in detail" : "Analyse this zone in detail"}</button>
    </div>`;
  }).join("");
  if (scored.length === 2) {
    const [a, b] = scored[0] === winner ? scored : [scored[1], scored[0]];
    const diff = results[a].score - results[b].score;
    $("compare-verdict").innerHTML = `<strong>${escapeHtml(results[a].zone.name)}</strong> is the closer analog for ` +
      `${escapeHtml(t.location)} (+${fmt(diff, 1)} points over ${escapeHtml(results[b].zone.name)}).`;
  } else {
    $("compare-verdict").textContent = "";
  }

  // feature table: target vs each zone's best region (physical values)
  const feats = results[zones[0]].method.features_used;
  const row = (zone, f) => {
    const best = results[zone] && results[zone].ranking[0];
    return best ? best.comparison.find((c) => c.feature === f) : null;
  };
  $("compare-body").innerHTML = feats.map((f) => {
    const cells = zones.map((zone) => row(zone, f));
    const diffs = cells.map((c) => (c && isNum(c.difference_normalized) ? c.difference_normalized : Infinity));
    const bestIdx = diffs.indexOf(Math.min(...diffs));
    const ref = cells.find(Boolean) || {};
    const zoneCells = ["atacama", "merzouga"].map((zone) => {
      const i = zones.indexOf(zone), c = i >= 0 ? cells[i] : null;
      return `<td class="${i === bestIdx && zones.length > 1 ? "is-closer" : ""}">${c ? physical(c.earth_value, c.units) : "—"}${i === bestIdx && zones.length > 1 ? " ✓" : ""}</td>`;
    }).join("");
    return `<tr><td>${escapeHtml(label(f))}</td><td>${physical(ref.target_value, ref.units)}</td>${zoneCells}</tr>`;
  }).join("");
}

/* ------------------------------------------------------------------
   EVENTS + START-UP
------------------------------------------------------------------ */
els.planet.addEventListener("change", () => { updateLocations(); setScenario(null); });
els.zone.addEventListener("change", () => {
  if (results[els.zone.value]) setActiveZone(els.zone.value);   // instant: both zones already analysed
  else activeZone = els.zone.value;                            // used by the next search
});
$("compare-scores").addEventListener("click", (e) => {
  const btn = e.target.closest(".zscore__btn");
  if (btn && !btn.disabled) setActiveZone(btn.dataset.zone);
});
els.location.addEventListener("change", () => setScenario(null));

/* rover filter controls */
function syncRover() {
  els.maxSlopeValue.textContent = `${els.maxSlope.value}°`;
  els.roverMode.closest(".rover").classList.toggle("is-off", !els.roverMode.checked);
}
els.maxSlope.addEventListener("input", syncRover);
els.roverMode.addEventListener("change", syncRover);
syncRover();

/* one-click mission scenarios */
function setScenario(btn) {
  activeScenario = btn ? btn.querySelector(".scenario__title").textContent : null;
  els.scenarios.forEach((b) => b.classList.toggle("is-active", b === btn));
}
els.scenarios.forEach((btn) => btn.addEventListener("click", () => {
  els.planet.value = btn.dataset.planet;
  updateLocations();
  els.location.value = btn.dataset.location;
  els.roverMode.checked = btn.dataset.rover === "1";
  els.maxSlope.value = btn.dataset.slope;
  syncRover();
  setScenario(btn);
  els.form.requestSubmit();
  els.brief.scrollIntoView({ behavior: "smooth", block: "start" });
}));

/* copy the brief as plain text (for an email / report) */
els.briefCopy.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(els.brief.dataset.text || "");
    els.briefCopy.textContent = "Copied ✓";
  } catch {
    els.briefCopy.textContent = "Copy failed";
  }
  setTimeout(() => { els.briefCopy.textContent = "Copy brief"; }, 1800);
});
els.form.addEventListener("submit", runSearch);
els.ranking.addEventListener("click", (e) => {
  const tr = e.target.closest("tr[data-rank]");
  if (tr) selectRegion(Number(tr.dataset.rank));
});
els.ranking.addEventListener("keydown", (e) => {
  const tr = e.target.closest("tr[data-rank]");
  if (tr && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); selectRegion(Number(tr.dataset.rank)); }
});

renderUseCases(null);
loadStatus();
loadTargets().catch((err) => showMessage(`Could not load targets: ${err.message}`, true));

/*###########################################################################
# AI MISSION ASSISTANT (floating chat panel)
#   POST /api/assistant with the question, the recent conversation and the
#   current dashboard state, so "site #1" means the region the user sees.
#   The answer is rendered from a tiny, safe markdown subset (bold, lists).
###########################################################################*/
const ai = {
  open: $("assistant-open"), panel: $("assistant"), close: $("assistant-close"), log: $("assistant-log"),
  form: $("assistant-form"), input: $("assistant-input"), send: $("assistant-send"),
  chips: document.querySelectorAll("#assistant-chips .chip"), model: $("assistant-model"),
  history: [], busy: false,
};

function renderMarkdown(text) {
  const inline = (s) => escapeHtml(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
  const out = [];
  let list = [];
  const flush = () => { if (list.length) { out.push(`<ul>${list.map((l) => `<li>${inline(l)}</li>`).join("")}</ul>`); list = []; } };
  for (const raw of String(text).split(/\n/)) {
    const line = raw.trim();
    const m = line.match(/^(?:[-*•]|\d+[.)])\s+(.*)$/);
    if (m) { list.push(m[1]); continue; }
    flush();
    if (line) out.push(`<p>${inline(line)}</p>`);
  }
  flush();
  return out.join("");
}

function addMessage(role, html, meta) {
  const div = document.createElement("div");
  div.className = `msg msg--${role}`;
  div.innerHTML = html + (meta ? `<span class="msg__meta">${escapeHtml(meta)}</span>` : "");
  ai.log.appendChild(div);
  ai.log.scrollTop = ai.log.scrollHeight;
  return div;
}

function dashboardContext() {
  if (!result) return {};
  return { zone: activeZone, planet: result.target.planet, location: result.target.location,
           rover_mode: !!(result.method.rover && result.method.rover.enabled),
           max_slope: result.method.rover ? result.method.rover.max_slope_deg : Number(els.maxSlope.value),
           selected_rank: selected + 1 };
}

async function askAssistant(question) {
  question = question.trim();
  if (!question || ai.busy) return;
  ai.busy = true;
  ai.send.disabled = true;
  addMessage("user", escapeHtml(question));
  const typing = addMessage("bot msg--typing", "Analyzing the results…");
  try {
    const res = await fetch("/api/assistant", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history: ai.history.slice(-10), context: dashboardContext() }),
    });
    const data = await res.json().catch(() => ({}));
    typing.remove();
    if (!res.ok || data.status !== "ok") throw new Error(data.message || `Request failed (${res.status})`);
    const tools = data.tools_used.length ? `tools: ${[...new Set(data.tools_used)].join(", ")}` : "no tool used";
    addMessage("bot", renderMarkdown(data.answer), `${tools} · ${data.model}`);
    ai.history.push({ role: "user", content: question }, { role: "assistant", content: data.answer });
  } catch (err) {
    typing.remove();
    addMessage("bot msg--error", escapeHtml(err.message));
  } finally {
    ai.busy = false;
    ai.send.disabled = false;
    ai.input.focus();
  }
}

function toggleAssistant(open) {
  ai.panel.hidden = !open;
  ai.open.setAttribute("aria-expanded", String(open));
  if (open) ai.input.focus();
}

ai.open.addEventListener("click", () => toggleAssistant(true));
ai.close.addEventListener("click", () => toggleAssistant(false));
ai.form.addEventListener("submit", (e) => { e.preventDefault(); const q = ai.input.value; ai.input.value = ""; askAssistant(q); });
ai.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ai.form.requestSubmit(); }
});
ai.chips.forEach((chip) => chip.addEventListener("click", () => {
  let q = chip.dataset.q;
  if (q === "__ROVER__") {
    const r = result && result.ranking[selected];
    q = r && r.refined
      ? `Can my rover drive at ${coord(r.refined.lat, r.refined.lon, 3)}?`
      : `Can a rover drive in the best ${zn()} region?`;
  }
  askAssistant(q);
}));

fetch("/api/assistant/status").then((r) => r.json()).then((s) => {
  ai.model.textContent = s.configured ? `AI · ${s.provider} ${s.model} · grounded in this project's results`
    : "Unavailable: GROQ_API_KEY not configured on the server";
}).catch(() => { ai.model.textContent = "Unavailable"; });


/*###########################################################################
# VALIDATION AGAINST KNOWN NASA ANALOG SITES (bottom section)
#   Reads result.validation (computed after the analysis, never used in it).
###########################################################################*/
function renderValidation() {
  const v = result && result.validation;
  const body = $("validation-body");
  if (!v || !v.sites.length) {
    body.innerHTML = `<tr><td colspan="6" class="table__empty">No validation data.</td></tr>`;
    return;
  }
  const s = v.summary, t = result.target;
  $("validation-target").textContent = `Checked for ${t.location} (${t.planet === "mars" ? "Mars" : "Moon"}).`;

  const agreeTxt = s.agreeing
    ? `<strong>${s.agreeing} of ${s.evaluated}</strong> reference analog sites rank above average (${s.agreeing_sites.map(escapeHtml).join(", ")})`
    : `<strong>None of the ${s.evaluated}</strong> reference analog sites ranks above average`;
  let summary = `${agreeTxt} for ${escapeHtml(t.location)}; mean percentile <strong>${fmt(s.mean_percentile, 0)} %</strong> ` +
    `(a random pick averages 50 %).`;
  const strong = v.sites.filter((r) => r.evaluated && r.percentile >= 80);
  if (!s.is_mars_target) {
    summary += " <em>These are Mars analog sites: for a Moon target they are not expected to rank high.</em>";
  } else if (strong.length) {
    summary += " Without being tuned on it, our system ranks " + strong.map((r) =>
      `<strong>${escapeHtml(r.name)}</strong> in the top ${Math.max(1, Math.round(100 - r.percentile))} %`).join(" and ") +
      ` of ${zn()} cells — a place already studied as a Mars analog (${strong.map((r) => escapeHtml(r.program)).join("; ")}).`;
  } else if (s.agreeing) {
    summary += " Agreement is partial: see which kind of terrain each site represents below.";
  }
  $("validation-summary").innerHTML = summary;

  body.innerHTML = v.sites.map((r) => {
    const where = r.inside_study_area ? "" : `<small>just outside the study area · closest cell ${fmt(r.cell && r.cell.distance_km, 0)} km away</small>`;
    if (!r.evaluated) {
      return `<tr><td><strong>${escapeHtml(r.name)}</strong><small>${escapeHtml(r.program)}</small></td>
        <td>${escapeHtml(r.studied_for)}</td><td colspan="4">${escapeHtml(r.note || "Not evaluated")}</td></tr>`;
    }
    const top = r.nearest_top10 && r.nearest_top10.rank
      ? `#${r.nearest_top10.rank} at ${fmt(r.nearest_top10.distance_km, 0)} km` : "—";
    return `<tr>
      <td><strong>${escapeHtml(r.name)}</strong><small>${escapeHtml(r.program)}</small>${where}</td>
      <td>${escapeHtml(r.studied_for)}</td>
      <td>${fmt(r.score, 1)}</td>
      <td><div class="pct"><span class="pct__bar"><span style="width:${r.percentile}%"></span></span>${fmt(r.percentile, 0)} %</div></td>
      <td>${top}</td>
      <td><span class="verdict verdict--${r.verdict}">${escapeHtml(r.verdict_label)}</span></td>
    </tr>`;
  }).join("");

  $("validation-sources").innerHTML = "Sources: " + v.sites.flatMap((r) => r.sources.map((x) =>
    `<a href="${escapeHtml(x.url)}" target="_blank" rel="noopener">${escapeHtml(x.label)}</a>`)).join(" · ");
}


/*###########################################################################
# MACHINE LEARNING SECTION (GET /api/ml)
#   A: PCA scatter of Earth / Mars / Moon cells (Chart.js, interactive)
#   B: K-means terrain types (cards + "show on map" overlay)
#   Clicking an Atacama point selects that cell in the radar and on the map.
###########################################################################*/
const ml = { data: null, chart: null, colorBy: "body", mapType: null, typeAt: new Map() };
const keyOf = (lat, lon) => `${Number(lat).toFixed(3)},${Number(lon).toFixed(3)}`;
function mlTypeOf(c) { return ml.typeAt.get(keyOf(c.lat, c.lon)); }

async function loadML() {
  if (!result) return;
  const r = result.method.rover || {};
  const q = new URLSearchParams({ planet: result.target.planet, location: result.target.location,
    rover_mode: String(!!r.enabled), max_slope: String(r.max_slope_deg || 15), zone: activeZone });
  try {
    const res = await fetch(`/api/ml?${q}`);
    const data = await res.json();
    if (!res.ok || data.status !== "ok") throw new Error(data.message || "ML unavailable");
    ml.data = data;
    ml.mapType = null;
    ml.typeAt = new Map(data.clustering.earth_types.map(([lat, lon, t]) => [keyOf(lat, lon), t]));
    renderML();
  } catch (err) {
    $("pca-empty").hidden = false;
    $("pca-empty").textContent = `Machine-learning models unavailable: ${err.message}`;
  }
}

function renderML() {
  const d = ml.data, t = result.target, c = d.clustering, a = d.agreement, p = d.pca;
  const typeName = (i) => (i === null || i === undefined ? "—" : c.types[i].name);

  // headline numbers
  const ratio = p.centroid_distance.earth_moon / p.centroid_distance.earth_mars;
  $("ml-stat-ratio").textContent = `${ratio.toFixed(1)}×`;
  $("ml-stat-ratio-detail").textContent =
    `centroid distance: Mars ${p.centroid_distance.earth_mars.toFixed(2)} vs Moon ${p.centroid_distance.earth_moon.toFixed(2)} (6 shared features)`;
  $("ml-stat-agree").textContent = `${a.top10_same_type}/${a.top10_count}`;
  $("ml-stat-agree-label").innerHTML = `top-10 regions share ${escapeHtml(t.location)}'s terrain type<br><small>ML clustering vs similarity ranking</small>`;
  $("ml-stat-var").textContent = `${Math.round(p.explained_variance_pct[0] + p.explained_variance_pct[1])} %`;

  // terrain type cards
  const sil = c.silhouettes[c.k];
  $("types-hint").textContent = `K-means found ${c.k} terrain types (best silhouette ${sil} among k = ` +
    `${Object.keys(c.silhouettes).join(", ")}) from slope, roughness and relief. Bars: share of each body's cells.`;
  const bodies = [["zone", zn(), "#8fb3ff"], ["mars", "Mars", "#ff7a45"], ["moon", "Moon", "#c8cdd8"]];
  $("types-list").innerHTML = c.types.map((ty) => `
    <li class="type${ty.id === c.target_type ? " is-target" : ""}">
      <div class="type__head">
        <span class="type__name"><span class="type__dot" style="background:${ty.color}"></span>${escapeHtml(ty.name)}</span>
        ${ty.id === c.target_type ? `<span class="type__badge">${escapeHtml(t.location)}'s type · ${fmt(c.target_type_share_pct, 0)} % of target area</span>` : ""}
      </div>
      <div class="type__bars">${bodies.map(([b, label, col]) => `
        <div class="type__bar"><span>${label}</span><span class="type__track"><span style="width:${ty.share_pct[b] ?? ty.share_pct.earth}%;background:${col}"></span></span><span>${fmt(ty.share_pct[b] ?? ty.share_pct.earth, 1)} %</span></div>`).join("")}
      </div>
      <button type="button" class="type__show${ml.mapType === ty.id ? " is-on" : ""}" data-type="${ty.id}">Show on the ${escapeHtml(zn())} map</button>
    </li>`).join("");

  // agreement sentence (honest in both directions)
  const tt = typeName(c.target_type);
  let txt;
  if (a.top10_same_type >= 6) {
    txt = `<strong>${a.top10_same_type} of ${a.top10_count}</strong> top-ranked regions belong to ${escapeHtml(t.location)}'s terrain type ` +
      `(${escapeHtml(tt)}), and cells of that type score higher on average (${fmt(a.mean_score_same_type, 1)} vs ` +
      `${fmt(a.mean_score_other_types, 1)}). <strong>Two independent methods agree.</strong>`;
  } else {
    txt = `Only <strong>${a.top10_same_type} of ${a.top10_count}</strong> top-ranked regions belong to ${escapeHtml(t.location)}'s ` +
      `dominant terrain type (${escapeHtml(tt)}, ${fmt(c.target_type_share_pct, 0)} % of the target area). ${escapeHtml(zn())} has ` +
      `${fmt(c.atacama_same_type_pct, 1)} % of its cells of that type, so the score favours the closest other terrain — ` +
      `a real limit of ${escapeHtml(zn())} as an analog for this target.`;
  }
  $("ml-agree-text").innerHTML = txt;
  $("ml-method").textContent = d.method;
  $("types-reset").hidden = ml.mapType === null;

  $("pca-axes").textContent = `Axis 1 (${p.explained_variance_pct[0]} %): ${p.axis_labels[0]} · ` +
    `Axis 2 (${p.explained_variance_pct[1]} %): ${p.axis_labels[1]}. Click a ${zn()} point to inspect it.`;
  drawScatter();
}

function scatterDatasets() {
  const d = ml.data, types = d.clustering.types;
  const bg = (pts, body) => pts.map((q) => ({ x: q[0], y: q[1], type: q[2], body }));
  const earthPts = d.pca.earth.map((q) => ({ x: q[0], y: q[1], type: q[2], lat: q[3], lon: q[4], score: q[5], rank: q[6], body: "earth" }));
  const top = earthPts.filter((q) => q.rank);
  const target = d.pca.target.map((q) => ({ x: q[0], y: q[1], body: "target" }));
  const overlays = [
    { label: `Top-10 ${zn()} regions`, data: top, pointRadius: 6, pointHoverRadius: 8, backgroundColor: "#8fb3ff",
      borderColor: "#ffffff", borderWidth: 2, order: 1 },
    { label: `${result.target.location} (target area)`, data: target, pointStyle: "star", pointRadius: 9, pointHoverRadius: 11,
      backgroundColor: "#ffd166", borderColor: "#ff7a45", borderWidth: 1.5, order: 0 },
  ];
  if (ml.colorBy === "type") {
    const all = [...bg(d.pca.background.mars, "mars"), ...bg(d.pca.background.moon, "moon"), ...earthPts];
    return [...types.map((ty) => ({ label: ty.name, data: all.filter((q) => q.type === ty.id), pointRadius: 2.2,
      backgroundColor: ty.color + "99", borderWidth: 0, order: 5 })), ...overlays];
  }
  return [
    { label: "Mars", data: bg(d.pca.background.mars, "mars"), pointRadius: 2, backgroundColor: "rgba(255,122,69,.35)", borderWidth: 0, order: 6 },
    { label: "Moon", data: bg(d.pca.background.moon, "moon"), pointRadius: 2, backgroundColor: "rgba(200,205,220,.35)", borderWidth: 0, order: 6 },
    { label: `${zn()} (Earth)`, data: earthPts, pointRadius: 2.6, backgroundColor: "rgba(143,179,255,.85)", borderWidth: 0, order: 3 },
    ...overlays,
  ];
}

function nearestEarthPoint(evt, maxPx = 12) {
  if (!ml.chart) return null;
  let best = null, bestD = maxPx;
  ml.chart.data.datasets.forEach((ds, i) => {
    const meta = ml.chart.getDatasetMeta(i);
    if (meta.hidden) return;
    ds.data.forEach((q, j) => {
      if (q.body !== "earth") return;
      const el = meta.data[j];
      const d = Math.hypot(el.x - evt.x, el.y - evt.y);
      if (d < bestD) { bestD = d; best = q; }
    });
  });
  return best;
}

function drawScatter() {
  if (!window.Chart || !ml.data) return;
  $("pca-empty").hidden = true;
  const types = ml.data.clustering.types, p = ml.data.pca;
  const tooltip = (ctx) => {
    const q = ctx.raw, ty = q.type !== undefined && q.type !== null ? ` · ${types[q.type].name}` : "";
    if (q.body === "earth") {
      return `${zn()} ${coord(q.lat, q.lon, 2)} · score ${fmt(q.score, 1)}${q.rank ? ` · rank #${q.rank}` : ""}${ty}`;
    }
    if (q.body === "target") return `${result.target.location} target cell`;
    return `${q.body === "mars" ? "Mars" : "Moon"} cell${ty}`;
  };
  const axis = (i) => ({ title: { display: true, text: `Axis ${i + 1} (${p.explained_variance_pct[i]} %): ${p.axis_labels[i]}`, color: "#9aa6c2" },
    grid: { color: "rgba(255,255,255,.06)" }, ticks: { color: "#9aa6c2" } });
  const config = {
    type: "scatter",
    data: { datasets: scatterDatasets() },
    options: {
      responsive: true, maintainAspectRatio: false, animation: { duration: 700 },
      scales: { x: axis(0), y: axis(1) },
      plugins: {
        legend: { position: "bottom", labels: { color: "#e8ecf5", usePointStyle: true, boxWidth: 8 } },
        tooltip: { callbacks: { label: tooltip } },
      },
      // Dense clouds: Mars/Moon points can sit on top of Atacama points, so find the nearest
      // ATACAMA point to the cursor ourselves (within 12 px) instead of Chart.js's single nearest point.
      onClick: (evt) => {
        const hit = nearestEarthPoint(evt);
        if (!hit) return;
        const cell = findCell(hit.lat, hit.lon);
        if (cell) {
          selectCell(cell);
          $("radar-canvas").scrollIntoView({ behavior: "smooth", block: "center" });
        }
      },
      onHover: (evt) => {
        evt.native.target.style.cursor = nearestEarthPoint(evt) ? "pointer" : "default";
      },
    },
  };
  if (ml.chart) ml.chart.destroy();
  ml.chart = new Chart($("pca-canvas"), config);
}

/* colour toggle + "show type on map" */
document.querySelectorAll(".seg__btn").forEach((btn) => btn.addEventListener("click", () => {
  ml.colorBy = btn.dataset.color;
  document.querySelectorAll(".seg__btn").forEach((b) => b.classList.toggle("is-active", b === btn));
  drawScatter();
}));
$("types-list").addEventListener("click", (e) => {
  const btn = e.target.closest(".type__show");
  if (!btn || !ml.data) return;
  const id = Number(btn.dataset.type);
  ml.mapType = ml.mapType === id ? null : id;
  renderML();
  drawEarthMap(false);
  drawEarthMarkers(null);
  if (ml.mapType !== null) $("earth-map").scrollIntoView({ behavior: "smooth", block: "center" });
});
$("types-reset").addEventListener("click", () => {
  ml.mapType = null;
  renderML();
  drawEarthMap(false);
  drawEarthMarkers(null);
});
