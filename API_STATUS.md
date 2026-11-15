# C3 TWIN-API status — lane/backend

Checkpoint: 2026-11-15. Owner paths: `backend/twinsite/{api,jobs,storage,ai}/`, `backend/tests/`, this file.

**G1 backend: DONE locally.** The API and worker run as separate processes, and C0's frozen `scripts/integration/smoke.py` passes against them.
**Data/evidence G3 routes: NOT IMPLEMENTED.** They return an explicit 501, as the contract requires, pending C0 schema review.
**AI router: deterministic stub.** Inference is off.
All runs so far use SYNTHETIC fixtures. No NASA-measured result exists.

## DONE

- **Durable job queue** (`storage/db.py`). SQLite in WAL mode, which the contract accepts as the demo fallback (one API process plus exactly one worker).
  - `BEGIN IMMEDIATE` writes.
  - Idempotent POST: same key and same canonical SHA-256 replays the identical `mission_accepted`; same key with a different body gives 409.
  - Bounded queue of 20 (429 with `Retry-After`).
  - One active mission at a time, and at most 3 attempts.
  - Lease, heartbeat and fence token. Expired leases are re-queued, or failed once the attempt budget is exhausted.
- **Atomic, fenced commit.** The result, `release_evidence` sidecar, HTML report and terminal status are written in one transaction.
- **Content-addressed blob store** (`storage/blobs.py`). Committed artifacts are stored under `artifact_root/sha256/..`. Events expose only `sha256:` IDs, never paths.
- **Worker** (`jobs/worker.py`, `python -m twinsite.jobs`). Emits real phase events P00–P90 with per-run sequence numbers 1..n.
  - Totals are `null` when unknown.
  - P10 and P20 truthfully report that 0 assets were acquired or decoded for inline input.
  - Only transient failures are retried, with exponential backoff (`TransientError`, sqlite `OperationalError`, timeouts, connection errors). Invalid input and internal errors fail permanently on the first attempt.
  - Cancellation is checked at every phase boundary.
- **Science adapter** (`jobs/science_adapter.py`). C3 implements no scoring.
  - It prefers C2's `twinsite.science.analyze(payload, progress=None)` (optional `validate`, `VERSION`).
  - Otherwise it loads the pinned ARES reference engine from `references/extracted/...`, or from `TWINSITE_REFERENCE_ENGINE_DIR`. The fallback is used for SYNTHETIC input only.
  - All four frozen fixture pairs reproduce byte-exactly.
- **Fail-closed evidence.**
  - Synthetic runs get `release_action: BLOCK`, `strict_gate_status: NOT_EVALUATED` and `blocking_issues: [SYNTHETIC_ONLY]`, and end as `completed_with_limits`.
  - `source_snapshot_id` is set on status and sidecar from P10 onward.
  - **Measured input fails with `MEASURED_EVIDENCE_UNAVAILABLE`, and no result is published.** Client-asserted measurements are never treated as science.
- **HTTP API** (`api/server.py`, `python -m twinsite.api`). Built on stdlib `ThreadingHTTPServer`, with zero third-party dependencies.
  - Serves all G1 routes in the contract table.
  - Request checks run in this order: 415 → 400 (Content-Length) → 413 → 400 (Idempotency-Key) → 422 (JSON, NaN, schema, then engine cross-field checks) → 409/429.
  - Error bodies follow `error.schema.json`. JSON never contains NaN.
  - The HTML report is served as `text/html; charset=utf-8` with a restrictive CSP and fully escaped content.
  - CORS is allowlisted for the Vite dev origins.
- **OpenAPI 3.1** is committed at `backend/twinsite/api/openapi.json` and also served at `GET /v1/openapi.json`. Its components are C0's frozen schemas.
- **Report** (`jobs/report.py`): a deterministic template showing the synthetic and BLOCK banners, snapshot, input hash, sites, portfolios, rejected candidates, limitations and unknowns.
- **AI** (`ai/registry.py`):
  - All 13 roles A01–A13 are registered.
  - `route()` always returns the deterministic implementation.
  - The policy is free-only hard block: no paid fallback, a 60% demo reserve, and quota UNKNOWN.
  - Health always reports `ai_enabled:false, uploads_enabled:false`, and the server starts with zero keys.

## Deviation from lane prompt (for C0)

The lane prompt says "FastAPI". `make dev` runs the API with C0's `.venv` interpreter, which contains only `jsonschema`, and PyPI was unreachable when this session started. I therefore used the stdlib. The HTTP behaviour and OpenAPI document are what the contract requires.

SQLite+WAL replaces PostgreSQL/PostGIS. The contract explicitly accepts this demo fallback when the store is durable and there is a single worker.

## FILES

| Path | Purpose |
| --- | --- |
| `backend/twinsite/storage/{config,db,blobs}.py` | Env config, durable queue/events/results, blob store |
| `backend/twinsite/jobs/{worker,science_adapter,evidence,report,contract}.py`, `__main__.py` | Worker, engine adapter, sidecar, HTML template, contract validation adapter |
| `backend/twinsite/api/{server,openapi}.py`, `__main__.py`, `openapi.json`, `.env.example` | HTTP API, OpenAPI document, env variable names (no values) |
| `backend/twinsite/ai/registry.py` | Deterministic 13-role registry stub |
| `backend/tests/api/test_backend.py` | 16 tests: store, worker, HTTP, C0 smoke, OpenAPI drift |

## TESTS

From the worktree root:

```sh
PYTHONPATH=backend:. TWINSITE_REFERENCE_ENGINE_DIR=/Users/macbook/Projects/TwinSite/references/extracted/ARES_NASA_Feasibility_Architecture/ARES/implementation \
  /Users/macbook/Projects/TwinSite/.venv/bin/python -m unittest discover -s backend/tests -t backend -v
```

The test file finds the engine automatically when the env var is unset: it checks the worktree first, then the main checkout.

| Check | Result |
| --- | --- |
| Unit and HTTP suite (C0 `.venv`, jsonschema present) | **16/16 pass**. Includes HTTP POST of each fixture: `input_sha256 == contracts.validation.digest(original)` and the result equals the frozen fixture. |
| Same suite under bare `python3.13` (no jsonschema) | Passes with the smoke test skipped (it needs jsonschema). The server falls back to a minimal structural check. |
| C0 `scripts/integration/smoke.py --base-url` against real `python -m twinsite.api` and `python -m twinsite.jobs` processes | **PASS** |
| Four frozen synthetic request/result pairs through the worker | Byte-identical to `contracts/examples/*.result.synthetic.json` |
| Covered failure paths | 413 (>1,000,000 B), 400 (missing key / bad cursor), 415, 422 (NaN / schema), 404, 405 and 501 |

## C0 REQUESTS

1. **Add `POST /v1/missions/{run_id}/cancel` to the contract.** It is already implemented and marked `x-twinsite-status: provisional` in OpenAPI.
   - It returns 202 with `mission_status`, and 404 for an unknown run.
   - A queued run is cancelled at once. An active run is cancelled at the next phase boundary.
   - The CLI equivalent is `python -m twinsite.jobs cancel RUN_ID`.
2. **Response schemas for the G3 routes**: catalog, records, metadata, compare and alternatives. Proposal:
   - **catalog:** `{schema_version, items:[{dataset_id,title,body,provider,license,data_status,version}], next_cursor}`
   - **records:** `{schema_version, dataset_id, stage, columns:[allowlisted], rows:[...], next_cursor}`
   - **metadata:** `{schema_version, dataset_id, source, version, license, time_range, qa, geometry, crs, resolution_m, lineage:[provenance_id...]}`
   - **compare:** `{schema_version, dataset_ids, columns, rows, provenance_ids}`
   - Until these schemas are approved and C1 publishes an approved public dataset index, these routes return 501. No simulated data is served.
3. **Root `.env.example`.** Please append the names in `backend/twinsite/api/.env.example`: `TWINSITE_QUEUE_LIMIT`, `TWINSITE_LEASE_SECONDS`, `TWINSITE_CORS_ORIGINS`, `TWINSITE_REFERENCE_ENGINE_DIR`.
4. **Package layout.** No `backend/twinsite/__init__.py` is needed: `twinsite` is an implicit namespace package. Please don't add one unless all lanes agree.
5. **Lane ownership.** `review_lane.py lane/backend` flags `API_STATUS.md`, `backend/tests/__init__.py` and `backend/tests/api/*` as cross-owner.
   - The lane brief assigns them to C3.
   - Please add `backend/tests/api/` and `API_STATUS.md` to C3 in `lanes.json`, or confirm them at review.
   - Nothing else outside `backend/twinsite/{api,jobs,storage,ai}/` changed. `git diff --name-status main..lane/backend` confirms it.
6. **`make dev`** already matches the entry points. After `make bootstrap`, the reference engine resolves from `references/extracted/` in the main checkout.

## Interfaces for other lanes

- **C2.** Expose `twinsite.science.analyze(payload, progress=None) -> mission_result`.
  - Call `progress(stage, completed)` with the ARES stage names `P30_CLEAN, P40_QUALITY, P60_ANALYZE, P70_PORTFOLIO, P80_REVIEW, P90_PUBLISH`.
  - Optionally provide `validate(payload)`, which raises `ValueError` for cross-field violations, and `VERSION`.
  - The adapter picks your engine up automatically, and it then also runs for measured inputs, once a C1 resolver exists.
- **C1.** Measured release needs an evidence resolver that returns `release_evidence` `assets` and `observations` for a request.
  - Until one is integrated, measured runs fail closed.
  - The intended hook is the `data_status != 'synthetic'` branch in `jobs/worker.py::_pipeline`.
- **C4.** Use `backend/twinsite/api/openapi.json` or `GET /v1/openapi.json`.
  - Poll `GET /v1/missions/{id}/events?after=<last seq>`.
  - Treat `completed_with_limits` plus `release_action: BLOCK` as "synthetic / not released".
  - Allowed dev origins are `http://127.0.0.1:5173` and `http://localhost:5173`, configurable with `TWINSITE_CORS_ORIGINS`.

## Run without the frontend

`make dev` refuses to start until `frontend/package.json` exists. To run the backend on its own, start the API and worker in two terminals from the worktree, or from main after the merge:

```sh
export PYTHONPATH=backend:. TWINSITE_API_PORT=8080
.venv/bin/python -m twinsite.api        # terminal 1
.venv/bin/python -m twinsite.jobs       # terminal 2
.venv/bin/python scripts/integration/smoke.py --base-url http://127.0.0.1:8080
```

In a worktree with no `references/extracted/`, also set `TWINSITE_REFERENCE_ENGINE_DIR=/Users/macbook/Projects/TwinSite/references/extracted/ARES_NASA_Feasibility_Architecture/ARES/implementation`.

## BLOCKERS

- **Backend: none.** This does NOT mean G1 is unblocked. Full G1 acceptance (the UI) is still blocked on C4, and C2 has no `twinsite.science` engine yet, so the ARES synthetic reference fallback is in use.
- G2 depends on C1 (approved assets and evidence resolver) and C2 (`twinsite.science`). Neither exists on its branch at this checkpoint.

## NEXT GATE

1. C0 merges `lane/backend` and runs `make dev` + `make smoke`.
2. C4 wires up the UI.
3. C5 runs negative controls.
4. G3 data routes follow once C0 approves the schemas and C1 publishes its dataset index.
