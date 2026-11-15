"""C2 Simple Analysis tests. ENGINEERING TESTS ON SYNTHETIC FIXTURES ONLY.

Passing these proves arithmetic, gating, lineage and determinism. It is NOT
scientific validation: no real NASA product pair has been scored yet.
"""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from _fixtures import ROOT, TARGET_ID, build, evidence, sha

from twinsite.science import ScienceError, analyze_mission, canonical_hash
from twinsite.science.engine import with_exclusions

EXAMPLES = ROOT / "contracts" / "examples"
FIXTURES = ("mission", "moon_mission", "three_body_mission", "zone_mission")
try:
    from contracts.validation import validate as schema_validate
    import jsonschema  # noqa: F401
    HAVE_JSONSCHEMA = True
except Exception:  # pragma: no cover - depends on interpreter
    HAVE_JSONSCHEMA = False


def run(request, records=None, mode="strict", runs=20):
    return analyze_mission(request, evidence=records, mode=mode, sensitivity_runs=runs)


class FrozenFixtureCompatibility(unittest.TestCase):
    def test_reproduces_frozen_synthetic_results(self):
        for name in FIXTURES:
            request = json.loads((EXAMPLES / f"{name}.synthetic.json").read_text())
            expected = json.loads((EXAMPLES / f"{name}.result.synthetic.json").read_text())
            result = run(request, mode="exploratory", runs=50)["result"]
            self.assertEqual(set(result), set(expected), name)
            for key in expected:
                if key in ("algorithm_version", "limitations"):
                    continue  # intentionally re-versioned; see SCIENCE_STATUS.md
                self.assertEqual(result[key], expected[key], f"{name}:{key}")

    def test_synthetic_fixture_strict_mode_blocks(self):
        request = json.loads((EXAMPLES / "moon_mission.synthetic.json").read_text())
        out = run(request, mode="strict")
        ev = out["science_evidence"]
        self.assertEqual(ev["strict_gate_status"], "BLOCK")
        self.assertEqual(ev["release_action"], "BLOCK")
        self.assertIn("SYNTHETIC_OR_UNVERIFIED_DATA", ev["blocking_issues"])
        self.assertIn("UNREGISTERED_FEATURE:dry_fraction", ev["blocking_issues"])
        self.assertEqual(out["result"]["status"], "no_feasible_portfolio")


@unittest.skipUnless(HAVE_JSONSCHEMA, "jsonschema not installed")
class SchemaConformance(unittest.TestCase):
    def test_outputs_validate_against_frozen_contracts(self):
        request, records = build()
        for r in records:
            schema_validate("evidence_observation", r)
        schema_validate("mission_request", request)
        for mode in ("strict", "exploratory"):
            out = run(request, records, mode=mode)
            schema_validate("mission_result", out["result"])
            sidecar = dict(out["science_evidence"], run_id="run-test", source_snapshot_id="snap-test",
                           source_snapshot_sha256=sha("snap"), assets=[])
            schema_validate("release_evidence", sidecar)
        for name in FIXTURES:
            request = json.loads((EXAMPLES / f"{name}.synthetic.json").read_text())
            schema_validate("mission_result", run(request, mode="exploratory")["result"])


class Ranking(unittest.TestCase):
    def test_easy_ranking_and_hand_calculation(self):
        request, records = build()
        result = run(request, records)["result"]
        ids = [s["id"] for s in result["sites"]]
        self.assertEqual(ids[0], "GOOD")
        good = result["sites"][0]
        expected = 0.5 * (1 - 1 / 10) + 0.3 * (1 - 0.2 / 2) + 0.2 * (1 - 20 / 200)
        self.assertAlmostEqual(good["lower_utility"], expected)
        self.assertAlmostEqual(good["coverage"], 1.0)
        self.assertAlmostEqual(good["upper_utility"], good["lower_utility"])

    def test_negative_control_ranks_last_with_evidence_linked_weaknesses(self):
        request, records = build()
        out = run(request, records)
        result = out["result"]
        self.assertEqual(result["sites"][-1]["id"], "NEG_CONTROL")
        self.assertEqual(result["sites"][-1]["lower_utility"], 0.0)
        top = result["portfolios"][0]["site_ids"]
        self.assertNotIn("NEG_CONTROL", top)
        ann = next(a for a in out["annotations"]["sites"] if a["site_id"] == "NEG_CONTROL")
        self.assertEqual(len(ann["weaknesses"]), 3)
        self.assertEqual(ann["strengths"], [])
        for w in ann["weaknesses"]:
            self.assertEqual(w["evidence_ids"][1], f"ev-target-{w['feature_id']}")
            self.assertTrue(w["evidence_ids"][0].startswith("ev-NEG_CONTROL-"))
        good = next(a for a in out["annotations"]["sites"] if a["site_id"] == "GOOD")
        self.assertEqual(len(good["strengths"]), 3)


class Missingness(unittest.TestCase):
    def test_missing_required_feature_strict_blocks_exploratory_bounds(self):
        request, records = build()
        site = next(s for s in request["sites"] if s["id"] == "GOOD")
        site["observations"]["slope_deg"]["value"] = None
        records = [r for r in records if r["evidence_id"] != "ev-GOOD-slope_deg"]
        for mode in ("strict", "exploratory"):
            out = run(request, records, mode=mode)
            good = next(s for s in out["result"]["sites"] if s["id"] == "GOOD")
            self.assertFalse(good["eligible"], mode)
            self.assertIn("required feature Mars/slope_deg missing", good["failures"])
            self.assertAlmostEqual(good["coverage"], 0.5)
            self.assertLess(good["lower_utility"], good["upper_utility"])
            self.assertAlmostEqual(good["upper_utility"], good["lower_utility"] + 0.5)
            ann = next(a for a in out["annotations"]["sites"] if a["site_id"] == "GOOD")
            self.assertEqual(ann["gates"]["scientific_evidence"], "UNKNOWN")
            gap = ann["gaps"][0]
            self.assertEqual(gap["interpretation"], "missing information, not physical dissimilarity")
            self.assertEqual(ann["weaknesses"], [])  # missing is never reported as mismatch

    def test_missing_target_never_becomes_a_good_match(self):
        request, records = build()
        request["target_profiles"][0]["observations"]["slope_deg"]["value"] = None
        records = [r for r in records if r["evidence_id"] != "ev-target-slope_deg"]
        out = run(request, records)
        self.assertEqual(out["result"]["status"], "no_feasible_portfolio")
        self.assertIn("MISSING_REQUIRED_TARGET_MEASUREMENT:Mars/slope_deg", out["science_evidence"]["blocking_issues"])

    def test_unknown_cost_under_budget_is_not_affordable(self):
        sites = copy.deepcopy(__import__("_fixtures").SITES)
        lon, lat, _c, days, access, values = sites["GOOD"]
        sites["GOOD"] = (lon, lat, None, days, access, values)
        request, records = build(sites=sites, budget=1000)
        out = run(request, records)
        self.assertTrue(all("GOOD" not in p["site_ids"] for p in out["result"]["portfolios"]))
        ann = next(a for a in out["annotations"]["sites"] if a["site_id"] == "GOOD")
        self.assertEqual(ann["gates"]["budget"], "USER_PARAMETER:UNKNOWN")
        self.assertEqual(ann["cost_status"], "unknown")


class EvidenceIntegrity(unittest.TestCase):
    def test_duplicate_evidence_id_rejected(self):
        request, records = build()
        with self.assertRaises(ScienceError):
            run(request, records + [copy.deepcopy(records[0])])

    def test_evidence_reused_for_another_site_is_rejected(self):
        request, records = build()
        site = next(s for s in request["sites"] if s["id"] == "SLOPE_ONLY")
        site["observations"]["slope_deg"] = {"value": 6.0, "unit": "degree", "source_id": "ev-GOOD-slope_deg"}
        out = run(request, records)
        excl = [e for e in out["annotations"]["evidence_exclusions"] if e["location_id"] == "SLOPE_ONLY"]
        self.assertTrue(any("evidence site GOOD != SLOPE_ONLY" in r for e in excl for r in e["reasons"]))
        slope_only = next(s for s in out["result"]["sites"] if s["id"] == "SLOPE_ONLY")
        self.assertFalse(slope_only["eligible"])

    def test_identical_source_bytes_for_two_sites_flagged_non_independent(self):
        request, records = build()
        for r in records:
            if r["evidence_id"] in ("ev-GOOD-slope_deg", "ev-ROUGH_ONLY-slope_deg"):
                r["source_checksum"] = sha("same-tile")
        out = run(request, records)
        self.assertIn(["GOOD", "ROUGH_ONLY"], out["annotations"]["non_independent_evidence_pairs"])

    def test_quarantined_evidence_strict_rejects_exploratory_warns(self):
        request, records = build()
        for r in records:
            if r["evidence_id"] == "ev-GOOD-roughness_m":
                r["qa_status"] = "QUARANTINE"
        strict = run(request, records)
        good = next(s for s in strict["result"]["sites"] if s["id"] == "GOOD")
        self.assertNotIn("Mars/roughness_m", good["contributions"])
        self.assertFalse(good["eligible"])
        explore = run(request, records, mode="exploratory")
        good = next(s for s in explore["result"]["sites"] if s["id"] == "GOOD")
        self.assertIn("Mars/roughness_m", good["contributions"])
        self.assertTrue(any("qa_status QUARANTINE" in w for w in explore["annotations"]["warnings"]))

    def test_value_mismatch_between_request_and_evidence_rejected_in_all_modes(self):
        request, records = build()
        next(s for s in request["sites"] if s["id"] == "GOOD")["observations"]["slope_deg"]["value"] = 5.0
        for mode in ("strict", "exploratory"):
            good = next(s for s in run(request, records, mode=mode)["result"]["sites"] if s["id"] == "GOOD")
            self.assertNotIn("Mars/slope_deg", good["contributions"], mode)

    def test_analysis_scale_mismatch(self):
        request, records = build()
        for r in records:
            if r["evidence_id"] == "ev-GOOD-slope_deg":
                r["analysis_scale_m"] = 1000.0
        good = next(s for s in run(request, records)["result"]["sites"] if s["id"] == "GOOD")
        self.assertNotIn("Mars/slope_deg", good["contributions"])
        explore = run(request, records, mode="exploratory")
        self.assertTrue(any("analysis scale" in w for w in explore["annotations"]["warnings"]))


class ImpossibleInputs(unittest.TestCase):
    def test_non_canonical_unit_rejected_with_hint(self):
        request, records = build()
        request["mission"]["features"]["slope_deg"]["unit"] = "radian"
        for s in request["sites"]:
            s["observations"]["slope_deg"]["unit"] = "radian"
        request["target_profiles"][0]["observations"]["slope_deg"]["unit"] = "radian"
        with self.assertRaisesRegex(ScienceError, "convert upstream"):
            run(request, records)

    def test_mixed_units_rejected(self):
        request, records = build()
        request["sites"][0]["observations"]["roughness_m"]["unit"] = "km"
        with self.assertRaises(ScienceError):
            run(request, records)

    def test_physically_impossible_value_rejected(self):
        request, records = build()
        request["sites"][0]["observations"]["slope_deg"]["value"] = 120.0
        with self.assertRaisesRegex(ScienceError, "physical maximum"):
            run(request, records)

    def test_absolute_elevation_not_comparable_across_bodies(self):
        features = {"elevation_m": (1.0, 500.0, True, "m", "SRTMGL1.003", -2000.0)}
        sites = {"A": (-116.85, 35.15, 1, 1, "pass", {"elevation_m": 100.0})}
        request, records = build(features=features, sites=sites)
        with self.assertRaisesRegex(ScienceError, "not physically comparable"):
            run(request, records)

    def test_nan_rejected(self):
        request, records = build()
        request["sites"][0]["cost"] = float("nan")
        with self.assertRaises(ScienceError):
            run(request, records)


class Portfolios(unittest.TestCase):
    def test_two_site_complementary_portfolio_beats_both_singles(self):
        sites = {k: v for k, v in __import__("_fixtures").SITES.items() if k in ("SLOPE_ONLY", "ROUGH_ONLY")}
        request, records = build(sites=sites, budget=1000)
        out = run(request, records)
        ports = {tuple(p["site_ids"]): p for p in out["result"]["portfolios"]}
        pair = ports[("ROUGH_ONLY", "SLOPE_ONLY")]
        for single in (("ROUGH_ONLY",), ("SLOPE_ONLY",)):
            self.assertGreater(pair["test_coverage_utility"], ports[single]["test_coverage_utility"])
            self.assertGreater(pair["objective"], ports[single]["objective"])
        self.assertEqual(out["result"]["portfolios"][0]["site_ids"], ["ROUGH_ONLY", "SLOPE_ONLY"])
        expected = 0.5 * 1.0 + 0.3 * 1.0 + 0.2 * 1.0
        self.assertAlmostEqual(pair["test_coverage_utility"], expected)
        self.assertEqual(pair["cost"], 450.0)
        ann = out["annotations"]["portfolios"][0]
        self.assertTrue(ann["complementary"])
        self.assertEqual(ann["best_contributor_by_dimension"]["Mars/slope_deg"], "SLOPE_ONLY")
        self.assertEqual(ann["best_contributor_by_dimension"]["Mars/roughness_m"], "ROUGH_ONLY")

    def test_budget_site_count_and_pareto(self):
        request, records = build(budget=500, max_sites=2)
        out = run(request, records)
        for p in out["result"]["portfolios"]:
            self.assertLessEqual(p["cost"], 500)
            self.assertLessEqual(len(p["site_ids"]), 2)
        front = out["annotations"]["pareto_alternatives"]["science_front"]
        self.assertTrue(front)
        utilities = [p["test_coverage_utility"] for p in out["result"]["portfolios"]]
        self.assertEqual(front[0]["test_coverage_utility"], max(utilities))

    def test_redundant_identical_sites_penalized(self):
        sites = copy.deepcopy(__import__("_fixtures").SITES)
        sites["GOOD_TWIN"] = sites["GOOD"]
        request, records = build(sites=sites)
        out = run(request, records)
        pair = next(p for p in out["result"]["portfolios"] if p["site_ids"] == ["GOOD", "GOOD_TWIN"])
        self.assertGreater(pair["redundancy"], 0.8)
        single = next(p for p in out["result"]["portfolios"] if p["site_ids"] == ["GOOD"])
        self.assertLess(pair["objective"], single["objective"])

    def test_alternatives_exclude_prior_portfolio(self):
        request, records = build()
        first = run(request, records)["result"]["portfolios"][0]["site_ids"]
        second = run(with_exclusions(request, [first]), records)["result"]
        self.assertTrue(all(p["site_ids"] != first for p in second["portfolios"]))

    def test_unknown_access_never_passes(self):
        sites = copy.deepcopy(__import__("_fixtures").SITES)
        lon, lat, c, d, _a, v = sites["GOOD"]
        sites["GOOD"] = (lon, lat, c, d, "unknown", v)
        request, records = build(sites=sites)
        out = run(request, records)
        good = next(s for s in out["result"]["sites"] if s["id"] == "GOOD")
        self.assertFalse(good["eligible"])
        self.assertIn("access status unknown", good["failures"])


class Robustness(unittest.TestCase):
    def test_one_at_a_time_weight_sensitivity(self):
        request, records = build()
        sens = run(request, records)["annotations"]["sensitivity"]
        self.assertEqual(len(sens["scenarios"]), 6)
        self.assertEqual({s["weight_factor"] for s in sens["scenarios"]}, {0.8, 1.2})
        self.assertEqual(sens["site_rank_range"]["NEG_CONTROL"], [4, 4])
        self.assertTrue(sens["top_portfolio_stable"])

    def test_leave_one_source_out(self):
        request, records = build()
        loso = run(request, records)["annotations"]["leave_one_source_out"]
        self.assertEqual(loso["status"], "evaluated")
        by_product = {r["excluded_source_product"]: r for r in loso["runs"]}
        self.assertEqual(set(by_product), {"SRTMGL1.003", "MOLA_MEGDR"})
        # Removing the only Mars product removes all target evidence: nothing qualifies.
        self.assertEqual(by_product["MOLA_MEGDR"]["eligible_site_ids"], [])
        self.assertFalse(by_product["MOLA_MEGDR"]["claims_survive"])

    def test_temporal_windows_only_with_real_time_series(self):
        request, records = build()
        self.assertEqual(run(request, records)["annotations"]["temporal"]["status"], "not_available")
        extra = evidence("ev-GOOD-slope_deg-2019", "slope_deg", "GOOD", "Earth", 9.0, "degree", "SRTMGL1.003",
                         period=("2019-01-01T00:00:00Z", "2019-12-31T23:59:59Z"))
        temporal = run(request, records + [extra])["annotations"]["temporal"]
        self.assertEqual(temporal["status"], "evaluated")
        window = temporal["windows"][0]
        self.assertEqual(len(window["periods"]), 2)
        self.assertEqual(window["best_historical_period"]["start"], "2020-01-01T00:00:00Z")

    def test_unregistered_feature_strict_blocks_exploratory_warns(self):
        features = dict(__import__("_fixtures").FEATURES)
        features["dust_index"] = (0.1, 1.0, False, "1", "FIXTURE", 0.5)
        sites = {k: (lo, la, c, d, a, dict(v, dust_index=0.4)) for k, (lo, la, c, d, a, v) in __import__("_fixtures").SITES.items()}
        request, records = build(features=features, sites=sites)
        strict = run(request, records)["science_evidence"]
        self.assertIn("UNREGISTERED_FEATURE:dust_index", strict["blocking_issues"])
        self.assertEqual(strict["strict_gate_status"], "BLOCK")
        explore = run(request, records, mode="exploratory")
        self.assertTrue(any("dust_index" in w for w in explore["annotations"]["warnings"]))


class Reproducibility(unittest.TestCase):
    def test_same_input_same_output_and_hash(self):
        request, records = build()
        a = run(request, records, runs=50)
        b = run(copy.deepcopy(request), copy.deepcopy(records), runs=50)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        self.assertEqual(a["result"]["input_sha256"], canonical_hash(request))
        self.assertEqual(a["result"]["sensitivity"]["seed"], 20261114)
        self.assertEqual(a["result"]["algorithm_version"], "twinsite-science/0.1.0")

    def test_input_not_mutated(self):
        request, records = build()
        before = json.dumps([request, records], sort_keys=True)
        run(request, records)
        self.assertEqual(before, json.dumps([request, records], sort_keys=True))

    def test_weight_change_keeps_evidence_identical(self):
        request, records = build()
        base = run(request, records)["science_evidence"]["observations"]
        request["mission"]["features"]["slope_deg"]["weight"] = 0.9
        self.assertEqual(base, run(request, records)["science_evidence"]["observations"])


class IntegrationLineage(unittest.TestCase):
    """Run C0's fail-closed measured_release_issues on engine output (engineering fixture)."""

    def test_contribution_lineage_passes_integration_checks(self):
        from contracts.validation import digest, measured_release_issues
        request, records = build()
        out = run(request, records)
        self.assertEqual(out["science_evidence"]["strict_gate_status"], "PASS")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            assets, seen = [], set()
            for r in out["science_evidence"]["observations"]:
                for aid in r["source_asset_ids"]:
                    if aid in seen:
                        continue
                    seen.add(aid)
                    data = f"{r['source_product']}:{r['site_id']}".encode()
                    (root / aid).write_bytes(data)
                    digest_hex = hashlib.sha256(data).hexdigest()
                    self.assertEqual(digest_hex, r["source_checksum"])
                    assets.append({"asset_id": aid, "sha256": digest_hex, "byte_size": len(data), "object_key": aid,
                                   "source_url": r["source_url"], "product_id": r["source_product"], "body": r["body"]})
            pinned = sorted([{"asset_id": a["asset_id"], "sha256": a["sha256"]} for a in assets], key=lambda a: a["asset_id"])
            manifest = dict(out["science_evidence"], assets=assets, source_snapshot_sha256=digest(pinned))
            issues = measured_release_issues(request, out["result"], manifest, root)
        self.assertEqual(set(issues), {"QA_GATE_NOT_PASSED", "MISSING_OR_BLOCKED_REVIEW"}, issues)


if __name__ == "__main__":
    unittest.main()
