"""TwinSite Simple Analysis engine (lane C2): deterministic, no AI, no network.

Public entry point for the backend lane (C3)::

    from twinsite.science import analyze_mission

    out = analyze_mission(request, evidence=observations, mode="strict")
    out["result"]            # exact contracts/v1/mission_result.schema.json payload
    out["science_evidence"]  # C2-owned fields of contracts/v1/release_evidence.schema.json
    out["annotations"]       # strengths/weaknesses, gates, sensitivity, Pareto, temporal
                             # (NOT a frozen contract; see docs/status/SCIENCE_STATUS.md contract requests)

Scores are engineering similarity heuristics with missing-evidence bounds; they
are never calibrated probabilities or confidence intervals.
"""
from __future__ import annotations

from .version import ENGINE_VERSION, LEGACY_ALGORITHM_VERSION, WEIGHTS_VERSION  # noqa: F401
from .registry import FeatureDefinition, default_registry  # noqa: F401
from .engine import ScienceError, analyze_mission, canonical_hash  # noqa: F401
