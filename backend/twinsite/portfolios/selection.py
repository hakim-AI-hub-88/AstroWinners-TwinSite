"""Exact portfolio enumeration, complementarity reward, redundancy penalty, Pareto.

`portfolio_result`/`optimize` are an arithmetic port of ARES 0.4.0 so frozen
fixtures reproduce. A dimension no member observed counts as 0 in the legacy
`test_coverage_utility` (a conservative LOWER bound, not a dissimilarity claim);
`annotate_portfolio` separates unobserved from observed-low and adds an upper bound.

Hard constraints are applied before ranking: eligibility (scientific + access),
max site count, user budget and user max_days. Unknown cost/duration under a
user budget/limit makes the portfolio infeasible (never assumed affordable);
without a budget, unknown cost stays `null` and operational status `unknown`.
"""
from __future__ import annotations

import itertools
import math


def portfolio_result(group, mission, weights):
    costs = [site["cost"] for site in group]
    days = [site["days"] for site in group]
    cost = math.fsum(costs) if all(value is not None for value in costs) else None
    duration = math.fsum(days) if all(value is not None for value in days) else None
    if mission.get("budget") is not None and (cost is None or cost > mission["budget"]):
        return None
    if mission.get("max_days") is not None and (duration is None or duration > mission["max_days"]):
        return None
    dimensions = {name: max(site["contributions"].get(name, {}).get("similarity", 0) for site in group)
                  for name in weights}
    utility = math.fsum(weights[name] * value for name, value in dimensions.items())
    pairs = list(itertools.combinations(group, 2))
    overlap = 0.0
    for left, right in pairs:
        overlap += math.fsum(weights[name] * min(left["contributions"].get(name, {}).get("similarity", 0),
                                                 right["contributions"].get(name, {}).get("similarity", 0))
                             for name in weights)
    redundancy = overlap / len(pairs) if pairs else 0.0
    budget = mission.get("budget")
    normalized_cost = cost / budget if budget and cost is not None else 0.0
    objective = (utility - mission.get("cost_penalty", 0.1) * normalized_cost
                 - mission.get("redundancy_penalty", 0.05) * redundancy)
    status = "pass"
    if cost is None or duration is None or any(site["access"] == "unknown" for site in group):
        status = "unknown"
    return {"site_ids": sorted(site["id"] for site in group),
            "kind": "standalone" if len(group) == 1 else "combined", "objective": objective,
            "test_coverage_utility": utility, "dimension_coverage": dimensions,
            "redundancy": redundancy, "cost": cost, "days": duration,
            "operational_status": status, "minimum_evidence_coverage": min(site["coverage"] for site in group)}


def optimize(scored, mission, weights):
    """Enumerate every 1..max_sites combination of eligible sites exactly (<=298 for 12 sites)."""
    eligible = [site for site in scored if site["eligible"]]
    excluded = {tuple(sorted(group)) for group in mission.get("exclude_portfolios", [])}
    portfolios = []
    mode = mission.get("portfolio_mode", "both")
    first = 2 if mode == "combined" else 1
    last = 1 if mode == "standalone" else mission["max_sites"]
    for size in range(first, min(last, len(eligible)) + 1):
        for group in itertools.combinations(eligible, size):
            result = portfolio_result(group, mission, weights)
            if result is not None and tuple(result["site_ids"]) not in excluded:
                portfolios.append(result)
    return sorted(portfolios, key=lambda item: (-item["objective"], tuple(item["site_ids"])))


def annotate_portfolio(portfolio, scored_by_id, weights, shared_evidence_pairs=()):
    """Missing-vs-dissimilar breakdown and an optimistic upper bound for one portfolio."""
    members = [scored_by_id[i] for i in portfolio["site_ids"]]
    dims = {}
    upper = 0.0
    for name in sorted(weights):
        observed = [m["contributions"][name]["similarity"] for m in members if name in m["contributions"]]
        unobserved_by = [m["id"] for m in members if name not in m["contributions"]]
        best = max(observed) if observed else None
        if not observed:
            status = "unobserved"
        elif best < 0.25:
            status = "observed_low"
        else:
            status = "observed"
        bound = 1.0 if unobserved_by else best
        upper += weights[name] * bound
        best_site = None
        if observed:
            best_site = sorted((m for m in members if name in m["contributions"]),
                               key=lambda m: (-m["contributions"][name]["similarity"], m["id"]))[0]["id"]
        dims[name] = {"status": status, "best_observed_similarity": best, "best_site_id": best_site,
                      "unobserved_by": unobserved_by}
    contributors = {name: d["best_site_id"] for name, d in dims.items() if d["best_site_id"]}
    complementary = len(set(contributors.values())) > 1
    ids = set(portfolio["site_ids"])
    shared = sorted([list(p) for p in shared_evidence_pairs if set(p) <= ids])
    return {"site_ids": portfolio["site_ids"], "lower_bound_utility": portfolio["test_coverage_utility"],
            "upper_bound_utility": min(1.0, upper), "dimensions": dims,
            "complementary": complementary, "best_contributor_by_dimension": contributors,
            "non_independent_evidence_pairs": shared}


def _dominates(a, b, keys):
    better_or_equal = all(a[k] >= b[k] for k in keys)
    strictly = any(a[k] > b[k] for k in keys)
    return better_or_equal and strictly


def pareto_fronts(portfolios):
    """Non-dominated alternatives. Cost is a dimension only where every member cost is known."""
    rows = [{"site_ids": p["site_ids"], "utility": p["test_coverage_utility"],
             "coverage": p["minimum_evidence_coverage"], "neg_sites": -len(p["site_ids"]),
             "neg_cost": (-p["cost"]) if p["cost"] is not None else None, "cost": p["cost"],
             "objective": p["objective"]} for p in portfolios]
    sci_keys = ("utility", "coverage", "neg_sites")
    science = [r for r in rows if not any(_dominates(o, r, sci_keys) for o in rows if o is not r)]
    known = [r for r in rows if r["neg_cost"] is not None]
    cost_keys = ("utility", "coverage", "neg_sites", "neg_cost")
    costed = [r for r in known if not any(_dominates(o, r, cost_keys) for o in known if o is not r)]
    clean = lambda rs: [{"site_ids": r["site_ids"], "test_coverage_utility": r["utility"],
                         "minimum_evidence_coverage": r["coverage"], "site_count": -r["neg_sites"],
                         "cost": r["cost"], "objective": r["objective"]}
                        for r in sorted(rs, key=lambda r: (-r["utility"], -r["neg_sites"], r["site_ids"]))]
    return {"science_front": clean(science), "cost_known_front": clean(costed),
            "cost_unknown_excluded_from_cost_front": sorted(r["site_ids"] for r in rows if r["neg_cost"] is None)}
