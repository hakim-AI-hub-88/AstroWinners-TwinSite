"""Terrain feature math on north-up lon/lat grids (standard library only).

Metric cell sizes are computed by the *caller's* body model and passed in, so
this module cannot mix Earth ellipsoid and Mars/Moon sphere geodesy.

Definitions (stable; versioned by ``TERRAIN_METHOD_VERSION``):

* aggregation: non-overlapping block mean of an integer number of native
  samples per axis chosen so that the block size is the closest achievable to
  the requested analysis scale but never finer than native.  A block is valid
  only if *every* member sample is valid -- no gap filling.
* slope: Horn (1981) 3x3 finite difference on the aggregated grid,
  ``atan(sqrt(dzdx^2 + dzdy^2))`` in degrees; a cell needs all 8 neighbours valid.
* roughness_m: standard deviation of elevation in the 3x3 aggregated
  neighbourhood (population SD), averaged over cells with all 9 values valid.
* local_relief_m: max - min of valid aggregated elevations within the AOI.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from twinsite.sources.base import Grid, ResolutionError

TERRAIN_METHOD_VERSION = "terrain/1.0.0 (block-mean, Horn-1981 slope, 3x3 SD roughness)"


def choose_block(native_dx_m: float, native_dy_m: float, scale_m: float) -> Tuple[int, int]:
    """Integer block (rows, cols) whose size is closest to ``scale_m``.

    Raises :class:`ResolutionError` when the requested scale is finer than the
    coarser native axis (we cannot invent sub-native detail).  A 2 % tolerance
    absorbs the latitude dependence of longitude spacing.
    """
    if scale_m <= 0 or math.isnan(scale_m):
        raise ResolutionError("analysis scale must be positive", scale_m=scale_m)
    native = max(native_dx_m, native_dy_m)
    if scale_m < native * 0.98:
        raise ResolutionError(
            f"requested analysis scale {scale_m:.1f} m is finer than native {native:.1f} m",
            scale_m=scale_m,
            native_m=native,
        )
    by = max(1, int(round(scale_m / native_dy_m)))
    bx = max(1, int(round(scale_m / native_dx_m)))
    return by, bx


def aggregate(grid: Grid, by: int, bx: int) -> Grid:
    if by == 1 and bx == 1:
        return grid
    nr, nc = grid.nrows // by, grid.ncols // bx
    if nr < 3 or nc < 3:
        raise ResolutionError("AOI too small for a 3x3 neighbourhood at this analysis scale",
                              blocks=f"{nr}x{nc}", block=f"{by}x{bx}")
    out: List[Optional[float]] = []
    for R in range(nr):
        for C in range(nc):
            s = 0.0
            ok = True
            for r in range(R * by, R * by + by):
                base = r * grid.ncols
                for c in range(C * bx, C * bx + bx):
                    v = grid.values[base + c]
                    if v is None:
                        ok = False
                        break
                    s += v
                if not ok:
                    break
            out.append(s / (by * bx) if ok else None)
    # centre of block (R,C) = mean of member sample centres
    lat0 = grid.lat0 - (by - 1) * grid.dlat / 2.0
    lon0 = grid.lon0 + (bx - 1) * grid.dlon / 2.0
    return Grid(nr, nc, lat0, lon0, grid.dlat * by, grid.dlon * bx, out, "area")


def _percentile(sorted_vals: Sequence[float], q: float) -> float:
    if not sorted_vals:
        raise ValueError("empty")
    k = (len(sorted_vals) - 1) * q
    f, c = math.floor(k), math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def summarize(vals: Sequence[float]) -> dict:
    s = sorted(vals)
    n = len(s)
    if n == 0:
        return {"n": 0}
    mean = sum(s) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in s) / n)
    return {
        "n": n,
        "mean": mean,
        "sd": sd,
        "min": s[0],
        "p10": _percentile(s, 0.10),
        "median": _percentile(s, 0.50),
        "p90": _percentile(s, 0.90),
        "max": s[-1],
    }


def slope_deg(grid: Grid, dx_of_row: Sequence[float], dy_m: float) -> List[Optional[float]]:
    """Horn slope per interior cell (None at edges / where any neighbour is missing).

    ``dx_of_row[r]`` is the east-west metric spacing at row r (varies with latitude).
    """
    nr, nc = grid.nrows, grid.ncols
    out: List[Optional[float]] = [None] * (nr * nc)
    v = grid.values
    for r in range(1, nr - 1):
        dx = dx_of_row[r]
        for c in range(1, nc - 1):
            a, b, cc = v[(r - 1) * nc + c - 1], v[(r - 1) * nc + c], v[(r - 1) * nc + c + 1]
            d, f = v[r * nc + c - 1], v[r * nc + c + 1]
            g, h, i = v[(r + 1) * nc + c - 1], v[(r + 1) * nc + c], v[(r + 1) * nc + c + 1]
            if None in (a, b, cc, d, f, g, h, i):
                continue
            dzdx = ((cc + 2 * f + i) - (a + 2 * d + g)) / (8.0 * dx)
            # rows increase southwards; dz/dnorth = (top - bottom)
            dzdy = ((a + 2 * b + cc) - (g + 2 * h + i)) / (8.0 * dy_m)
            out[r * nc + c] = math.degrees(math.atan(math.hypot(dzdx, dzdy)))
    return out


def roughness_sd(grid: Grid) -> List[Optional[float]]:
    nr, nc = grid.nrows, grid.ncols
    out: List[Optional[float]] = [None] * (nr * nc)
    v = grid.values
    for r in range(1, nr - 1):
        for c in range(1, nc - 1):
            w = [v[(r + dr) * nc + c + dc] for dr in (-1, 0, 1) for dc in (-1, 0, 1)]
            if None in w:
                continue
            m = sum(w) / 9.0
            out[r * nc + c] = math.sqrt(sum((x - m) ** 2 for x in w) / 9.0)
    return out


def interior_count(grid: Grid) -> int:
    return max(0, grid.nrows - 2) * max(0, grid.ncols - 2)
