# Live acceptance (G1) — 2026-11-15

Run on macOS with local sockets allowed, against `main` after `71860f8` plus the fixes listed here.
Every child process ran with the Earthdata secret file disabled (`TWINSITE_SECRET_ENV_FILE` set to a
missing path). No network acquisition was performed; measured runs use the verified local cache.

## Automated (`make verify`)

16 automated suites PASS, 0 FAIL. `browser_smoke` is always reported as needing a separate
manual run, so `make verify` still exits non-zero by design. Its result is recorded below.

| Suite | Result |
| --- | --- |
| schemas, types, integration, science, data, c0, qa_negative_controls, store_worker | PASS |
| frontend typecheck / build / unit tests (26) | PASS |
| backend_http (6 HTTP tests) | PASS |
| c5_http_restart_e2e: boot, smoke, 16 HTTP acceptance checks, restart, worker-down, SIGKILL, AI flag, bad storage | PASS (synthetic path) |
| measured_http_restart_e2e (`tests/e2e/measured_live.py`, 21 checks) | PASS (measured path) |
| secret_scan | PASS |
| c5_measured_provenance (19 checks on current evidence) | PASS |

`measured_live.py` starts its own API and worker processes and checks the following:

- **Engine:** the C2 engine is used (`twinsite-science/0.1.0`, never ARES), and result and evidence are both `measured`.
- **Release gate:** stays `BLOCK`, with `C5_INDEPENDENT_REVIEW_REQUIRED`, `NO_QUALIFIED_CANDIDATE` and `UNREGISTERED_FEATURE:dry_fraction`.
- **Valid outcome:** `no_feasible_portfolio` is preserved.
- **Events:** ordered P00–P90, and every worker phase ends `succeeded`.
- **Restart:** after an API and worker restart, the result, evidence and report are byte-identical. An idempotent replay returns the same run.
- **Worker down:** with the worker stopped, a run stays queued and then completes once the worker starts. Results are deterministic across runs.
- **SIGKILL:** killing the worker mid-run recovers at attempt 2, with an identical result.
- **Guards (422):** the server rejects a client-asserted measured payload, an unknown dataset, and client-supplied mission parameters.
- **Data API:** returns 200, 404 and 422 as specified, with no 500s for malformed bodies.

## Browser (manual, built-in browser against Vite + live API)

| Check | Result |
| --- | --- |
| Header shows "API connected · AI off"; network panel shows real `/v1/*` 2xx responses | PASS |
| Workspace → "Analyze measured Zagora–Gale pair" → `POST /v1/missions/measured` 202 → Analysis page | PASS |
| Analysis page: MEASURED badge, strict gate and release both BLOCK, blockers listed, scores withheld until diagnostics are opened ("Do not cite") | PASS |
| Activity: complete P00–P90 timeline from committed events | PASS after fix 1 |
| Portfolios: "No feasible portfolio" with the actual reason (access status unknown) | PASS after fix 2 |
| Report: C2 version, BLOCK, five source assets with SHA-256, assumptions and gaps, JSON/CSV downloads | PASS |
| Data Explorer catalog, records, Source & QA, and Compare are served from `/v1/data/*` (no demo banner) | PASS |
| Unknown dataset or run shows the real API error, with no demo substitution | PASS after fix 3 |
| API stopped: demo banner reads "DEMO / SYNTHETIC … API unreachable", and the measured button is disabled | PASS after fix 4 |
| Mobile 375×812: no horizontal page overflow on Overview, Workspace, Explorer, Data, Compare, Analysis, Activity, Portfolios, Report, Docs | PASS after fix 5 |
| Console: no errors apart from the deliberate 404 and offline tests | PASS |

## Defects fixed in this pass

1. **Worker events:** phases P30–P80 were left `running` after completion. Engine phases now record `succeeded` when the C2 call returns, and run status only moves forward.
2. **Portfolios page:** text read "max —-site", and the infeasibility notice was generic. It now lists each ineligible site's failures and states that this is a valid outcome.
3. **Data Explorer:** it replaced *any* API error (404/422/500) with synthetic demo tables. Demo fallback now happens only when the API is unreachable or returns 501, and real errors are shown. Queries no longer retry 4xx responses.
4. **Offline handling:** when the backend was down, the proxy's bare 5xx was reported as a server error. A 5xx without the API's JSON error envelope now counts as "unreachable".
5. **Mobile layout:** grid children could overflow narrow viewports (the activity history table and long `<select>` options).
6. **Diagnostics:** worker and API failures logged only the exception class. Full tracebacks now go to the protected service log, while public run errors stay redacted.
7. **Data Explorer metadata:** it was missing the site title, temporal coverage, product version and data-policy link, and showed a raw Python dict as the time basis.
