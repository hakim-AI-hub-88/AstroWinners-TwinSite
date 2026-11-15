/* TwinSite Data Hub (/data) - data lane.
   Renders the catalogue, explorer, cleaning algorithms, API examples and live sources
   from the /api/data JSON API. No framework, no external dependency. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (v) => (typeof v === "number" && Number.isFinite(v) ? v : null);
  const int = (v) => (num(v) === null ? "—" : v.toLocaleString("en-US"));
  const val = (v) => (num(v) === null ? "—" : Math.abs(v) >= 1000 ? v.toFixed(0) : String(+v.toPrecision(5)));
  const bytes = (b) => (num(b) === null ? "—" : b >= 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${(b / 1e3).toFixed(0)} kB`);
  const BODY = { earth: "Earth", mars: "Mars", moon: "Moon" };
  const PAGE = 50;
  const origin = window.location.origin;

  async function api(url, opts) {
    const res = await fetch(url, opts);
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.message || `Request failed (${res.status})`);
    return data;
  }

  const state = { datasets: [], profiles: [], meta: null, offset: 0, total: 0, bodyFilter: "" };

  /* ---------------- CATALOGUE ---------------- */
  function renderCatalog() {
    const list = state.datasets.filter((d) => !state.bodyFilter || d.body === state.bodyFilter);
    $("catalog-cards").innerHTML = list.map((d) => `
      <article class="dh-card${d.available ? "" : " is-off"}">
        <div class="dh-card__top">
          <span class="tag">${esc(BODY[d.body] || d.body)}</span>
          <span class="dh-badge ${d.available ? "ok" : "off"}">${d.available ? "available" : "unavailable"}</span>
        </div>
        <h3>${esc(d.title)}</h3>
        <p class="dh-card__id"><code>${esc(d.id)}</code></p>
        <dl class="dh-dl">
          <div><dt>Zone</dt><dd>${esc(d.zone)}</dd></div>
          <div><dt>Stage</dt><dd>${esc(d.stage.replace(/_/g, " "))}</dd></div>
          <div><dt>Rows</dt><dd>${int(d.rows)}</dd></div>
          <div><dt>Columns</dt><dd>${d.columns.length || "—"}</dd></div>
          <div><dt>Size</dt><dd>${bytes(d.bytes)}</dd></div>
          <div><dt>Grid</dt><dd>${esc(d.resolution || "—")}</dd></div>
        </dl>
        ${d.available
          ? `<button type="button" class="btn dh-card__btn" data-explore="${esc(d.id)}">Explore</button>`
          : `<p class="dh-card__reason">${esc(d.reason)}</p>`}
      </article>`).join("");
  }

  async function loadCatalog() {
    try {
      const j = await api("/api/data/datasets");
      state.datasets = j.datasets;
      const avail = j.datasets.filter((d) => d.available);
      $("st-datasets").textContent = j.count;
      $("st-available").textContent = j.available;
      $("st-rows").textContent = avail.reduce((s, d) => s + (d.rows || 0), 0).toLocaleString("en-US");
      $("catalog-note").textContent = `${j.available} of ${j.count} datasets are on this server. ` +
        "Unavailable ones say why (not bundled here, or still downloading).";
      renderCatalog();
      $("ex-dataset").innerHTML = j.datasets.map((d) =>
        `<option value="${esc(d.id)}"${d.available ? "" : " disabled"}>${esc(d.title)}${d.available ? "" : " (unavailable)"}</option>`).join("");
      const first = avail.find((d) => d.id === "earth.harmonized") || avail[0];
      if (first) { $("ex-dataset").value = first.id; await selectDataset(first.id); }
      renderApi(first ? first.id : "earth.harmonized");
    } catch (err) {
      $("catalog-note").textContent = `Catalogue unavailable: ${err.message}`;
    }
  }

  document.querySelector(".dh-filter").addEventListener("click", (e) => {
    const b = e.target.closest(".dh-chip");
    if (!b) return;
    document.querySelectorAll(".dh-chip").forEach((x) => x.classList.toggle("is-on", x === b));
    state.bodyFilter = b.dataset.body;
    renderCatalog();
  });
  $("catalog-cards").addEventListener("click", async (e) => {
    const b = e.target.closest("[data-explore]");
    if (!b) return;
    $("ex-dataset").value = b.dataset.explore;
    await selectDataset(b.dataset.explore);
    $("explorer").scrollIntoView({ behavior: "smooth" });
    runQuery(0);
  });

  /* ---------------- EXPLORER ---------------- */
  async function selectDataset(id) {
    $("ex-msg").textContent = "Loading metadata…";
    try {
      state.meta = await api(`/api/data/datasets/${encodeURIComponent(id)}`);
      $("ex-msg").textContent = "";
    } catch (err) {
      state.meta = null;
      $("ex-msg").textContent = err.message;
      return;
    }
    const cols = state.meta.columns.map((c) => c.name).filter((c) => c !== "latitude" && c !== "longitude");
    const empty = new Set(state.meta.columns.filter((c) => c.valid === 0).map((c) => c.name));
    $("ex-columns").innerHTML = cols.map((c) =>
      `<label class="dh-check"><input type="checkbox" value="${esc(c)}"${empty.has(c) ? "" : " checked"}> ${esc(c.replace(/_/g, " "))}</label>`).join("");
    renderStats();
    renderFlags();
    renderProvenance();
    updateLinks();
    renderApi(id);
  }

  function query(extra = {}) {
    const p = new URLSearchParams();
    const cols = [...document.querySelectorAll("#ex-columns input:checked")].map((i) => i.value);
    const all = document.querySelectorAll("#ex-columns input").length;
    if (cols.length && cols.length < all) p.set("columns", cols.join(","));
    const bbox = $("ex-bbox").value.replace(/\s+/g, "");
    if (bbox) p.set("bbox", bbox);
    p.set("cleaning", $("ex-cleaning").value || "standard");
    Object.entries(extra).forEach(([k, v]) => p.set(k, v));
    return p.toString();
  }

  function updateLinks() {
    const id = $("ex-dataset").value;
    const base = `/api/data/datasets/${encodeURIComponent(id)}`;
    $("dl-csv").href = `${base}/records?${query({ format: "csv" })}`;
    $("dl-json").href = `${base}/records?${query({ format: "json", limit: 5000, offset: 0, download: 1 })}`;
    $("dl-file").href = `${base}/file`;
  }

  async function runQuery(offset) {
    const id = $("ex-dataset").value;
    if (!id) return;
    $("ex-msg").textContent = "Loading records…";
    updateLinks();
    try {
      const j = await api(`/api/data/datasets/${encodeURIComponent(id)}/records?${query({ limit: PAGE, offset })}`);
      state.offset = j.offset;
      state.total = j.total;
      renderTable(j);
      renderCleaning(j.cleaning.report);
      $("ex-results").hidden = false;
      $("ex-msg").textContent = "";
    } catch (err) {
      $("ex-msg").textContent = err.message;
    }
  }

  function renderTable(j) {
    const head = `<thead><tr>${j.columns.map((c) => `<th scope="col">${esc(c.replace(/_/g, " "))}</th>`).join("")}</tr></thead>`;
    const body = j.rows.length
      ? j.rows.map((r) => `<tr>${j.columns.map((c) => `<td class="mono">${c === "quality_flags" ? esc(r[c]) : val(r[c])}</td>`).join("")}</tr>`).join("")
      : `<tr><td colspan="${j.columns.length}">No rows match this selection.</td></tr>`;
    $("ex-table").innerHTML = head + `<tbody>${body}</tbody>`;
    const end = Math.min(j.offset + j.rows.length, j.total);
    $("ex-total").textContent = `${int(j.total)} rows after cleaning`;
    $("pg-info").textContent = j.total ? `${int(j.offset + 1)}–${int(end)} of ${int(j.total)}` : "0 rows";
    $("pg-prev").disabled = j.offset <= 0;
    $("pg-next").disabled = end >= j.total;
  }

  function renderCleaning(rep) {
    const pct = rep.rows_in ? Math.round((100 * rep.rows_out) / rep.rows_in) : 0;
    $("ex-ba").innerHTML = `
      <div class="dh-ba"><span class="dh-ba__n">${int(rep.rows_in)}</span><span class="dh-hint">rows in selection</span></div>
      <span class="dh-ba__arrow" aria-hidden="true">→</span>
      <div class="dh-ba"><span class="dh-ba__n">${int(rep.rows_out)}</span><span class="dh-hint">after ${esc(rep.name)} (${pct} %)</span></div>
      <div class="dh-ba"><span class="dh-ba__n">${int(rep.values_masked)}</span><span class="dh-hint">values masked</span></div>
      <div class="dh-ba"><span class="dh-ba__n">${int(rep.rows_complete)}</span><span class="dh-hint">complete rows</span></div>
      <div class="dh-bar" role="img" aria-label="${pct} % of rows kept"><span style="width:${pct}%"></span></div>`;
    $("ex-steps").innerHTML = rep.steps.length
      ? rep.steps.map((s) => `<li><strong>${esc(s.label)}</strong> — ${int(s.removed)} rows removed, ${int(s.masked)} values masked</li>`).join("")
      : "<li>No cleaning step (values exactly as published).</li>";
  }

  function renderFlags() {
    const flags = (state.meta && state.meta.quality_flags) || [];
    $("ex-flags").innerHTML = flags.map((f) => `
      <div class="dh-flag" title="${esc(f.meaning)}">
        <span class="dh-flag__name">${esc(f.name)} <code>${f.bit}</code></span>
        <span class="dh-flag__bar"><span style="width:${Math.min(100, f.pct || 0)}%"></span></span>
        <span class="dh-flag__n">${int(f.count)} · ${num(f.pct) === null ? "—" : f.pct} %</span>
      </div>`).join("") || "<p class='dh-hint'>No quality flag column.</p>";
  }

  function renderStats() {
    const cols = (state.meta && state.meta.columns) || [];
    $("ex-stats").innerHTML = `<thead><tr><th>Column</th><th>Units</th><th>Min</th><th>Mean</th><th>Median</th><th>Max</th><th>Missing</th></tr></thead><tbody>` +
      cols.filter((c) => c.name !== "quality_flags").map((c) => `<tr><td>${esc(c.name.replace(/_/g, " "))}</td><td>${esc(c.units)}</td>
        <td class="mono">${val(c.min)}</td><td class="mono">${val(c.mean)}</td><td class="mono">${val(c.median)}</td>
        <td class="mono">${val(c.max)}</td><td class="mono">${num(c.null_pct) === null ? "—" : c.null_pct + " %"}</td></tr>`).join("") + "</tbody>";
  }

  function renderProvenance() {
    const p = (state.meta && state.meta.provenance) || {};
    const src = Object.entries(p.feature_sources || {}).map(([f, s]) => `<li><strong>${esc(f.replace(/_/g, " "))}</strong>: ${esc(s)}</li>`).join("");
    const steps = (p.processing_steps || []).map((s) => `<li>${esc(s)}</li>`).join("");
    const notes = (p.notes || []).map((s) => `<li>${esc(s)}</li>`).join("");
    const norm = state.meta && state.meta.normalization;
    $("ex-prov").innerHTML = (src ? `<h4>Feature sources</h4><ul>${src}</ul>` : "") +
      (steps ? `<h4>Processing steps</h4><ol>${steps}</ol>` : "") +
      (notes ? `<h4>Notes</h4><ul>${notes}</ul>` : "") +
      (norm ? `<h4>Normalization</h4><p>${esc(norm.method)}</p>` : "") +
      `<p class="dh-hint">Full report: <code>${esc(p.pipeline_report || "")}</code> · License: ${esc(state.meta ? state.meta.license : "")}</p>`;
  }

  $("ex-dataset").addEventListener("change", async (e) => { await selectDataset(e.target.value); runQuery(0); });
  $("ex-form").addEventListener("submit", (e) => { e.preventDefault(); runQuery(0); });
  $("ex-form").addEventListener("change", (e) => { if (e.target.id !== "ex-dataset") updateLinks(); });
  $("ex-bbox").addEventListener("input", updateLinks);
  $("pg-prev").addEventListener("click", () => runQuery(Math.max(0, state.offset - PAGE)));
  $("pg-next").addEventListener("click", () => runQuery(state.offset + PAGE));

  /* ---------------- CLEANING ALGORITHMS ---------------- */
  async function loadCleaning() {
    try {
      const j = await api("/api/data/cleaning");
      state.profiles = j.profiles;
      $("ex-cleaning").innerHTML = j.profiles.map((p) =>
        `<option value="${esc(p.id)}"${p.id === j.default ? " selected" : ""}>${esc(p.name)}${p.id === j.default ? " (default)" : ""}</option>`).join("");
      $("cleaning-profiles").innerHTML = j.profiles.map((p) => `
        <article class="panel dh-profile" id="profile-${esc(p.id)}">
          <div class="dh-card__top"><h3>${esc(p.name)}</h3><code>${esc(p.id)}</code>${p.id === j.default ? '<span class="tag">default</span>' : ""}</div>
          <p class="dh-profile__sum">${esc(p.summary)}</p>
          <p class="dh-hint">${esc(p.description)}</p>
          ${p.steps.length ? `<ol class="dh-steps">${p.steps.map((s) => `<li><strong>${esc(s.label)}</strong><br><span class="dh-hint">${esc(s.description)}</span></li>`).join("")}</ol>`
            : "<p class='dh-hint'>No step: values are passed through untouched.</p>"}
        </article>`).join("");
      $("cleaning-flags").innerHTML = `<thead><tr><th>Flag</th><th>Bit</th><th>Meaning</th><th>Strict / Robust</th></tr></thead><tbody>` +
        j.flags.map((f) => `<tr><td><code>${esc(f.name)}</code></td><td class="mono">${f.bit}</td><td>${esc(f.meaning)}</td><td>${esc(f.strict_action)}</td></tr>`).join("") + "</tbody>";
    } catch (err) {
      $("cleaning-profiles").innerHTML = `<p class="dh-note">Cleaning profiles unavailable: ${esc(err.message)}</p>`;
    }
  }

  /* ---------------- API EXAMPLES ---------------- */
  function renderApi(id) {
    const ex = [
      ["GET", "/api/data/datasets", "Catalogue of every dataset (availability, rows, columns, size)."],
      ["GET", `/api/data/datasets/${id}`, "Metadata: column statistics, quality flags, normalization, provenance."],
      ["GET", `/api/data/datasets/${id}/records?limit=100&offset=0&cleaning=strict&bbox=-69,-24,-68,-23&columns=slope,albedo`, "Paginated JSON records (limit ≤ 5,000)."],
      ["GET", `/api/data/datasets/${id}/records?format=csv&cleaning=robust`, "Streamed CSV download (≤ 200,000 rows)."],
      ["GET", `/api/data/datasets/${id}/file`, "Original bundled file, byte for byte."],
      ["GET", "/api/data/cleaning", "Cleaning profiles and their steps."],
      ["POST", "/api/data/clean", "Cleaning report only (rows removed per step, per feature).", { dataset: id, profile: "robust" }],
      ["GET", "/api/data/sources", "Bundled products + live platform connectors."],
      ["POST", "/api/similarity", "Run a mission with options.", { planet: "mars", location: "Jezero Crater", cleaning: "strict", data_mode: "bundled" }],
    ];
    $("api-list").innerHTML = ex.map(([m, path, desc, body], i) => {
      const curl = body
        ? `curl -X POST ${origin}${path} -H 'Content-Type: application/json' -d '${JSON.stringify(body)}'`
        : `curl '${origin}${path}'${path.includes("format=csv") || path.endsWith("/file") ? " -OJ" : ""}`;
      const py = body
        ? `import requests\nr = requests.post("${origin}${path}", json=${JSON.stringify(body)})\nprint(r.json())`
        : path.includes("format=csv")
          ? `import pandas as pd\ndf = pd.read_csv("${origin}${path}")`
          : path.endsWith("/file") ? `import pandas as pd\ndf = pd.read_csv("${origin}${path}")` : `import requests\nprint(requests.get("${origin}${path}").json())`;
      return `<details class="panel dh-endpoint"${i < 3 ? " open" : ""}>
        <summary><span class="dh-method dh-method--${m.toLowerCase()}">${m}</span><code>${esc(path.split("?")[0])}</code><span class="dh-hint">${esc(desc)}</span></summary>
        <div class="dh-code"><div class="dh-code__head">curl<button type="button" class="dh-copy" data-copy="c${i}">Copy</button></div><pre id="c${i}">${esc(curl)}</pre></div>
        <div class="dh-code"><div class="dh-code__head">Python<button type="button" class="dh-copy" data-copy="p${i}">Copy</button></div><pre id="p${i}">${esc(py)}</pre></div>
      </details>`;
    }).join("");
  }
  $("api-list").addEventListener("click", async (e) => {
    const b = e.target.closest(".dh-copy");
    if (!b) return;
    try {
      await navigator.clipboard.writeText($(b.dataset.copy).textContent);
      b.textContent = "Copied";
    } catch { b.textContent = "Select & copy"; }
    setTimeout(() => { b.textContent = "Copy"; }, 1500);
  });

  /* ---------------- LIVE SOURCES ---------------- */
  async function loadSources() {
    try {
      const j = await api("/api/data/sources");
      const live = j.sources.filter((s) => s.kind === "live");
      $("st-live").textContent = j.platform.status === "ok" ? live.length : "offline";
      $("sources-status").textContent = j.platform.status === "ok"
        ? `${live.length} connectors reported by the TwinSite platform API. New connectors appear here as soon as the platform registers them.`
        : `Live sources unavailable: ${j.platform.reason}`;
      $("sources-live").innerHTML = live.length
        ? `<thead><tr><th>Source</th><th>Provider</th><th>Bodies</th><th>Domains</th><th>Status</th><th>Access</th></tr></thead><tbody>` +
          live.map((s) => `<tr><td>${s.documentation_url ? `<a href="${esc(s.documentation_url)}" rel="noopener" target="_blank">${esc(s.name)}</a>` : esc(s.name)}
            ${s.notes ? `<br><span class="dh-hint">${esc(s.notes)}</span>` : ""}</td><td>${esc(s.provider)}</td>
            <td>${esc((s.bodies || []).join(", "))}</td><td>${esc((s.domains || []).join(", ").replace(/_/g, " "))}</td>
            <td><span class="dh-badge ${/live|cached/.test(s.status) ? "ok" : "muted"}">${esc((s.status || "").replace(/_/g, " "))}</span></td>
            <td>${esc(s.access)}</td></tr>`).join("") + "</tbody>"
        : "";
      $("sources-bundled").innerHTML = `<thead><tr><th>Body</th><th>Product</th><th>Provider</th><th>Resolution</th><th>Purpose</th><th>Status</th></tr></thead><tbody>` +
        j.bundled_products.map((p) => `<tr><td>${esc(p.body)}</td><td>${esc(p.dataset)}</td><td>${esc(p.provider)}</td>
          <td>${esc(p.resolution)}</td><td>${esc(p.purpose)}</td><td><span class="dh-badge ${p.status === "available" ? "ok" : "muted"}">${esc(p.status)}</span></td></tr>`).join("") + "</tbody>";
    } catch (err) {
      $("sources-status").textContent = `Sources unavailable: ${err.message}`;
      $("st-live").textContent = "—";
    }
  }

  loadCleaning().then(loadCatalog).then(() => runQuery(0));
  loadSources();
})();
