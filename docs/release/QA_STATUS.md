# QA_STATUS — C5 (TWIN-QA), 2026-11-15 04:10 UTC

> **Update (later on 2026-11-15, after the C0 integration):** this snapshot is historical.
> - The C2 engine is wired in.
> - The official SRTM tile is cached, and the MOLA origin bytes are re-verified.
> - `make verify` gives 16 automated PASS and 0 FAIL. Live HTTP, browser, restart and crash checks pass.
>
> Current status: [`LIVE_ACCEPTANCE.md`](LIVE_ACCEPTANCE.md) and [`SCIENTIFIC_REVIEW.md`](SCIENTIFIC_REVIEW.md).
> Recommendation is still **HOLD** for scientific release (BLOCK) and for deployment, because no VM has been approved.

**Recommendation: HOLD.**
- Synthetic end-to-end works and survives restarts and crashes.
- G2 has half a pair: the Mars MOLA bytes are independently verified against NASA PDS, but no Earth bytes exist.
- C2's engine is not wired in.
- Nothing is deployed.

| Item | Value |
| --- | --- |
| P0 blockers | **4** (below) |
| Tests | `ops/verify.sh`: **22 PASS / 0 FAIL / 1 BLOCKED (G2)**, plus 9 ownership WARNs for C0 |
| Deployed URL | **none**: no host or OK. Runbook in `DEPLOYMENT.md` |
| Tested tree | composite of committed branches, built outside the repo: main `9b8570c` + data `1cba3df` + science `18025cd` + backend `0383322` + frontend `d4b6043` |
| Lane sessions (app note, ~04:00 UTC) | c1-data idle; c2-science, c3-backend and c4-frontend reported **failed**, though all have since committed. Treat further deliveries as uncertain |

## Gate status

| Gate | Status | Evidence |
| --- | --- | --- |
| G0 contracts | PASS | Draft 2020-12 schemas, types drift, freeze and integration unittest all PASS in the composite. C0 had these BLOCKED |
| G1 end-to-end | **PASS for API + worker + build; UI flow not browser-tested** | C0 smoke and C5 acceptance PASS against C3. The frontend `npm ci` (lockfile present) and build PASS. Clicking through the UI was not exercised |
| G2 scientific evidence | **BLOCKED (half)** | Mars: verified (below). Earth: SRTMGL1 is only an incomplete `.part` in C1's worktree. No `release_evidence`/measured run on any branch. C2 not wired (P0-2) |
| G3 | NOT STARTED | `/v1/data/*` and alternatives return 501 (explicit, not simulated) |
| G5 AI-free / restart | PASS (synthetic) | See e2e below |

## G2 real-NASA verification performed by C5 (independent of C1's code)

| Asset (C1 worktree `.runtime`, uncommitted) | C5 check | Result |
| --- | --- | --- |
| `megt00n090hb.lbl`, MGS-M-MOLA-5-MEGDR-L3-V1.0, pds-geosciences.wustl.edu | Re-downloaded from PDS and SHA-256 compared | **MATCH** `c85891df…` |
| `megt00n090hb.img`, 38 HTTP byte ranges (38×38 px, 128 px/deg) | Re-fetched the same 38 ranges from PDS and compared the concatenated SHA-256 | **MATCH** `2bc27bff…` (2888 bytes) |
| same | C5 decode as MSB int16 | min −4532, max −2996, mean −4365.0 m. The offsets give a window of ~137.25–137.55°E, 4.45–4.75°S, which covers the target bbox; values are plausible for Gale crater |
| `megc00n090hb.lbl` / `.img` ranges | Refetch | BLOCKED: PDS connection timed out; on-disk hashes match the manifest |
| SRTMGL1 `N30W006` | — | **MISSING**: 3.2 MB `.part` only (incomplete download) |

**Provenance gaps:**
- No Earth raw bytes.
- No committed manifest or evidence JSON.
- MOLA assets are still uncommitted runtime files.
- MOLA areoid/radius convention not yet compared to C1's derived feature.
- No measured contribution lineage, because no measured run exists.

## Tests run (stack booted by C5 from the composite, all credential env vars stripped)

| Suite | Result |
| --- | --- |
| C0 checkpoint inside composite | integration, schemas, types, reference (39), handoff (7), freeze, **reference API smoke**, **frontend build**: all PASS |
| C0 `smoke.py` against C3 | PASS |
| C5 HTTP acceptance | **15 PASS / 0 FAIL / 1 NOT_EXERCISED** (data explorer 501). Covers: AI/uploads off, no leaks; 400 missing key; 413 >1 MB; 400/422 bad JSON; `id==run_id`; replay; canonical input hash; stable bytes; synthetic ⇒ BLOCK; event cursor/ordering/P00–P90; report content-type + synthetic label; **XSS marker rendered escaped `&lt;script&gt;`**; 404s; GET ≠ create (405); uploads 501; AI routes 404 |
| C5 e2e | **8/8 PASS**: boot with zero keys; restart ⇒ status/result/evidence/report/events byte-identical and idempotency persists; worker down ⇒ `queued` + 409 then completes; **SIGKILL mid-run ⇒ attempt 2, identical result**; AI flag on with no keys ⇒ identical; bad data dir ⇒ refuses to start |
| Provenance checker self-test | 14/14 (negative controls + constructed non-NASA control correctly *not* NASA-verified) |
| Secret scan | 0 findings (positive control detected) |

**Caveat:** the "client `data_status: measured` is not released" check passes only because measured runs are currently unsupported (the worker fails them). It is not yet evidence of relabel detection; re-run once C2 is wired.

## P0 blockers

1. **G2 Earth half (C1):** no complete SRTMGL1 (or equivalent) bytes, no committed asset manifest or `release_evidence`. Running `TWINSITE_G2_EVIDENCE=… TWINSITE_G2_ARTIFACT_ROOT=… TWINSITE_G2_REFETCH=1 ops/verify.sh` is the gate. `srtm.py` mentions `step.esa.int`, which FAILs as `NON_NASA_HOST`; use LP DAAC.
2. **C2 not wired (C2/C3 interface):** C3's `jobs/science_adapter.py` looks up `twinsite.science.analyze` (+`ALGORITHM_VERSION`/`VERSION`). C2 exports `analyze_mission(request, evidence, mode, …)` and `ENGINE_VERSION`. The composite therefore silently uses the **ARES reference engine**, and C2's engine never runs. Every green HTTP check above is still the reference engine on synthetic data. C0 must pick one name or signature.
3. **UI flow unverified in a browser:** submit → real events → `/analysis/:runId` → banner. Build passes; the demo path (`demo-*` IDs, clock-driven replay) is labelled "DEMO / SYNTHETIC" and must never be filmed as live.
4. **Deployment (user-owned):** no host, access or explicit OK, so no public URL.

## Needs C0 ruling (WARN)

- Files outside `lanes.json` paths: C1 `backend/tests/data/**`; C2 `backend/tests/science/**`; C3 `API_STATUS.md`, `backend/tests/**`.
- Deployment needs `references/extracted/` (`make bootstrap`) for the synthetic engine.
- C0's `twinsite_api_smoke` hits whatever listens on :8080. C5's authoritative run boots its own stack.
- External-AI consent tests can't run: no AI routes exist (safe default, no transmission). Retest when they exist.

## Request to C0

Add `verify:` → `ops/verify.sh` to the root Makefile.

## Files (lane/qa)

`ops/{assemble.py,verify.sh,secret_scan.py}`, `tests/acceptance/{http_contract.py,provenance_check.py,test_provenance_check.py}`, `tests/e2e/run_stack.py`, `docs/release/{QA_STATUS,DEPLOYMENT,DEMO_CHECKLIST}.md`
