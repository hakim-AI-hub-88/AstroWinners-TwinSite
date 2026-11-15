# SCIENCE_STATUS — lane C2 (TWIN-SCIENCE, Simple Analysis engine)

Lane: C2 · Branch: `lane/science` · Gate: G1 engine ready; **G2 real-science BLOCKED (awaiting C1 real pair)**
Checkpoint: 2026-11-15.

## DONE
- No-AI, stdlib-only, deterministic engine in `backend/twinsite/science/` + exact portfolio enumeration in `backend/twinsite/portfolios/`.
- **Reproduces all four frozen synthetic fixtures exactly** (`contracts/examples/*.result.synthetic.json`) in exploratory mode, except two intentionally changed keys: `algorithm_version` (now `twinsite-science/0.1.0`, tracked) and `limitations` (adds mode + synthetic disclaimers). Scoring arithmetic is a byte-compatible port of ARES 0.4.0.
- Feature registry (`registry.py`): body validity, canonical unit, physical range, cross-body comparability, spatial/temporal support, missingness policy. `slope_deg`, `roughness_m`, `local_relief_m` match C1's feature IDs. `elevation_m` is registered but rejected across bodies (geoid vs areoid datums).
- Evidence intake typed against the frozen `evidence_observation` schema. A request `source_id` must resolve to an `evidence_id` with identical value/unit/feature/body/site; duplicate `evidence_id` = error; identical source bytes for two sites flagged non-independent; analysis-scale mismatch (>10 %) rejected in strict mode.
- Strict vs exploratory modes; missing-evidence bounds `[L,U]` (not confidence intervals); hard gates PASS/FAIL/UNKNOWN (scientific evidence, evidence attestation, access, user budget, user duration); evidence-linked strengths/weaknesses/gaps ("missing information, not physical dissimilarity"); physics limitations per body.
- Sensitivity: seeded (20261114) random ±20 % weights (legacy, in result); one-at-a-time ×0.8/×1.2 per feature with site rank ranges; leave-one-source-out by `source_product`. Temporal windows only when ≥2 accepted records over distinct periods exist, else `not_available`.
- Portfolios: exact enumeration (≤298 combos for 12 sites, max 3); eligibility/site-count/budget/max_days hard constraints; complementarity reward; redundancy penalty; unobserved-vs-observed-low breakdown with upper bound; Pareto fronts (science; cost only where all member costs are known); `with_exclusions` for alternatives on the same snapshot.
- `bridge.request_from_evidence` builds a mission_request verbatim from C1 evidence records.

## ENTRY POINT (for C3)
```python
# PYTHONPATH=backend:.
from twinsite.science import analyze_mission, ScienceError
from twinsite.science.engine import with_exclusions          # alternatives
from twinsite.science.bridge import request_from_evidence     # C1 evidence -> request

out = analyze_mission(request, evidence=list_of_evidence_observations, mode="strict", sensitivity_runs=50)
out["result"]            # exact mission_result (closed schema) -> GET /result
out["science_evidence"]  # release_evidence fields C2 owns; C3 adds run_id, source_snapshot_id,
                         # source_snapshot_sha256, assets; C5/C0 own review_ids and any RELEASE decision
out["annotations"]       # non-contract: gates, pros/cons, Pareto, OAT, leave-one-source-out, temporal
```
- `ScienceError` (a `ValueError`) = field-level invalid input → map to HTTP 422. Never repaired silently.
- `mode="strict"` (default): synthetic data, unregistered features or unattested evidence → `strict_gate_status: BLOCK`, nothing qualifies. Use `mode="exploratory"` **only** for the G1 synthetic smoke; it is always `NOT_EVALUATED` with blocking issue `EXPLORATORY_MODE_NOT_A_SCIENTIFIC_RELEASE`.
- `release_action` is always `BLOCK` from C2; even a strict `PASS` awaits C5 independent review.
- `evidence_coverage` = `minimum_evidence_coverage` of the top portfolio (0 if none).
- Pure function: inputs are not mutated; identical inputs → byte-identical JSON output.

## EVIDENCE CONVENTIONS C1 MUST FOLLOW (strict mode)
- `site_id` == request Earth site `id`, or the target scope location `id` (e.g. `mars-gale-aeolis`).
- `feature_id` registered (`slope_deg`, `roughness_m`, `local_relief_m`) with the exact canonical unit (`degree`, `m`); no conversion in the engine.
- Request `observations[f].source_id` == `evidence_id`, value byte-identical (`request_from_evidence` does this).
- `data_status=measured`, `evidence_kind` direct/derived measurement, `qa_status=ACCEPT`, coverage > 0, resolution and scale present.
- Earth and target `analysis_scale_m` within 10 %.
- One record per (site_id, feature_id) when building a request; several records over distinct periods activate temporal windows.
- A portfolio needs ≥2 Earth candidate sites.

## FILES CHANGED
- `backend/twinsite/science/{__init__,version,scope,core,registry,evidence,engine,bridge}.py`
- `backend/twinsite/portfolios/{__init__,selection}.py`
- `backend/tests/science/{_fixtures,test_engine}.py`
- `SCIENCE_STATUS.md`

## TESTS RUN + RESULTS
Command (from worktree root):
```sh
python3 -m unittest discover -s backend/tests/science -v
```
- System Python 3.9.6: **33 run, 32 passed, 1 skipped** (schema test; jsonschema absent).
- Python 3.13.15 + jsonschema 4.25.1 (scratch venv): **33 run, 33 passed**, including Draft 2020-12 validation of result + sidecar + evidence + request.
- Covered: frozen-fixture reproduction; strict blocks synthetic; easy ranking + hand-calculated score; negative control ranks last with evidence-linked weaknesses; missing required feature (strict blocks / exploratory bounds, gate UNKNOWN); missing target never a good match; unknown cost under budget excluded; duplicate evidence IDs; evidence reused for another site; shared source bytes; quarantined evidence; request/evidence value mismatch; scale mismatch; non-canonical / mixed / impossible units and values; cross-body elevation; NaN; complementary two-site portfolio beats both singles; budget/site-count/Pareto; redundancy penalty; alternatives; unknown access; OAT sensitivity; leave-one-source-out; temporal; unregistered features; reproducibility; no mutation; weight change keeps evidence identical; evidence→request bridge; **C0 `measured_release_issues` on engine output → only `QA_GATE_NOT_PASSED` + `MISSING_OR_BLOCKED_REVIEW`** (expected: no review, release BLOCK).

**ALL OF THE ABOVE ARE ENGINEERING TESTS ON SYNTHETIC FIXTURES** (tagged `SYNTHETIC-ENGINEERING-FIXTURE`). The measured-shaped fixture exists only to exercise the measured lineage path. None of it is scientific validation.

## REAL NASA DATA EVIDENCE
None scored yet. At this checkpoint C1 (`lane/data` @ 1cba3df) has adapters and raw MOLA MEGDR bytes locally, but the SRTMGL1 tile download is incomplete (`.part`) and `processing/published/g2_feature_pair.json` does not exist. **Real-science release is BLOCKED.** No real candidate comparison or real portfolio is claimed.

## BLOCKERS
0. The shared-notes hand-over file was **not written** (blocked by a session permission check). C1's evidence conventions exist only in this file; C0, please forward them to C1.
1. **C1 (high):** no published, QA-accepted Earth + Mars evidence pair yet, so the G2 deliverable (2 real comparisons + 1 portfolio) cannot run. Once C1 publishes ≥2 Earth sites + 1 Mars target at a common analysis scale: `request_from_evidence` → `analyze_mission(mode="strict")`. C1's G2 script currently defines one Earth site; a portfolio needs ≥2.
2. **Environment (low):** system python3 lacks jsonschema; the schema test skips there.

## CONTRACT REQUESTS FOR C0
(Checked: `scripts/integration/smoke.py` compares two fresh C2 runs to each other rather than to the ARES baseline, so the re-versioned `algorithm_version`/`limitations` keys need no contract change.)
1. `annotations` (gates, strengths/weaknesses/gaps, portfolio dimension status + upper bound, Pareto fronts, OAT + leave-one-source-out, temporal windows) has no frozen home because `mission_result` and `release_evidence` are closed. Request a `science_annotations` v1 schema or sidecar route; until then C3 should store it as an opaque artifact and the UI must not treat it as contract.
2. Analysis mode (`strict|exploratory`) is not a request field; C3 passes it as an argument. Request an explicit `analysis_mode` field in a future schema version.
3. `release_evidence.qa_gate_id/qa_gate_version`: C2 fills `c2-science-<mode>` / engine version; confirm ownership.

## NEXT GATE AND INTEGRATION NEEDS
- C3: wire `analyze_mission` into the worker (exploratory for the frozen synthetic smoke, strict for everything else); merge sidecar fields.
- C1: publish evidence per the conventions above.
- C5: independent review + negative controls on real data.

READY FOR MERGE? **YES for the G1 engine (synthetic, fail-closed). NO for any real-science claim.**
