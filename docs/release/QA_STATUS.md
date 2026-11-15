# QA_STATUS — C5 (TWIN-QA), 2026-11-15 ~04:00 UTC

**Recommendation: HOLD.** The backend job/worker/evidence flow is solid on synthetic data, but there is no real NASA Earth + Moon/Mars evidence, no committed frontend and no deployment. Nothing scientific can be released.

| Item | Value |
| --- | --- |
| P0 blockers | **4** (below) |
| Deployed URL | **none** (no host/OK; runbook ready in `DEPLOYMENT.md`) |
| Tested tree | composite of committed branches: main `9b8570c` + lane/backend `7a7b8ac` (lane/data, science, frontend: 0 commits) |
| How to reproduce | `ops/verify.sh` (or `--from-worktrees` to include uncommitted lane work) |

## Gate status

| Gate | Status | Evidence |
| --- | --- | --- |
| G0 contracts | PASS (new) | In the composite: Draft 2020-12 schema validation PASS, types drift PASS, freeze PASS, integration unittest PASS. C0 had these BLOCKED; jsonschema is now in `.venv` |
| G1 end-to-end | **PARTIAL** | API → worker → events → result/evidence/report all PASS. The frontend leg is BLOCKED: C4 has no commits |
| G2 scientific evidence | **BLOCKED** | No measured run, raw NASA bytes or manifest on any branch. C1 worktree holds only an incomplete `N30W006.SRTMGL1.hgt.zip.part`. C2 engine absent |
| G3 features | NOT STARTED | `/v1/data/*` and alternatives return 501 (correctly explicit, never simulated) |
| G5 AI-free / restart | PASS (synthetic) | Zero provider keys; AI flag on with no keys gives an identical result; restart and SIGKILL recovery pass |

## Tests run (all against a stack C5 booted from the composite, with credentials stripped from env)

| Suite | Result |
| --- | --- |
| C0 checkpoint inside composite: integration unittest, schemas, types, reference unittest (39), handoff unittest (7), freeze, **reference API smoke** | 7 PASS (reference HTTP smoke was BLOCKED for C0 and now PASSes; historical, synthetic only). frontend_build BLOCKED |
| C0 `smoke.py --base-url` against C3 | PASS |
| C5 HTTP acceptance (`tests/acceptance/http_contract.py`) | **15 PASS / 0 FAIL / 1 NOT_EXERCISED**: health has AI/uploads off and no leaks; 400 on missing key; 413 on >1 MB (sent from Content-Length); malformed JSON gives 400/422; `id==run_id`; idempotent replay; canonical input SHA-256; stable result bytes; synthetic evidence ⇒ BLOCK; event cursor 400s, ≤200 per page, ascending, P00–P90; report `text/html; charset=utf-8` and visibly synthetic; **report escapes `<script>` from user input**; client `data_status: measured` over synthetic values is NOT released; 404s; GET doesn't create a job (405); uploads 501; AI probes 404. The data explorer is 501, so NOT_EXERCISED |
| C5 e2e (`tests/e2e/run_stack.py`) | **8/8 PASS**: boot with zero keys; full API+worker restart leaves status/result/evidence/report/events **byte-identical** and the idempotency key persists; worker down ⇒ run stays `queued` with result 409, then completes; **SIGKILL mid-run (during analyzing) ⇒ recovered at attempt 2 with an identical result**; AI flag on with no keys ⇒ identical result; unusable data dir ⇒ API refuses to start |
| C5 provenance checker self-test | 14/14 PASS. Negative controls: synthetic example rejected; relabelled synthetic rejected; mutated bytes; non-NASA host; signed URL; body/product mismatch; no common scale; unit mismatch; untraceable granule; fixture token/value leakage; Earth-only; path escape. The constructed (non-NASA) control passes consistency but is correctly **not** NASA-verified |
| Secret scan of composite + backend worktree | 0 findings (scanner positive control detected) |

## P0 blockers

1. **G2 / C1:** no real NASA Earth + Moon/Mars product files committed, so no granule IDs or raw checksums to verify. `tests/acceptance/provenance_check.py --refetch` is ready and is the only thing that can prove NASA origin. Heads-up: C1's `srtm.py` references `step.esa.int`, which is not a NASA host and FAILs the check.
2. **G2 / C2:** no `twinsite.science.analyze`. C3 correctly uses the ARES reference engine for synthetic input only and fails measured runs, so no measured score can exist yet.
3. **G1 / C4:** no committed frontend and no lockfile, so submission → actual result page → SYNTHETIC banner is unverified.
4. **Deployment (user-owned):** no host, access or explicit OK to deploy publicly, so there is no public URL.

## P1 / needs C0 ruling

- C3 committed `API_STATUS.md`, `backend/tests/**` outside its `lanes.json` paths (the kit asked for API_STATUS). C0 should decide.
- Deployment depends on `references/extracted/` (gitignored) for the synthetic engine. The server needs `make bootstrap`.
- C0's own `twinsite_api_smoke` check targets whatever listens on :8080 (possibly another lane's dev server). C5 runs the same `smoke.py` against a stack it boots itself.
- External-AI consent tests cannot run yet: AI routes are absent (404). Current behaviour is the safe default: no route, no transmission. Retest per-provider opt-in and the audit record when C3 adds AI.

## Unresolved provenance gaps

All of them: there are no measured observations, assets or refetch results. Every displayed number is SYNTHETIC.

## Request to C0

Please add a root target (C0 owns the Makefile):

```make
verify:
	ops/verify.sh
```

## Files (lane/qa)

`ops/assemble.py`, `ops/verify.sh`, `ops/secret_scan.py`, `tests/acceptance/http_contract.py`, `tests/acceptance/provenance_check.py`, `tests/acceptance/test_provenance_check.py`, `tests/e2e/run_stack.py`, `docs/release/{QA_STATUS,DEPLOYMENT,DEMO_CHECKLIST}.md`

## Next gate

When C1 commits a measured pair: run `TWINSITE_G2_EVIDENCE=… TWINSITE_G2_ARTIFACT_ROOT=… TWINSITE_G2_REFETCH=1 ops/verify.sh`. When C4 commits: rerun verify (build + SPA routes). Re-scan with `git log main..lane/*`.
