# C4 TWIN-UI status — lane/frontend

Owner paths: `frontend/` only. Checkpoint written 2026-11-15 (submission cutoff day).

## DONE (code written; see TESTS for what has actually been verified)

- Vite + React 18 + TypeScript + Tailwind v4 + React Router + TanStack Query + MapLibre GL 5.
- Visual language: reference image 3 (black `#0b0a09`, warm ivory `#efe7d6`, muted orange `#c8642b`, serif editorial headings). Blue-neon drafts ignored. The reference's "System Status" pill, settings gear and invented percentages were deliberately NOT copied.
- Routes (all from `contracts/FRONTEND_ROUTES.json`): `/`, `/workspace`, `/explorer`, `/analysis/:runId`, `/portfolios/:runId`, `/data`, `/data/:datasetId`, `/activity/:runId`, `/reports/:runId`, `/docs`. No login, RBAC, profile, settings or health panels.
- **G1 flow:** Workspace (explicit Run) → `/analysis/:runId` shows real P00–P90 events while the job runs (polls `events?after=N`, no percentages) → same URL shows results once `completed` / `completed_with_limits`.
- Analysis: run/target/phase/snapshot/time-basis strip, strict-gate + release banner, ranked candidates with derived strengths/weaknesses, feature comparison table with source IDs, confidence as three separate readings (QA, coverage, stability), temporal tab (observation periods from evidence), gaps/limitations.
- Release gating: measured result with missing/BLOCK evidence sidecar → scores withheld behind an explicit "diagnostic, do not cite" reveal. Synthetic results always carry the DEMO / SYNTHETIC banner.
- Portfolios: standalone vs combined tabs, cost-vs-objective chart ("no cost" lane when the user supplied none), dimension coverage, alternatives action (`POST …/portfolios/alternatives`, 501 handled).
- Explorer: Earth = MapLibre (NASA GIBS Blue Marble) 2D + 3D globe; Moon/Mars = imagery-free equirectangular planetocentric SVG map (no Earth data on other bodies); candidate pins + target footprints from the selected run.
- Data Explorer: catalog with filters + pick-two compare, raw / cleaned / derived tabs, source & QA tab, side-by-side compare table, bounded (≤100 rows) CSV sample download.
- Activity, Report (source-backed in-app report, JSON/CSV exports, print/PDF, sandboxed server HTML iframe when live), Docs, full Landing.

## DATA MODES (read this before judging screenshots)

| Mode | When | What the user sees |
| --- | --- | --- |
| **Live** | `GET /v1/health` returns ready (Vite proxies `/v1` → `http://127.0.0.1:8080`, override with `TWINSITE_API_URL`) | Real `POST /v1/missions`, real events/result/evidence/report. "Run synthetic fixture (DEMO data)" button posts a frozen synthetic request so the real pipeline can be exercised (C3 fails measured requests closed with `MEASURED_EVIDENCE_UNAVAILABLE`). |
| **Demo** | API unreachable, or `VITE_FORCE_DEMO=1`, or runId starts `demo-` | Frozen contract fixtures. Amber DEMO / SYNTHETIC banner on every affected page; header says "API offline · demo fixtures"; P00–P90 lifecycle is a labelled `[DEMO REPLAY]`. Workspace "Run" opens a fixture and says the parameters are not scored. |
| **Data Explorer fallback** | `/v1/data/*` returns 501/404/network error | DEMO tables derived from the synthetic fixtures (raw = request observations, cleaned = + result transformations, derived = contributions). Banner states why. |

No NASA values are fabricated anywhere in this lane. Maps use NASA GIBS imagery only as a basemap.

## CONTRACT REQUESTS FOR C0

1. **Mission request without client measurements.** `mission_request.schema.json` requires `sites` and `target_profiles` (minItems 1, each with observations). A frontend cannot (and per SHARED_CONTRACT must not) assert measurements. Needed: either a documented "measured/resolve-server-side" request shape (e.g. `sites: []`, `target_profiles[].observations: {}`) that C3 accepts and passes to the C1 resolver, or a separate request schema. The UI currently sends `data_status: "measured"`, `sites: []`, empty target observations; today C3 fails this closed.
2. **G3 response schemas** (catalog, records, metadata, compare, alternatives). UI adapters are tolerant of C3's proposal (`items[{dataset_id,title,body,provider,license,data_status,version}]`) but additionally want: `domain`, `resolution`, `temporal_coverage`, `records` (count), `qa_status`, a `sampled`/`total` flag on records, and per-record stable `record_id` for compare.
3. **List-runs endpoint** (optional): there is no `GET /v1/missions`; the UI remembers run IDs in `localStorage` only.
4. Accept C3's provisional `POST /v1/missions/{run_id}/cancel` (UI does not use it yet).
5. Frozen phase→status mapping for the progress screen is taken from `FRONTEND_ROUTES`/SHARED_CONTRACT; no change needed.

## DEVIATIONS / HONEST LIMITS

- Charts are hand-rolled SVG (cost/objective scatter, meters) rather than a chart library — fewer dependencies, full control over unlabelled 0–1 indices.
- Moon/Mars have no imagery basemap: MapLibre cannot render the NASA Trek equirectangular tiles without distortion in the time available. The planetocentric grid map is explicit about this.
- "Strength/weakness" marks (similarity ≥ 0.80 / < 0.50) are display conventions, stated in the UI, not scientific thresholds.
- Earth custom bounding box is selectable by preset only (no free-form Earth bbox inputs yet).
- Time-basis/temporal tabs fill only from evidence observations; synthetic runs show "none attested".

## FILES CHANGED

All new under `frontend/`: `package.json`, lockfile, `vite.config.ts`, `tsconfig.json`, `index.html`, `src/**` (lib/, components/, pages/, `__tests__/`), `UI_STATUS.md`, `screenshots/`.

## TESTS RUN + RESULTS

_See "VERIFICATION LOG" below (filled in after the run)._

## BLOCKERS

- npm registry throughput was ~30–90 KB/s and one `npm install` stalled/crashed mid-run ("Exit handler never called"); retried successfully (see log below).

## NEXT GATE

G1: C0 merges `lane/backend` + `lane/frontend`, runs `make dev`; verify Live mode end-to-end with the synthetic fixture button. G3: swap Data Explorer adapters to the frozen response schemas once approved.

## VERIFICATION LOG
