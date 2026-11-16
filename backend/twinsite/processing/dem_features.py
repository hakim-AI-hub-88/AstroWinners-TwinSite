"""Body-agnostic DEM feature extraction; geodesy is injected by the adapter."""
from __future__ import annotations

import math
from typing import Callable, List, Optional

from twinsite.sources.base import Decoded, Feature, FeatureSet, Grid, ResolutionError

from . import terrain

MIN_COVERAGE = 0.65  # below this a feature value is withheld (INSUFFICIENT), never extrapolated


def dem_features(
    clean: Decoded,
    scale_m: float,
    dx_at_lat: Callable[[float, float], float],  # (lat_deg, dlon_deg) -> metres
    dy_at_lat: Callable[[float, float], float],  # (lat_deg, dlat_deg) -> metres
    vertical_uncertainty_note: str,
    support: Optional[Grid] = None,
) -> FeatureSet:
    """``support`` (e.g. MOLA shots per cell) makes the *reported* coverage the
    fraction of analysis blocks containing at least one direct observation.
    Withholding still uses non-fill coverage: interpolated product values are
    product values, but they are never reported as observed support."""
    g = clean.grid
    mid_lat = (g.lat(0) + g.lat(g.nrows - 1)) / 2.0
    ndx, ndy = dx_at_lat(mid_lat, g.dlon), dy_at_lat(mid_lat, g.dlat)
    by, bx = terrain.choose_block(ndx, ndy, scale_m)
    agg = terrain.aggregate(g, by, bx)
    dy = dy_at_lat(mid_lat, agg.dlat)
    dx_rows = [dx_at_lat(agg.lat(r), agg.dlon) for r in range(agg.nrows)]
    cell = (dx_at_lat(mid_lat, agg.dlon), dy)

    transformations = list(clean.transformations) + [
        f"aggregate: block mean {by}x{bx} native samples -> {cell[0]:.1f} m (E-W) x {cell[1]:.1f} m (N-S) "
        f"at lat {mid_lat:.4f}; block valid only if all members valid",
        f"metric spacing from {clean.radius_model}",
        terrain.TERRAIN_METHOD_VERSION,
    ]

    native_cov = g.valid_count() / g.n if g.n else 0.0
    slopes = [s for s in terrain.slope_deg(agg, dx_rows, dy) if s is not None]
    rough = [s for s in terrain.roughness_sd(agg) if s is not None]
    elev = [v for v in agg.values if v is not None]
    interior = terrain.interior_count(agg)
    slope_cov = len(slopes) / interior if interior else 0.0
    coverage = min(native_cov, slope_cov)  # non-fill coverage: governs withholding
    reported = coverage
    flags = list(clean.quality_flags)
    support_frac = None
    if support is not None:
        support_frac = block_support_fraction(support, by, bx)
        reported = min(coverage, support_frac)
        flags.append(f"OBSERVATION_SUPPORTED_BLOCK_FRACTION={support_frac:.3f}")
        transformations.append(
            f"reported valid_coverage_fraction = fraction of {by}x{bx} analysis blocks with >=1 direct observation "
            f"({support_frac:.3f}); non-fill coverage {coverage:.3f}")

    def feat(fid: str, vals: List[float], unit: str, definition: str, cov: float) -> Feature:
        st = terrain.summarize(vals)
        if cov < MIN_COVERAGE or st["n"] == 0:
            return Feature(fid, None, unit, "unavailable",
                           {"kind": "unknown", "low": None, "high": None, "standard_deviation": None,
                            "basis": "value withheld"},
                           f"valid coverage {cov:.3f} below minimum {MIN_COVERAGE}", definition, {"stats": st})
        return Feature(
            fid, round(st["mean"], 4), unit, "derived_measurement",
            {"kind": "interval", "low": round(st["p10"], 4), "high": round(st["p90"], 4), "standard_deviation": None,
             "basis": "10th-90th percentile of per-cell values within the AOI at analysis scale "
                      "(spatial variability, not instrument error). " + vertical_uncertainty_note},
            None, definition, {"stats": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in st.items()},
                               "valid_cells": st["n"], "interior_cells": interior},
        )

    features = [
        feat("slope_deg", slopes, "degree",
             "AOI mean of Horn (1981) 3x3 slope on the block-mean DEM at analysis scale", slope_cov),
        feat("roughness_m", rough, "m",
             "AOI mean of 3x3-neighbourhood elevation standard deviation at analysis scale",
             len(rough) / interior if interior else 0.0),
    ]
    est = terrain.summarize(elev)
    relief_cov = len(elev) / agg.n if agg.n else 0.0
    if relief_cov >= MIN_COVERAGE and est["n"]:
        features.append(Feature(
            "local_relief_m", round(est["max"] - est["min"], 3), "m", "derived_measurement",
            {"kind": "unknown", "low": None, "high": None, "standard_deviation": None,
             "basis": "range statistic; " + vertical_uncertainty_note},
            None, "max - min of block-mean elevation within the AOI at analysis scale",
            {"stats": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in est.items()},
             "vertical_datum": clean.vertical_datum},
        ))
    else:
        features.append(Feature("local_relief_m", None, "m", "unavailable",
                                {"kind": "unknown", "low": None, "high": None, "standard_deviation": None,
                                 "basis": "value withheld"},
                                f"valid coverage {relief_cov:.3f} below minimum {MIN_COVERAGE}",
                                "max - min of block-mean elevation within the AOI at analysis scale"))
    if coverage < MIN_COVERAGE:
        flags.append("INSUFFICIENT_COVERAGE")
    if support_frac is not None and support_frac < MIN_COVERAGE:
        flags.append("LOW_OBSERVATION_SUPPORT")
    return FeatureSet(clean, float(scale_m), (round(cell[0], 3), round(cell[1], 3)), round(reported, 6),
                      flags, features, transformations)


def block_support_fraction(support: Grid, by: int, bx: int) -> float:
    """Fraction of complete by x bx blocks containing at least one cell with support > 0."""
    nr, nc = support.nrows // by, support.ncols // bx
    if nr == 0 or nc == 0:
        return 0.0
    ok = 0
    for R in range(nr):
        for C in range(nc):
            if any((support.at(r, c) or 0) > 0 for r in range(R * by, R * by + by) for c in range(C * bx, C * bx + bx)):
                ok += 1
    return ok / (nr * nc)
