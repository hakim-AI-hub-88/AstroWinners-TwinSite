"""Feature registry: what is scientifically comparable before any scoring.

Each definition declares physical quantity, canonical unit, valid bodies,
physical range, whether values are comparable across bodies, spatial/temporal
support and the missingness policy. Values are never converted here: C1 must
deliver canonical units so contribution lineage stays byte-exact
(contracts.validation.measured_release_issues compares values by equality).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Optional, Tuple

from .version import REGISTRY_VERSION

ALL_BODIES = frozenset({"Earth", "Moon", "Mars"})


@dataclass(frozen=True)
class FeatureDefinition:
    feature_id: str
    quantity: str
    unit: str
    valid_bodies: FrozenSet[str]
    physical_range: Tuple[Optional[float], Optional[float]]
    cross_body_comparable: bool
    spatial_support: str
    temporal_support: str  # "static" | "time_series"
    source_product_ids: Tuple[str, ...]
    missingness_policy: str = "null_is_unobserved_never_zero"
    notes: str = ""
    # Known unit spellings that are the SAME unit but a different string. They are
    # still rejected (no silent relabel); the message tells C1 what to emit.
    unit_aliases: FrozenSet[str] = field(default_factory=frozenset)
    # Units of the same quantity that need a conversion C1 must perform upstream.
    convertible_units: FrozenSet[str] = field(default_factory=frozenset)

    def check_value(self, value: float) -> Optional[str]:
        low, high = self.physical_range
        if low is not None and value < low:
            return f"{self.feature_id}={value} below physical minimum {low} {self.unit}"
        if high is not None and value > high:
            return f"{self.feature_id}={value} above physical maximum {high} {self.unit}"
        return None


_TERRAIN = ("SRTMGL1.003", "COPDEM", "MOLA_MEGDR", "LOLA_GDR")

DEFINITIONS = (
    FeatureDefinition("slope_deg", "AOI mean terrain slope at analysis scale", "degree", ALL_BODIES,
                      (0.0, 90.0), True, "AOI block-mean DEM at stated analysis_scale_m", "static", _TERRAIN,
                      notes="Compare only at a common physical analysis scale.",
                      unit_aliases=frozenset({"deg", "degrees"}), convertible_units=frozenset({"radian", "rad"})),
    FeatureDefinition("roughness_m", "AOI mean 3x3 elevation standard deviation", "m", ALL_BODIES,
                      (0.0, 10000.0), True, "AOI block-mean DEM at stated analysis_scale_m", "static", _TERRAIN,
                      unit_aliases=frozenset({"meter", "metre", "meters"}), convertible_units=frozenset({"km", "cm"})),
    FeatureDefinition("local_relief_m", "max-min block-mean elevation within AOI", "m", ALL_BODIES,
                      (0.0, 30000.0), True, "AOI; depends on AOI size", "static", _TERRAIN,
                      notes="Relief is a relative quantity, so datum differences cancel; AOI sizes must match.",
                      unit_aliases=frozenset({"meter", "metre", "meters"}), convertible_units=frozenset({"km"})),
    FeatureDefinition("elevation_m", "absolute elevation", "m", ALL_BODIES, (-12000.0, 30000.0), False,
                      "DEM cell", "static", _TERRAIN,
                      notes="Earth geoid vs Mars areoid vs lunar radius datums are not interchangeable."),
    FeatureDefinition("surface_temperature_day_K", "daytime land/regolith surface temperature", "K", ALL_BODIES,
                      (20.0, 450.0), True, "1 km (MOD11A2) / Diviner bins", "time_series",
                      ("MOD11A2.061", "DIVINER"), convertible_units=frozenset({"degC", "C"})),
    FeatureDefinition("surface_temperature_night_K", "night land/regolith surface temperature", "K", ALL_BODIES,
                      (20.0, 450.0), True, "1 km (MOD11A2) / Diviner bins", "time_series",
                      ("MOD11A2.061", "DIVINER"), convertible_units=frozenset({"degC", "C"})),
    FeatureDefinition("air_temperature_K", "near-surface air temperature", "K", frozenset({"Earth", "Mars"}),
                      (100.0, 340.0), True, "POWER grid cell / MEDA point", "time_series", ("POWER", "MEDA"),
                      convertible_units=frozenset({"degC", "C"})),
)


class FeatureRegistry:
    def __init__(self, definitions=DEFINITIONS, version=REGISTRY_VERSION):
        self.version = version
        self._defs: Dict[str, FeatureDefinition] = {d.feature_id: d for d in definitions}

    def get(self, feature_id: str) -> Optional[FeatureDefinition]:
        return self._defs.get(feature_id)

    def __contains__(self, feature_id: str) -> bool:
        return feature_id in self._defs

    def ids(self):
        return sorted(self._defs)

    def describe(self):
        return [{"feature_id": d.feature_id, "quantity": d.quantity, "unit": d.unit,
                 "valid_bodies": sorted(d.valid_bodies), "physical_range": list(d.physical_range),
                 "cross_body_comparable": d.cross_body_comparable, "spatial_support": d.spatial_support,
                 "temporal_support": d.temporal_support, "source_product_ids": list(d.source_product_ids),
                 "missingness_policy": d.missingness_policy, "notes": d.notes}
                for d in (self._defs[k] for k in self.ids())]


_DEFAULT = FeatureRegistry()


def default_registry() -> FeatureRegistry:
    return _DEFAULT
