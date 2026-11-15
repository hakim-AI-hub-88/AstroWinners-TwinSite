"""Simple Analysis entry point: analyze_mission(request, evidence, mode).

Deterministic, stdlib-only, no network and no AI. See package docstring for the
output layout and SCIENCE_STATUS.md for the integration contract with C3.
"""
from __future__ import annotations

import copy
import random

from . import core
from .core import canonical_hash
from .evidence import EvidenceError, attest, index_evidence, scales_comparable, shared_source_pairs
from .registry import default_registry
from .version import ENGINE_VERSION, REGISTRY_VERSION, SENSITIVITY_SEED, WEIGHTS_VERSION
from ..portfolios.selection import annotate_portfolio, optimize, pareto_fronts

MODES = ("strict", "exploratory")
STRENGTH_THRESHOLD = 0.75
WEAKNESS_THRESHOLD = 0.25
OAT_FACTORS = (0.8, 1.2)
LEGACY_LIMITATIONS = [
    "Feature tolerances and objective coefficients are scenario assumptions.",
    "Target bodies receive equal total weight, split equally across their reference locations; "
    "portfolios contain Earth analog candidates.",
    "Earth candidate discovery is represented by a supplied shortlist in this sample.",
    "Cost and duration use additive input scenarios.",
    "Missingness bounds and scenario frequency are descriptive indices.",
    "Full sensor processing, field validation and calibrated uncertainty require integration.",
]
PHYSICS_LIMITS = {
    "Moon": ["Earth sites cannot reproduce lunar 1.62 m/s^2 gravity, hard vacuum, or regolith electrostatics.",
             "Lunar day/night thermal cycling (about 29.5 Earth days) is not reproduced by Earth diurnal cycles."],
    "Mars": ["Earth sites cannot reproduce Martian 3.71 m/s^2 gravity or the ~0.6 kPa CO2 atmosphere.",
             "Martian surface radiation and perchlorate chemistry need laboratory or specialist test setups."],
}


class ScienceError(ValueError):
    """Invalid input (field-level). The engine never repairs input silently."""


def analyze_mission(request, evidence=None, mode="strict", sensitivity_runs=50, registry=None):
    if mode not in MODES:
        raise ScienceError("mode must be 'strict' or 'exploratory'")
    strict = mode == "strict"
    registry = registry or default_registry()
    try:
        input_sha256 = canonical_hash(request)
        cleaned, excluded_ids, ledger = core.clean(request)
    except (ValueError, KeyError, TypeError) as exc:
        raise ScienceError(f"invalid mission request: {exc}") from exc
    try:
        by_id = index_evidence(evidence)
    except EvidenceError as exc:
        raise ScienceError(f"invalid evidence: {exc}") from exc

    warnings, blocking = [], []
    unregistered = _check_registry(cleaned, registry, strict, warnings, blocking)
    if strict and cleaned["data_status"] != "measured":
        blocking.append("SYNTHETIC_OR_UNVERIFIED_DATA")

    gated, exclusions, used_records = _gate(cleaned, by_id, strict, unregistered, warnings)

    comparison_input = core.expand_comparisons(gated)
    mission = comparison_input["mission"]
    weights = core.weights_for(mission)
    scored = core.score_all(comparison_input, weights)
    if strict:
        for site in scored:
            for exc in exclusions:
                if exc["location_id"] == site["id"]:
                    site["failures"].append(f"evidence rejected for {exc['feature_id']}: {'; '.join(exc['reasons'])}")
            site["eligible"] = not site["failures"]
    portfolios = optimize(scored, mission, weights)

    # Seeded weight-perturbation sensitivity (identical procedure to ARES 0.4.0).
    rng = random.Random(SENSITIVITY_SEED)
    selection, infeasible = {}, 0
    for _ in range(sensitivity_runs):
        perturbed = {name: weight * rng.uniform(0.8, 1.2) for name, weight in weights.items()}
        total = core.math.fsum(perturbed.values())
        perturbed = {name: weight / total for name, weight in perturbed.items()}
        alternatives_ = optimize(_rescore(comparison_input, perturbed, scored, strict), mission, perturbed)
        if alternatives_:
            key = "|".join(alternatives_[0]["site_ids"])
            selection[key] = selection.get(key, 0) + 1
        else:
            infeasible += 1

    limitations = list(LEGACY_LIMITATIONS)
    limitations.append(f"Analysis mode: {mode}. Similarity scores are engineering heuristics, "
                       "not calibrated probabilities; [lower, upper] utilities are missing-evidence bounds.")
    if cleaned["data_status"] != "measured":
        limitations.append("Input is SYNTHETIC: results are engineering diagnostics, never scientific findings.")
    result = {
        "schema_version": "1.0", "algorithm_version": ENGINE_VERSION, "input_sha256": input_sha256,
        "cleaned_sha256": canonical_hash(cleaned), "data_status": cleaned["data_status"],
        "mission_id": mission["id"], "weights": weights, "transformations": ledger,
        "scope": mission["scope"], "mode": mission["mode"], "start_trigger": mission["start_trigger"],
        "comparison_pairs": [["Earth", body] for body in core.comparison_bodies(mission)],
        "target_profiles": gated["target_profiles"],
        "portfolio_mode": mission.get("portfolio_mode", "both"),
        "standalone_portfolios": [p for p in portfolios if p["kind"] == "standalone"][:10],
        "combined_portfolios": [p for p in portfolios if p["kind"] == "combined"][:10],
        "excluded_outside_scope": excluded_ids,
        "sites": scored, "portfolios": portfolios[:10], "feasible_portfolio_count": len(portfolios),
        "status": "completed" if portfolios else "no_feasible_portfolio",
        "sensitivity": {"seed": SENSITIVITY_SEED, "scenarios": sensitivity_runs, "weight_factor_range": [0.8, 1.2],
                        "top_portfolio_counts": selection, "infeasible_scenarios": infeasible},
        "limitations": limitations,
    }

    scored_by_id = {s["id"]: s for s in scored}
    records_by_site = {}
    for site in scored:
        records_by_site[site["id"]] = [by_id[c["source_id"]] for c in site["contributions"].values()
                                       if c["source_id"] in by_id]
    shared = shared_source_pairs(records_by_site)
    annotations = {
        "engine_version": ENGINE_VERSION, "registry_version": REGISTRY_VERSION, "mode": mode,
        "score_semantics": "s=max(0,1-|x-t|/tolerance); coverage C=sum observed weights; "
                           "lower L=sum w*s; upper U=L+(1-C). Not a probability or confidence interval.",
        "feature_registry": [d for d in registry.describe() if d["feature_id"] in cleaned["mission"]["features"]],
        "unregistered_features": unregistered,
        "warnings": sorted(set(warnings)),
        "evidence_exclusions": exclusions,
        "sites": [_site_annotation(s, mission, exclusions, strict) for s in scored],
        "portfolios": [annotate_portfolio(p, scored_by_id, weights, shared) for p in portfolios[:10]],
        "pareto_alternatives": pareto_fronts(portfolios),
        "non_independent_evidence_pairs": [list(p) for p in shared],
        "sensitivity": _oat_sensitivity(comparison_input, weights, scored, portfolios, strict),
        "leave_one_source_out": _leave_one_source_out(gated, by_id, used_records, scored, portfolios, strict),
        "temporal": _temporal(scored, mission, by_id, strict),
        "physics_limitations": {b: PHYSICS_LIMITS[b] for b in core.comparison_bodies(mission)},
        "release_evidence_fields_owned_by_c3": ["run_id", "source_snapshot_id", "source_snapshot_sha256", "assets"],
    }
    science_evidence = _science_evidence(result, cleaned, mode, blocking, used_records, scored, portfolios, mission)
    return {"result": result, "science_evidence": science_evidence, "annotations": annotations}


def with_exclusions(request, exclude_portfolios):
    """New request for an alternatives run on the same frozen snapshot (no reacquisition)."""
    updated = copy.deepcopy(request)
    prior = updated["mission"].get("exclude_portfolios", [])
    merged = {tuple(sorted(g)) for g in prior} | {tuple(sorted(g)) for g in exclude_portfolios}
    updated["mission"]["exclude_portfolios"] = [list(g) for g in sorted(merged)]
    return updated


# --------------------------------------------------------------------------- helpers

def _check_registry(cleaned, registry, strict, warnings, blocking):
    features = cleaned["mission"]["features"]
    targets = core.comparison_bodies(cleaned["mission"])
    unregistered = []
    for name in sorted(features):
        spec = features[name]
        definition = registry.get(name)
        if definition is None:
            unregistered.append(name)
            if strict:
                blocking.append("UNREGISTERED_FEATURE:" + name)
            else:
                warnings.append(f"feature {name} is not in the registry: comparability unverified")
            continue
        if spec["unit"] != definition.unit:
            hint = ""
            if spec["unit"] in definition.convertible_units:
                hint = " (convert upstream in C1; the engine never converts silently)"
            elif spec["unit"] in definition.unit_aliases:
                hint = f" (emit the canonical spelling '{definition.unit}')"
            raise ScienceError(f"{name}: unit '{spec['unit']}' is not canonical '{definition.unit}'{hint}")
        if not definition.cross_body_comparable:
            raise ScienceError(f"{name} is not physically comparable across bodies: {definition.notes}")
        for body in targets + ["Earth"]:
            if body not in definition.valid_bodies:
                raise ScienceError(f"{name} is not defined for {body}")
        locations = [(s["id"], s["observations"]) for s in cleaned["sites"]]
        locations += [(t["location"]["id"], t["observations"]) for t in cleaned["target_profiles"]]
        for location_id, observations in locations:
            obs = observations.get(name)
            if obs is not None and obs.get("value") is not None:
                problem = definition.check_value(obs["value"])
                if problem:
                    raise ScienceError(f"{location_id}: impossible value: {problem}")
    return unregistered


def _gate(cleaned, by_id, strict, unregistered, warnings):
    """Attest observations against evidence; return a scored-input copy with rejects nulled."""
    gated = copy.deepcopy(cleaned)
    exclusions, used = [], {}
    targets = [(t["location"]["id"], t["body"], t["observations"]) for t in gated["target_profiles"]]
    sites = [(s["id"], "Earth", s["observations"]) for s in gated["sites"]]
    target_records = {}
    for location_id, body, observations in targets + sites:
        for name in sorted(observations):
            obs = observations[name]
            if obs.get("value") is None:
                continue
            reasons = []
            if strict and name in unregistered:
                reasons.append("unregistered feature cannot satisfy strict analysis")
            record, problems, notes = attest(obs, name, location_id, body, by_id, strict)
            reasons.extend(problems)
            warnings.extend(f"{location_id}/{name}: {n}" for n in notes)
            if record is not None and not problems and body == "Earth":
                for (t_id, t_name), t_record in target_records.items():
                    if t_name == name and scales_comparable(record, t_record) is False:
                        msg = (f"analysis scale {record['analysis_scale_m']} m differs from target {t_id} "
                               f"scale {t_record['analysis_scale_m']} m")
                        (reasons if strict else warnings).append(msg if strict else f"{location_id}/{name}: {msg}")
            if reasons:
                obs["value"] = None
                obs["missing_reason"] = "evidence_rejected"
                exclusions.append({"location_id": location_id, "body": body, "feature_id": name,
                                   "source_id": obs["source_id"], "reasons": reasons})
            elif record is not None:
                used[record["evidence_id"]] = record
                if body != "Earth":
                    target_records[(location_id, name)] = record
    return gated, exclusions, used


def _rescore(comparison_input, weights, baseline, strict):
    rescored = core.score_all(comparison_input, weights)
    if strict:
        base = {s["id"]: s for s in baseline}
        for site in rescored:
            extra = [f for f in base[site["id"]]["failures"] if f.startswith("evidence rejected")]
            site["failures"].extend(extra)
            site["eligible"] = not site["failures"]
    return rescored


def _ranks(scored):
    return {s["id"]: i + 1 for i, s in enumerate(scored)}


def _oat_sensitivity(comparison_input, weights, scored, portfolios, strict):
    """One-at-a-time +/-20% per mission feature (all its target criteria), renormalized."""
    mission = comparison_input["mission"]
    base_top = portfolios[0]["site_ids"] if portfolios else None
    base_ranks = _ranks(scored)
    rank_range = {sid: [r, r] for sid, r in base_ranks.items()}
    scenarios, top_counts = [], {}
    feature_ids = sorted({spec["feature_id"] for spec in mission["features"].values()})
    for feature_id in feature_ids:
        for factor in OAT_FACTORS:
            raw = {k: w * (factor if mission["features"][k]["feature_id"] == feature_id else 1.0)
                   for k, w in weights.items()}
            total = core.math.fsum(raw.values())
            perturbed = {k: w / total for k, w in raw.items()}
            rescored = _rescore(comparison_input, perturbed, scored, strict)
            options = optimize(rescored, mission, perturbed)
            top = options[0]["site_ids"] if options else None
            key = "|".join(top) if top else "none"
            top_counts[key] = top_counts.get(key, 0) + 1
            for sid, r in _ranks(rescored).items():
                rank_range[sid] = [min(rank_range[sid][0], r), max(rank_range[sid][1], r)]
            scenarios.append({"feature_id": feature_id, "weight_factor": factor, "top_portfolio": top,
                              "top_changed": top != base_top})
    return {"method": "one-at-a-time weight x0.8 and x1.2 per mission feature, renormalized to sum 1",
            "baseline_top_portfolio": base_top, "scenarios": scenarios, "top_portfolio_counts": top_counts,
            "top_portfolio_stable": all(not s["top_changed"] for s in scenarios),
            "site_rank_range": {sid: rank_range[sid] for sid in sorted(rank_range)}}


def _leave_one_source_out(gated, by_id, used_records, scored, portfolios, strict):
    products = sorted({r["source_product"] for r in used_records.values()})
    if not products:
        return {"status": "not_available", "reason": "no evidence records were attested and scored"}
    base_top = portfolios[0]["site_ids"] if portfolios else None
    base_eligible = sorted(s["id"] for s in scored if s["eligible"])
    runs = []
    for product in products:
        variant = copy.deepcopy(gated)
        removed = 0
        for container in [s["observations"] for s in variant["sites"]] + [t["observations"] for t in variant["target_profiles"]]:
            for obs in container.values():
                record = by_id.get(obs.get("source_id"))
                if record is not None and record["source_product"] == product and obs.get("value") is not None:
                    obs["value"] = None
                    obs["missing_reason"] = "leave_one_source_out"
                    removed += 1
        comparison_input = core.expand_comparisons(variant)
        weights = core.weights_for(comparison_input["mission"])
        rescored = _rescore(comparison_input, weights, scored, strict)
        options = optimize(rescored, comparison_input["mission"], weights)
        top = options[0]["site_ids"] if options else None
        eligible = sorted(s["id"] for s in rescored if s["eligible"])
        runs.append({"excluded_source_product": product, "observations_removed": removed,
                     "top_portfolio": top, "top_changed": top != base_top, "eligible_site_ids": eligible,
                     "eligibility_changed": eligible != base_eligible,
                     "claims_survive": top == base_top and eligible == base_eligible})
    return {"status": "evaluated", "baseline_top_portfolio": base_top, "runs": runs,
            "note": "Removing a product nulls its observations (treated as unobserved, never as zero)."}


def _temporal(scored, mission, by_id, strict):
    series = {}
    for record in by_id.values():
        if record["body"] != "Earth" or record["value"] is None:
            continue
        if strict and (record["qa_status"] != "ACCEPT" or record["data_status"] != "measured"):
            continue
        series.setdefault((record["site_id"], record["feature_id"]), []).append(record)
    site_ids = {s["id"] for s in scored}
    windows = []
    for (site_id, feature_id), records in sorted(series.items()):
        periods = {(r["observation_period"]["start"], r["observation_period"]["end"]) for r in records}
        if site_id not in site_ids or len(periods) < 2:
            continue
        for key, spec in sorted(mission["features"].items()):
            if spec["feature_id"] != feature_id or spec.get("target") is None:
                continue
            rows = []
            for r in sorted(records, key=lambda r: (r["observation_period"]["start"], r["evidence_id"])):
                rows.append({"period": r["observation_period"], "value": r["value"], "unit": r["unit"],
                             "similarity": core.similarity(r["value"], spec["target"], spec["tolerance"]),
                             "valid_coverage_fraction": r["valid_coverage_fraction"],
                             "evidence_id": r["evidence_id"]})
            best = sorted(rows, key=lambda x: (-x["similarity"], x["period"]["start"]))[0]
            windows.append({"site_id": site_id, "criterion": key, "feature_id": feature_id,
                            "target_value": spec["target"], "target_source_id": spec.get("target_source_id"),
                            "periods": rows, "best_historical_period": best["period"]})
    if not windows:
        return {"status": "not_available",
                "reason": "no Earth site has >=2 accepted evidence records of one feature over distinct periods"}
    return {"status": "evaluated", "windows": windows,
            "note": "Historical descriptive windows, not forecasts; no future day is guaranteed to match."}


def _gate_value(value, limit):
    if limit is None:
        return "NOT_CONSTRAINED"
    if value is None:
        return "UNKNOWN"
    return "PASS" if value <= limit else "FAIL"


def _site_annotation(site, mission, exclusions, strict):
    strengths, weaknesses, gaps = [], [], []
    for key in sorted(mission["features"]):
        spec = mission["features"][key]
        c = site["contributions"].get(key)
        if c is None:
            excl = [e for e in exclusions if e["location_id"] in (site["id"], spec["target_location_id"])
                    and e["feature_id"] == spec["feature_id"]]
            if excl:
                reason = "evidence rejected: " + "; ".join(r for e in excl for r in e["reasons"])
            elif spec.get("target") is None:
                reason = "target value unavailable"
            else:
                reason = "no Earth observation"
            gaps.append({"criterion": key, "feature_id": spec["feature_id"], "reason": reason,
                         "required": bool(spec.get("required", False)),
                         "interpretation": "missing information, not physical dissimilarity",
                         "severity": "high" if spec.get("required") else "medium"})
            continue
        item = {"criterion": key, "feature_id": c["feature_id"], "similarity": c["similarity"],
                "site_value": c["value"], "target_value": c["target_value"], "unit": c["unit"],
                "tolerance": spec["tolerance"], "evidence_ids": [c["source_id"], c["target_source_id"]],
                "method": ENGINE_VERSION}
        if c["similarity"] >= STRENGTH_THRESHOLD:
            strengths.append(dict(item, severity="info", statement=(
                f"{c['feature_id']} {c['value']} {c['unit']} is within {abs(c['value'] - c['target_value'])} "
                f"{c['unit']} of the {c['target_body']} target {c['target_value']} {c['unit']}")))
        elif c["similarity"] <= WEAKNESS_THRESHOLD:
            weaknesses.append(dict(item, severity="high" if spec.get("required") else "medium", statement=(
                f"observed mismatch: {c['feature_id']} {c['value']} vs target {c['target_value']} {c['unit']}")))
    required_missing = [g for g in gaps if g["required"]]
    coverage_short = site["coverage"] + 1e-12 < mission["min_coverage"]
    gates = {
        "scientific_evidence": "UNKNOWN" if (required_missing or coverage_short) else "PASS",
        "access": site["access"].upper(),
        "budget": "USER_PARAMETER:" + _gate_value(site["cost"], mission.get("budget")),
        "duration": "USER_PARAMETER:" + _gate_value(site["days"], mission.get("max_days")),
        "required_features": {g["criterion"]: "UNKNOWN" for g in required_missing},
    }
    return {"site_id": site["id"], "eligible": site["eligible"], "gates": gates,
            "lower_utility": site["lower_utility"], "upper_utility": site["upper_utility"],
            "coverage": site["coverage"], "strengths": strengths, "weaknesses": weaknesses, "gaps": gaps,
            "cost_status": "user_supplied" if site["cost"] is not None else "unknown",
            "access_basis": "user/external parameter; never inferred from maps"}


def _science_evidence(result, cleaned, mode, blocking, used_records, scored, portfolios, mission):
    strict = mode == "strict"
    eligible = [s for s in scored if s["eligible"]]
    required_ids = set()
    for site in eligible:
        for key, c in site["contributions"].items():
            if mission["features"][key].get("required"):
                required_ids.update([c["source_id"], c["target_source_id"]])
    blocking = list(blocking)
    if strict:
        for key, spec in sorted(mission["features"].items()):
            if spec.get("required") and spec.get("target") is None:
                blocking.append("MISSING_REQUIRED_TARGET_MEASUREMENT:" + key)
        if not portfolios:
            blocking.append("NO_QUALIFIED_CANDIDATE")
    if strict:
        gate = "PASS" if not blocking and cleaned["data_status"] == "measured" else "BLOCK"
    else:
        gate = "NOT_EVALUATED"
        blocking.append("EXPLORATORY_MODE_NOT_A_SCIENTIFIC_RELEASE")
    if cleaned["data_status"] != "measured" and "SYNTHETIC_OR_UNVERIFIED_DATA" not in blocking:
        blocking.append("SYNTHETIC_OR_UNVERIFIED_DATA")
    unknowns = []
    for site in scored:
        if site["access"] == "unknown":
            unknowns.append(f"access/permission status unknown for site {site['id']}")
        if site["cost"] is None:
            unknowns.append(f"cost unknown for site {site['id']} (not inferred)")
        for key in site["missing"]:
            unknowns.append(f"{key} unobserved for site {site['id']}")
    return {
        "schema_version": "1.0",
        "input_sha256": result["input_sha256"],
        "qa_gate_id": "c2-science-" + mode,
        "qa_gate_version": ENGINE_VERSION,
        "data_status": cleaned["data_status"],
        "strict_gate_status": gate,
        # C2 never authorizes publication: C5 review + C0/C3 decide RELEASE/QUALIFIED_RELEASE.
        "release_action": "BLOCK",
        "weights_version": WEIGHTS_VERSION,
        "evidence_coverage": portfolios[0]["minimum_evidence_coverage"] if portfolios else 0.0,
        "required_evidence_ids": sorted(i for i in required_ids if i in used_records),
        "observations": [used_records[k] for k in sorted(used_records)],
        "rejected_candidates": [{"site_id": s["id"], "reasons": list(s["failures"])} for s in scored if s["failures"]],
        "assumptions": [
            "Feature weights, tolerances and min_coverage are user mission-scenario assumptions (" + WEIGHTS_VERSION + ").",
            "Cost, duration and access/permissions are user-supplied parameters or unknown; never inferred from maps.",
            "Similarity is an engineering heuristic; utility bounds reflect missing evidence only.",
        ],
        "unknowns": unknowns,
        "blocking_issues": sorted(set(blocking)),
        "review_ids": [],
    }
