/* Agentic Auto Mode page (templates/auto.html).
   Launches POST /api/auto/missions, follows GET /api/auto/missions/<id>, renders the
   timeline, the A01-A13 agent roster, results and recent missions. Every value shown
   comes from the API; empty states say what is missing and why. */
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const TARGETS = window.TWINSITE_TARGETS || {};
  const ROLES = [
    ["A01", "Source Curator", "deterministic", "Inventories evidence sources, assets and gateway context per domain."],
    ["A02", "Visual Interpreter", "AI vision", "Qualitative reading of agency imagery (never a measurement)."],
    ["A03", "Cleaning Planner", "deterministic", "Allowlisted cleaning transformations recorded by the engine."],
    ["A04", "Quality Reviewer", "deterministic", "Hard QA gates: qa_status, flags, coverage, spatial support."],
    ["A05", "Scenario Estimator", "AI", "Proposes labelled alternative weight scenarios; engine re-scores them."],
    ["A06", "Domain Analyst", "AI", "Evidence-linked findings per scientific domain, plus data gaps."],
    ["A07", "Synthesis Analyst", "AI", "Cross-domain synthesis with claims tied to evidence IDs."],
    ["A08", "Process Auditor", "deterministic", "Asserts the agent trace is well-formed and the result untouched."],
    ["A09", "Evidence Reviewer", "AI", "Independent provider reviews each synthesis claim against evidence."],
    ["A10", "Portfolio Reviewer", "deterministic", "Rechecks portfolio constraints and eligibility."],
    ["A11", "Release Judge", "deterministic", "Applies the deterministic release gate; AI cannot release."],
    ["A12", "Targeted Rechecker", "AI", "Re-examines only claims the reviewer could not support."],
    ["A13", "Report Writer", "AI narrative", "Evidence-cited narrative appended to the deterministic report."],
  ];
  const STATE_LABEL = { pending: "pending", running: "running", completed: "done", skipped: "skipped", failed: "failed" };
  let current = null, timer = null, following = false;

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (v, d = 1) => (v === null || v === undefined || Number.isNaN(Number(v)) ? "—" : Number(v).toFixed(d));
  const coord = (lat, lon) => `${num(Math.abs(lat), 3)}°${lat >= 0 ? "N" : "S"}, ${num(Math.abs(lon), 3)}°${lon >= 0 ? "E" : "W"}`;
  const dur = (s) => (s === null || s === undefined ? "" : s < 60 ? `${s.toFixed(1)} s` : `${Math.floor(s / 60)} min ${Math.round(s % 60)} s`);
  async function json(url, opts) {
    const res = await fetch(url, opts);
    const body = await res.json().catch(() => ({}));
    return { ok: res.ok, status: res.status, body };
  }

  /* ---------------------------------------------------------------- form */
  const planet = () => document.querySelector('input[name="planet"]:checked').value;
  function fillTargets() {
    const sel = $("f-target");
    const presets = TARGETS[planet()] || {};
    sel.innerHTML = Object.keys(presets).map((n) => `<option value="${esc(n)}">${esc(n)}</option>`).join("")
      + '<option value="__custom__">Custom point (lat / lon)…</option>';
    onTarget();
  }
  function onTarget() {
    const v = $("f-target").value, custom = v === "__custom__";
    $("custom-fields").hidden = !custom;
    const t = (TARGETS[planet()] || {})[v];
    $("target-note").textContent = custom
      ? "Any point between 88° S and 88° N. The platform characterizes it with live NASA data; the bundled analysis needs dataset coverage."
      : t ? `${t.note} · ${coord(t.lat, t.lon)}` : "";
  }
  function payload() {
    const v = $("f-target").value;
    const target = v === "__custom__"
      ? { planet: planet(), lat: parseFloat($("f-lat").value), lon: parseFloat($("f-lon").value),
          name: $("f-name").value.trim() || undefined, radius_km: parseInt($("f-radius").value, 10) }
      : { planet: planet(), location: v };
    return {
      target, objective: $("f-objective").value, slope_limit: parseFloat($("f-slope").value),
      zones: [...document.querySelectorAll('input[name="zones"]:checked')].map((x) => x.value),
      data_mode: document.querySelector('input[name="data_mode"]:checked').value,
      cleaning: $("f-cleaning").value, ai: $("f-ai").checked,
    };
  }
  function formError(msg) { $("form-error").textContent = msg || ""; $("form-error").hidden = !msg; }
  function localCheck(p) {
    if (p.target.location === undefined) {
      if (!Number.isFinite(p.target.lat) || p.target.lat < -88 || p.target.lat > 88) return "Latitude must be between -88 and 88.";
      if (!Number.isFinite(p.target.lon) || p.target.lon < -180 || p.target.lon > 180) return "Longitude must be between -180 and 180.";
    }
    if (!p.zones.length) return "Select at least one Earth zone.";
    if (!Number.isFinite(p.slope_limit) || p.slope_limit < 5 || p.slope_limit > 30) return "Slope limit must be between 5 and 30°.";
    return null;
  }

  async function launch(e) {
    e.preventDefault();
    const p = payload();
    const bad = localCheck(p);
    if (bad) return formError(bad);
    formError(null);
    $("btn-launch").disabled = true;
    $("btn-launch").textContent = "Launching…";
    try {
      const r = await json("/api/auto/missions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(p) });
      if (!r.ok) throw new Error(r.body.message || `Request failed (${r.status})`);
      follow(r.body.mission_id);
      loadRecent();
    } catch (err) {
      formError(err.message);
    } finally {
      $("btn-launch").disabled = false;
      $("btn-launch").textContent = "Launch autonomous mission";
    }
  }

  /* ---------------------------------------------------------------- follow */
  function follow(id) {
    stopFollowing();
    following = true;
    $("btn-stop").disabled = false;
    try { history.replaceState(null, "", `#m=${id}`); } catch (_) { /* ignore */ }
    poll(id);
  }
  function stopFollowing() {
    following = false;
    clearTimeout(timer);
    $("btn-stop").disabled = true;
  }
  async function poll(id) {
    const r = await json(`/api/auto/missions/${encodeURIComponent(id)}`).catch(() => null);
    if (r && r.ok) {
      current = r.body;
      render(current);
      if (current.state !== "running") { stopFollowing(); loadRecent(); return; }
    } else if (r && r.status === 404) {
      $("mission-meta").textContent = "Mission not found on this server.";
      stopFollowing();
      return;
    }
    if (following) timer = setTimeout(() => poll(id), 2500);
  }

  /* ---------------------------------------------------------------- render */
  function render(m) {
    const o = m.options, t = o.target;
    const st = $("mission-state");
    st.textContent = m.state;
    st.className = `tag auto-state auto-state--${m.state}`;
    $("mission-meta").innerHTML = `<b>${esc(t.name)}</b> (${t.planet === "mars" ? "Mars" : "Moon"}, ${coord(t.lat, t.lon)}) · `
      + `${esc(o.objective.replace(/_/g, " "))} · ${esc(o.data_mode)} data · ${esc(o.cleaning)} cleaning · AI ${o.ai ? "on" : "off"}`
      + `<br><span class="mono">${esc(m.mission_id)}</span> · started ${esc(new Date(m.created).toLocaleString())}`
      + (m.error ? `<br><span class="auto-error-inline">${esc(m.error)}</span>` : "");
    $("steps").innerHTML = m.steps.map((s) => `
      <li class="auto-step auto-step--${s.state}">
        <span class="auto-step__dot" aria-hidden="true"></span>
        <div class="auto-step__body">
          <div class="auto-step__head"><b>${esc(s.label)}</b>
            <span class="auto-step__state">${esc(STATE_LABEL[s.state] || s.state)}${s.duration_s != null ? ` · ${dur(s.duration_s)}` : ""}</span></div>
          ${s.detail ? `<p>${esc(s.detail)}</p>` : ""}
        </div>
      </li>`).join("");
    renderLinks(m);
    renderAgents(m);
    renderResults(m);
  }

  function renderLinks(m) {
    const r = m.result || {}, l = r.links || {};
    const items = [["Open in Mission Control", "/app#mission"]];
    if (l.platform_report) items.push(["Full platform report", l.platform_report]);
    if (l.console) items.push(["Console run", l.console]);
    $("links").innerHTML = items.map(([label, href]) => `<a class="btn" href="${esc(href)}" target="${href.startsWith("/app") ? "_self" : "_blank"}" rel="noopener">${esc(label)}</a>`).join("");
    $("links").hidden = false;
  }

  function renderAgents(m) {
    const rows = (m && m.result && m.result.agents) || [];
    const by = Object.fromEntries(rows.map((a) => [a.agent_id, a]));
    const p = (m && m.result && m.result.platform) || {};
    const ai = p.ai || {};
    if (m) {
      const agentsStep = m.steps.find((s) => s.id === "agents");
      $("agents-meta").textContent = rows.length
        ? `Platform run ${m.result.platform_run_id} · ${p.analysis_mode || ""} mode · `
          + `${rows.filter((a) => a.execution === "ai" || a.execution === "ai_cached").length} AI, `
          + `${rows.filter((a) => a.execution === "deterministic").length} deterministic`
          + (ai.fallback_reason ? ` · fallback: ${ai.fallback_reason}` : "")
        : agentsStep && ["failed", "skipped"].includes(agentsStep.state)
          ? `Agents did not run: ${agentsStep.detail || agentsStep.state}`
          : "Waiting for the platform agents…";
    }
    $("agents").innerHTML = ROLES.map(([id, name, kind, purpose]) => {
      const a = by[id];
      const exec = a ? a.execution : "waiting";
      const cls = !a ? "wait" : exec === "ai" || exec === "ai_cached" ? "ai" : exec === "deterministic" ? "det" : "off";
      const via = a && a.provider ? `${a.provider} · ${a.model || ""}${a.cached ? " (cached)" : ""}` : "";
      return `<article class="auto-agent auto-agent--${cls}">
        <header><span class="auto-agent__id">${id}</span><b>${esc(name)}</b></header>
        <p class="auto-agent__kind"><span class="tag">${esc(a ? exec.replace("_", " ") : kind)}</span>${a && a.outcome ? ` <span class="tag">${esc(a.outcome)}</span>` : ""}</p>
        <p class="auto-agent__sum">${esc(a ? a.summary : purpose)}</p>
        ${via ? `<p class="auto-agent__via mono">${esc(via)}</p>` : ""}
        ${a && a.error ? `<p class="auto-agent__err">${esc(a.error)}</p>` : ""}
      </article>`;
    }).join("");
  }

  function table(head, rows) {
    return `<div class="table-wrap"><table class="tbl"><thead><tr>${head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead>`
      + `<tbody>${rows.join("")}</tbody></table></div>`;
  }

  function renderResults(m) {
    const r = m.result || {};
    const out = [];
    const sim = r.similarity || {};
    if (r.best) {
      out.push(`<div class="panel auto-best"><p class="eyebrow">Best Earth analog</p><p class="auto-best__v">${esc(r.best.zone)}`
        + `${r.best.score != null ? ` · <b>${num(r.best.score)} / 100</b>` : ""}</p>`
        + `${r.best.lat != null ? `<p class="auto-hint">Region centre ${coord(r.best.lat, r.best.lon)} · source: ${esc(r.best.source)}</p>` : `<p class="auto-hint">source: ${esc(r.best.source)}</p>`}</div>`);
    }
    for (const [zid, z] of Object.entries(sim)) {
      out.push(`<div class="panel"><h3 class="auto-h3">${esc(z.zone)} <span class="tag">best ${num(z.best_score)} / 100</span></h3>`
        + `<p class="auto-hint">${z.cells_scored ?? "—"} cells scored · features: ${esc((z.features_used || []).join(", "))}</p>`
        + table(["Rank", "Region centre", "Score", "Drivable", "Exact point", "Closest"], (z.top_regions || []).map((x) =>
          `<tr><td>#${x.rank}</td><td>${coord(x.lat, x.lon)}</td><td><b>${num(x.score)}</b></td><td>${x.drivable_pct != null ? num(x.drivable_pct, 0) + " %" : "—"}</td>`
          + `<td>${x.exact_point ? coord(x.exact_point.lat, x.exact_point.lon) : "—"}</td><td>${esc((x.closest || []).join(", "))}</td></tr>`)) + `</div>`);
    }
    const errs = Object.entries(r.analysis_errors || {});
    if (errs.length) out.push(`<div class="panel"><h3 class="auto-h3">Zones not analysed</h3><ul>${errs.map(([z, e]) => `<li><b>${esc(z)}</b>: ${esc(e)}</li>`).join("")}</ul></div>`);
    const p = r.platform || {};
    if (p.top_sites && p.top_sites.length) {
      out.push(`<div class="panel"><h3 class="auto-h3">Platform analog ranking <span class="tag">live NASA evidence</span></h3>`
        + table(["Earth site", "Similarity", "Evidence coverage"], p.top_sites.map((s) =>
          `<tr><td>${esc(s.name || s.site_id)}</td><td><b>${num(100 * (s.similarity || 0))}</b> / 100</td><td>${num(100 * (s.coverage || 0), 0)} %</td></tr>`))
        + (p.limitations && p.limitations.length ? `<details><summary>Limitations</summary><ul>${p.limitations.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></details>` : "")
        + `</div>`);
    }
    const c = r.cleaning_report;
    if (c && c.datasets) {
      out.push(`<div class="panel"><h3 class="auto-h3">Cleaning report <span class="tag">${esc(c.profile)}</span></h3>`
        + table(["Dataset", "Rows in", "Rows out", "Steps"], Object.entries(c.datasets).map(([k, d]) =>
          `<tr><td>${esc(k)}</td><td>${d.rows_in ?? "—"}</td><td>${d.rows_out ?? "—"}</td><td>${d.error ? esc(d.error)
            : esc((d.steps || []).map((s) => `${s.step}: −${s.removed}`).join(" · ") || "none")}</td></tr>`)) + `</div>`);
    }
    const le = r.live_evidence;
    if (le) {
      const obs = (le.observations || []).filter((o) => o.value !== null && o.value !== undefined);
      out.push(`<div class="panel"><h3 class="auto-h3">Live NASA evidence <span class="tag">${esc(le.status)}</span></h3>`
        + (le.status !== "ok" ? `<p class="auto-hint">${esc(le.reason || "unavailable")}</p>` : "")
        + (obs.length ? table(["Feature", "Value", "Unit", "QA"], obs.map((o) =>
          `<tr><td>${esc(o.feature_id)}</td><td>${num(o.value, 3)}</td><td>${esc(o.unit || "")}</td><td>${esc(o.qa_status || "")}</td></tr>`)) : "")
        + `</div>`);
    }
    const nar = r.report && r.report.narrative;
    if (nar) {
      out.push(`<div class="panel"><h3 class="auto-h3">Report summary <span class="tag">${esc(nar.generated_by || "")}</span></h3>`
        + `<p>${esc(nar.executive_summary)}</p>`
        + (nar.key_findings && nar.key_findings.length ? `<ul>${nar.key_findings.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : "")
        + (nar.note ? `<p class="auto-hint">${esc(nar.note)}</p>` : "")
        + (nar.numeric_check && nar.numeric_check.removed_items.length ? `<p class="auto-hint">${nar.numeric_check.removed_items.length} AI statement(s) removed: numbers not found in the facts.</p>` : "")
        + `</div>`);
    }
    $("results").innerHTML = out.length ? out.join("") : `<p class="auto-hint">${m.state === "running" ? "Results appear here as each step completes." : "This mission produced no result data (see the step details above)."}</p>`;
  }

  /* ---------------------------------------------------------------- recent + status */
  async function loadRecent() {
    const r = await json("/api/auto/missions?limit=12").catch(() => null);
    if (!r || !r.ok) { $("recent-list").innerHTML = '<p class="auto-hint">Recent missions unavailable.</p>'; return; }
    const ms = r.body.missions || [];
    if (!ms.length) { $("recent-list").innerHTML = '<p class="auto-hint">No missions yet on this server.</p>'; return; }
    $("recent-list").innerHTML = table(["Mission", "Target", "Objective", "State", "Steps", "Best", ""], ms.map((m) => {
      const steps = Object.entries(m.steps).map(([k, v]) => `<span class="auto-mini auto-mini--${v}" title="${esc(k)}: ${esc(v)}"></span>`).join("");
      return `<tr><td class="mono">${esc(m.mission_id)}<br><span class="auto-hint">${esc(new Date(m.created).toLocaleString())}</span></td>`
        + `<td>${esc(m.target.name)}<br><span class="auto-hint">${m.target.planet === "mars" ? "Mars" : "Moon"}</span></td>`
        + `<td>${esc(m.objective.replace(/_/g, " "))}</td><td><span class="tag auto-state--${m.state}">${esc(m.state)}</span></td>`
        + `<td><span class="auto-minis">${steps}</span></td><td>${m.best ? `${esc(m.best.zone)}${m.best.score != null ? ` · ${num(m.best.score)}` : ""}` : "—"}</td>`
        + `<td><button class="btn auto-open" type="button" data-id="${esc(m.mission_id)}">Open</button></td></tr>`;
    }));
  }

  async function loadStatus() {
    const r = await json("/api/ai/status").catch(() => null);
    const b = $("ai-badge");
    if (r && r.ok) {
      const on = r.body.providers.filter((p) => p.configured).map((p) => p.name.split(" ")[0]);
      b.textContent = r.body.enabled ? `AI ready · ${on.length} free providers` : "AI unavailable";
      b.title = r.body.enabled ? `Configured: ${on.join(", ")}. Free tiers only; paid inference is blocked.` : (r.body.reason || "");
      b.className = `tag ${r.body.enabled ? "auto-ok" : "auto-warn"}`;
    } else { b.textContent = "AI status unknown"; b.className = "tag auto-warn"; }
    const h = await json("/v1/health").catch(() => null);
    const a = $("api-badge");
    const up = h && h.ok && h.body.status === "ready";
    a.textContent = up ? `Platform API ready${h.body.ai_enabled ? " · agents AI on" : " · agents deterministic"}` : "Platform API offline";
    a.title = up ? "The 13 agents run on the TwinSite platform API." : "The agents step will be reported as failed; bundled analysis still runs.";
    a.className = `tag ${up ? "auto-ok" : "auto-warn"}`;
  }

  function reset() {
    stopFollowing();
    current = null;
    try { history.replaceState(null, "", location.pathname); } catch (_) { /* ignore */ }
    $("mission-state").textContent = "idle";
    $("mission-state").className = "tag";
    $("mission-meta").innerHTML = "No mission yet. Configure the setup and press <b>Launch autonomous mission</b>.";
    $("steps").innerHTML = "";
    $("links").hidden = true;
    $("results").innerHTML = '<p class="auto-hint">Results appear here as each step completes.</p>';
    $("agents-meta").textContent = "The platform runs these agents on the mission. Deterministic agents compute; AI agents interpret and are checked. AI never changes scores or the release decision.";
    renderAgents(null);
    formError(null);
    $("f-target").focus();
  }

  /* ---------------------------------------------------------------- wire */
  document.querySelectorAll('input[name="planet"]').forEach((x) => x.addEventListener("change", fillTargets));
  $("f-target").addEventListener("change", onTarget);
  $("auto-form").addEventListener("submit", launch);
  $("btn-stop").addEventListener("click", stopFollowing);
  $("btn-new").addEventListener("click", reset);
  $("btn-refresh").addEventListener("click", loadRecent);
  $("recent-list").addEventListener("click", (e) => {
    const b = e.target.closest(".auto-open");
    if (b) { follow(b.dataset.id); window.scrollTo({ top: 0, behavior: "smooth" }); }
  });
  fillTargets();
  renderAgents(null);
  loadStatus();
  loadRecent();
  const m = /#m=(am-[0-9a-f]{12})/.exec(location.hash);
  if (m) follow(m[1]);
})();
