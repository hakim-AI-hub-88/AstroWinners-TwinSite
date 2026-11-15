# 30-second demo shot checklist (C5)

Rule: **record only what works live, and show real provenance on screen.** If G2 is not passed, the video must show the SYNTHETIC banner and must not narrate measured science.

| t | Shot | Must be visible (capture proof) | Verify before recording |
| --- | --- | --- | --- |
| 0–5s | Problem statement over the landing page `/` | — | `/` loads without sign-in |
| 5–12s | `/workspace`: pick a Moon/Mars target and objective, then click **Run** | Real target name; P00→P90 phase events from `/v1/missions/{run_id}/events` (actual events, no percentage animation) | `http_contract.py` events check PASS |
| 12–19s | `/analysis/:runId`: ranked Earth candidates | One strength, one weakness, **one rejected/unknown**; spatial scale (m) and observation dates | evidence `release_action` is not BLOCK, or the banner says SYNTHETIC/INSUFFICIENT |
| 19–25s | `/portfolios/:runId`: complementary portfolio; change one weight | Deterministic change; **no new download** in the activity log | G3 alternatives test (not yet implemented: 501) |
| 25–30s | `/data/:datasetId` provenance + report download | **Product/granule ID, source URL host (nasa.gov / PDS), SHA-256 prefix, unit, CRS, time** | `provenance_check.py` on that run: 0 FAIL and `REFETCH_MATCHES_NASA` |

## Provenance capture (attach to the submission)

1. `GET /v1/missions/{run_id}/evidence` → save as `evidence.json`.
2. `python tests/acceptance/provenance_check.py --evidence evidence.json --artifact-root <data root> --result result.json --refetch --json provenance.json`
3. Screenshot the terminal summary line `NASA-origin of bytes VERIFIED by re-download`, plus the UI provenance panel showing the same granule ID and SHA-256 prefix.
4. Record the AI-free proof: `GET /v1/health` showing `"ai_enabled": false` with no provider keys set.

## Do-not-ship list

- Any frame where a synthetic number is presented as a NASA measurement.
- A "complete" claim on a run whose evidence is `BLOCK`.
- Narrating data explorer, uploads or AI features while they return 501 or are disabled.
