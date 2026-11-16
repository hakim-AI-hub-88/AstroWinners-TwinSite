#############################################################################
# DATA HUB SERVICE (bundled datasets: catalogue, metadata, records, cleaning)
#
# Why this file exists:
#   Exposes every dataset shipped in data_ready/ (the pipeline outputs used by
#   the dashboard) through one catalogue, so users can browse, clean, filter
#   and download exactly the data behind the scores. data_ready/ is READ ONLY.
#
# Dataset ids: "<key>.<stage>"
#   key   earth (Atacama zone) | merzouga (second Earth zone) | mars | moon
#   stage processed              ~1 km (Earth) / 0.5 deg (Mars, Moon) cells, physical units
#         processed_normalized   same cells, 0-1 scale
#         harmonized             common ~11 km cells, physical units (explanation role)
#         harmonized_normalized  common ~11 km cells, 0-1 scale shared by all bodies (scoring role)
#
# A dataset whose file is missing (or still downloading: "<file>.part") is
# listed with available=false and a reason; it never breaks the app.
# Frames come from services.data_loader when it already caches them (the same
# objects the analysis uses), otherwise from a small LRU cache here.
#############################################################################
from __future__ import annotations

import gzip
import json
import logging
import re
import os
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from services import cleaning, data_loader
from utils import config

log = logging.getLogger(__name__)

STAGES = {
    "harmonized_normalized": {"title": "Harmonized, normalized (0-1)", "scale": "normalized", "role": "scoring",
                              "description": "Common ~11 km grid, every feature scaled 0-1 with percentiles shared "
                                             "by Earth, Mars and Moon. The similarity engine scores these values."},
    "harmonized": {"title": "Harmonized, physical units", "scale": "physical", "role": "explanation",
                   "description": "Same ~11 km cells in physical units (m, degrees, K). Used to explain results."},
    "processed": {"title": "Processed, physical units", "scale": "physical", "role": "refinement",
                  "description": "Native processing grid of the body pipeline (Earth 0.01 deg ~1 km; Mars / Moon "
                                 "0.5 deg) in physical units. Earth: rover filter and exact point."},
    "processed_normalized": {"title": "Processed, normalized (0-1)", "scale": "normalized", "role": "reference",
                             "description": "Processed grid scaled 0-1 with the body pipeline's normalization."},
}
KEYS = {
    "earth": {"body": "earth", "zone": "atacama", "label": "Atacama Desert (Chile)"},
    "merzouga": {"body": "earth", "zone": "merzouga", "label": "Merzouga - Erg Chebbi (Morocco)"},
    "mars": {"body": "mars", "zone": "global", "label": "Mars (global)"},
    "moon": {"body": "moon", "zone": "global", "label": "Moon (global)"},
}
LICENSE = "NASA data: public domain / open (see source products). TwinSite processing: MIT."
LIMITS = {"json": 5000, "csv": 200_000}
ID_RE = re.compile(r"^[a-z]+\.[a-z_]+$")


class DatasetError(ValueError):
    """Invalid request (400)."""


class DatasetNotFound(LookupError):
    """Unknown dataset id (404)."""


class DatasetUnavailable(RuntimeError):
    """Known dataset whose file is not available (503)."""


#############################################
# PATHS (all derived from utils.config)
#############################################
def _path(key: str, stage: str) -> Path:
    if stage.startswith("harmonized"):
        normalized = stage == "harmonized_normalized"
        if key in ("earth", "mars", "moon"):
            name = (config.DATASET_FILES if normalized else config.PHYSICAL_FILES)[key]
        else:
            name = config.EARTH_ZONES[key]["normalized" if normalized else "physical"]
        return config.HARMONIZED_DATA_DIR / name
    if key == "earth":
        base = config.EARTH_PROCESSED_FILE
    elif key in config.EARTH_ZONES:
        base = Path(config.EARTH_ZONES[key]["processed"])
    else:
        base = config.DATA_READY_DIR / key / "processed" / f"{key}_features.csv"
    return base if stage == "processed" else base.with_name(base.stem + "_normalized.csv")


def file_path(dataset_id: str) -> Path:
    """Path of the bundled file behind a dataset id."""
    return _path(*parse_id(dataset_id))


def _layers_json(key: str, stage: str) -> Path:
    if stage.startswith("harmonized"):
        return config.HARMONIZED_DATA_DIR / f"{key}_harmonized_layers.json"
    return _path(key, "processed").parent / f"{key}_layers.json"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _validation_report() -> dict:
    return _read_json(config.HARMONIZED_DATA_DIR / "validation_report.json")


def _normalization() -> dict:
    return _read_json(config.HARMONIZED_DATA_DIR / "feature_normalization.json")


def dataset_ids() -> list[str]:
    return [f"{k}.{s}" for k in KEYS for s in STAGES]


def parse_id(dataset_id: str) -> tuple[str, str]:
    if not isinstance(dataset_id, str) or not ID_RE.match(dataset_id):
        raise DatasetNotFound(f"Unknown dataset '{dataset_id}'.")
    key, stage = dataset_id.split(".", 1)
    if key not in KEYS or stage not in STAGES:
        raise DatasetNotFound(f"Unknown dataset '{dataset_id}'. See GET /api/data/datasets.")
    return key, stage


def availability(key: str, stage: str) -> tuple[bool, str | None]:
    p = _path(key, stage)
    if p.is_file():
        return True, None
    if p.with_name(p.name + ".part").exists():
        return False, "Download in progress (partial file present)."
    return False, f"File {p.name} not found in DATA_READY_DIR ({config.DATA_READY_DIR})."


@lru_cache(maxsize=64)
def _header(path_str: str, mtime: float) -> list[str]:
    opener = gzip.open if path_str.endswith(".gz") else open
    with opener(path_str, "rt", encoding="utf-8") as fh:
        return fh.readline().strip().split(",")


@lru_cache(maxsize=64)
def _count_rows(path_str: str, mtime: float) -> int:
    """Data rows of an uncompressed CSV (newline count minus header)."""
    n = 0
    with open(path_str, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            n += chunk.count(b"\n")
    return max(n - 1, 0)


def _rows(key: str, stage: str, path: Path) -> int | None:
    if stage.startswith("harmonized"):
        body = (_validation_report().get("bodies") or {}).get(key) or {}
        if body.get("rows_written") is not None:
            return int(body["rows_written"])
    if path.suffix == ".gz":
        return None
    return _count_rows(str(path), path.stat().st_mtime)


#############################################
# CATALOGUE
#############################################
def describe(dataset_id: str) -> dict:
    key, stage = parse_id(dataset_id)
    k, s = KEYS[key], STAGES[stage]
    path = _path(key, stage)
    ok, reason = availability(key, stage)
    layers = _read_json(_layers_json(key, stage))
    entry = {
        "id": dataset_id, "body": k["body"], "zone": k["zone"], "key": key, "stage": stage,
        "title": f"{k['label']} · {s['title']}", "scale": s["scale"], "role": s["role"],
        "description": s["description"], "available": ok, "reason": reason,
        "rows": None, "columns": [], "file": path.name,
        "path": str(path.relative_to(config.DATA_READY_DIR)) if path.is_relative_to(config.DATA_READY_DIR) else path.name,
        "bytes": None, "resolution": layers.get("resolution"), "license": LICENSE,
        "source": sorted({v for v in (layers.get("sources") or {}).values() if v and not v.startswith("MISSING")}),
    }
    if ok:
        st = path.stat()
        entry["bytes"] = int(st.st_size)
        try:
            entry["columns"] = _header(str(path), st.st_mtime)
            entry["rows"] = _rows(key, stage, path)
        except (OSError, ValueError, EOFError) as exc:
            entry.update(available=False, reason=f"File unreadable: {type(exc).__name__}: {exc}")
    return entry


def catalog() -> list[dict]:
    return [describe(i) for i in dataset_ids()]


#############################################
# FRAMES (cached; never modified in place)
#############################################
def _zone_role(key: str, stage: str) -> str | None:
    return {"harmonized_normalized": "normalized", "harmonized": "physical", "processed": "processed"}.get(stage)


def load(dataset_id: str) -> pd.DataFrame:
    key, stage = parse_id(dataset_id)
    ok, reason = availability(key, stage)
    if not ok:
        raise DatasetUnavailable(f"{dataset_id} is not available: {reason}")
    try:
        role = _zone_role(key, stage)
        if key in config.EARTH_ZONES and role:              # same cached frames as the analysis
            return data_loader.load_zone(key, role)
        if key in ("mars", "moon") and stage.startswith("harmonized"):
            return data_loader.LOADERS[key]() if stage == "harmonized_normalized" else data_loader.load_physical(key)
        if key == "earth" and role:
            return data_loader.load_zone(config.DEFAULT_ZONE, role)
        return _load_other(str(_path(key, stage)), dataset_id)
    except (FileNotFoundError, ValueError, OSError, EOFError) as exc:
        raise DatasetUnavailable(f"{dataset_id} could not be read: {exc}") from None


@lru_cache(maxsize=4)
def _load_other(path_str: str, label: str) -> pd.DataFrame:
    return data_loader._read_schema_csv(Path(path_str), label)


#############################################
# INPUT VALIDATION
#############################################
def parse_bbox(raw) -> tuple[float, float, float, float] | None:
    if raw is None or raw == "" or raw == []:
        return None
    parts = raw if isinstance(raw, (list, tuple)) else str(raw).split(",")
    try:
        vals = [float(x) for x in parts]
    except (TypeError, ValueError):
        raise DatasetError("bbox must be minLon,minLat,maxLon,maxLat (numbers)") from None
    if len(vals) != 4 or not all(np.isfinite(vals)):
        raise DatasetError("bbox must be minLon,minLat,maxLon,maxLat (4 finite numbers)")
    w, s, e, n = vals
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise DatasetError("bbox must satisfy -180 <= minLon < maxLon <= 180 and -90 <= minLat < maxLat <= 90")
    return w, s, e, n


def parse_columns(raw, available: list[str]) -> list[str]:
    if raw is None or raw == "" or raw == []:
        return list(available)
    cols = raw if isinstance(raw, (list, tuple)) else str(raw).split(",")
    cols = [str(c).strip() for c in cols if str(c).strip()]
    unknown = [c for c in cols if c not in available]
    if unknown:
        raise DatasetError(f"Unknown columns {unknown}. Available: {available}")
    out = [c for c in config.COORDINATE_COLUMNS if c in available]   # coordinates always included
    return out + [c for c in cols if c not in out]


def parse_int(raw, name: str, default: int, lo: int, hi: int) -> int:
    if raw is None or raw == "":
        return default
    try:
        v = int(raw)
    except (TypeError, ValueError):
        raise DatasetError(f"{name} must be an integer") from None
    if not lo <= v <= hi:
        raise DatasetError(f"{name} must be between {lo} and {hi}")
    return v


def parse_profile(raw) -> str:
    try:
        return cleaning.validate_profile(raw)
    except cleaning.CleaningError as exc:
        raise DatasetError(str(exc)) from None


#############################################
# SELECTION = bbox filter -> cleaning (statistics computed on the selection)
#############################################
def _bbox_filter(df: pd.DataFrame, bbox) -> pd.DataFrame:
    if bbox is None:
        return df
    w, s, e, n = bbox
    lat, lon = df["latitude"].to_numpy(), df["longitude"].to_numpy()
    return df.loc[(lon >= w) & (lon <= e) & (lat >= s) & (lat <= n)]


# Cleaned frames kept in memory. A cleaned full Mars grid is ~90 MB, so small hosts (512 MB) set
# TWINSITE_DATAHUB_CACHE=1 (or 0: recompute every request); default 6.
_SELECT_CACHE = max(0, int(os.environ.get("TWINSITE_DATAHUB_CACHE", "6") or 6))
# Strict / robust cleaning works on a full copy of the selection. On small hosts set
# TWINSITE_CLEAN_MAX_ROWS (e.g. 500000 on 512 MB): larger selections then need a bbox. 0/unset = no limit.
_CLEAN_MAX_ROWS = max(0, int(os.environ.get("TWINSITE_CLEAN_MAX_ROWS", "0") or 0))


@lru_cache(maxsize=_SELECT_CACHE)
def select(dataset_id: str, profile: str = cleaning.DEFAULT_PROFILE, bbox: tuple | None = None):
    """(clean_df, cleaning report) for a dataset, bbox and profile. Cached (results are read-only)."""
    _, stage = parse_id(dataset_id)
    df = _bbox_filter(load(dataset_id), bbox)
    if _CLEAN_MAX_ROWS and profile in ("strict", "robust") and len(df) > _CLEAN_MAX_ROWS:
        raise DatasetError(
            f"'{profile}' cleaning of {len(df):,} rows needs more memory than this server has. Add a bbox "
            f"(west,south,east,north) covering at most {_CLEAN_MAX_ROWS:,} rows, or use the 'raw' or 'standard' "
            "profile for the full dataset (the original file is also downloadable).")
    return cleaning.apply(df, profile, config.FEATURES, STAGES[stage]["scale"])


def records(dataset_id: str, profile: str, bbox, columns: list[str], limit: int, offset: int) -> dict:
    df, report = select(dataset_id, profile, bbox)
    page = df.iloc[offset:offset + limit][columns].copy()
    for c in page.columns:                    # float32 -> shortest decimal (e.g. -23.005, not -23.004999)
        if page[c].dtype == np.float32:
            page[c] = page[c].astype(str).astype(float)
    return {
        "dataset": dataset_id, "total": int(len(df)), "offset": offset, "limit": limit, "columns": columns,
        "bbox": list(bbox) if bbox else None,
        "rows": json.loads(page.to_json(orient="records", double_precision=6)),
        "cleaning": {"profile": profile, "removed": report["rows_removed"], "masked": report["values_masked"],
                     "report": report},
    }


def csv_chunks(df: pd.DataFrame, columns: list[str], chunk: int = 20_000):
    """Generator for a streamed CSV download."""
    yield ",".join(columns) + "\n"
    for i in range(0, len(df), chunk):
        yield df.iloc[i:i + chunk][columns].to_csv(index=False, header=False, lineterminator="\n")


#############################################
# METADATA (column statistics, flags, normalization, provenance)
#############################################
@lru_cache(maxsize=16)
def _stats(dataset_id: str) -> dict:
    df = load(dataset_id)
    cols = {}
    n = len(df)
    for c in df.columns:
        x = df[c]
        nulls = int(x.isna().sum())
        entry = {"name": c, "dtype": str(x.dtype), "units": config.FEATURE_UNITS.get(c, "deg" if c in config.COORDINATE_COLUMNS else ""),
                 "null_pct": round(100 * nulls / n, 3) if n else None, "valid": int(n - nulls)}
        if c != config.QUALITY_COLUMN and n - nulls > 0:
            v = x.to_numpy(dtype=float)
            entry.update(min=_f(np.nanmin(v)), max=_f(np.nanmax(v)), mean=_f(np.nanmean(v)), median=_f(np.nanmedian(v)))
        cols[c] = entry
    flags = cleaning.decode_flags(df[config.QUALITY_COLUMN].fillna(0)) if config.QUALITY_COLUMN in df else {}
    return {"rows": int(n), "columns": list(cols.values()),
            "quality_flags": [{"name": k, "bit": b, "count": flags.get(k, 0),
                               "pct": round(100 * flags.get(k, 0) / n, 2) if n else None,
                               "meaning": cleaning.FLAG_MEANINGS.get(k, "")} for k, b in config.FLAG_BITS.items()]}


def _f(v) -> float | None:
    v = float(v)
    return None if not np.isfinite(v) else float(f"{v:.6g}")


def metadata(dataset_id: str) -> dict:
    entry = describe(dataset_id)
    key, stage = parse_id(dataset_id)
    out = dict(entry)
    layers = _read_json(_layers_json(key, stage))
    body_report = (_validation_report().get("bodies") or {}).get(key) or {}
    out["provenance"] = {
        "feature_sources": layers.get("sources") or {},
        "processing_steps": layers.get("steps") or body_report.get("processing_steps") or [],
        "notes": layers.get("notes") or body_report.get("notes") or [],
        "pipeline_report": "data_ready/harmonized/validation_report.md",
        "products": [p for p in bundled_products() if p["body"] == key],
    }
    out["normalization"] = ({"method": "x' = clip((x - lo) / (hi - lo), 0, 1); lo/hi = joint percentiles of "
                                       "Earth, Mars and Moon (feature_normalization.json)",
                             "params": _normalization()} if stage == "harmonized_normalized" else
                            {"method": "body pipeline normalization (0-1)"} if stage == "processed_normalized" else None)
    out["features"] = [{"name": f, "units": config.FEATURE_UNITS.get(f, ""),
                        "used_in_similarity": f in config.SIMILARITY["weights"] and f not in config.SIMILARITY["excluded"],
                        "weight": config.SIMILARITY["weights"].get(f)} for f in config.FEATURES]
    out["limits"] = {"json_rows_per_page": LIMITS["json"], "csv_rows_per_download": LIMITS["csv"]}
    if entry["available"]:
        try:
            out.update(_stats(dataset_id))
        except DatasetUnavailable as exc:
            out.update(available=False, reason=str(exc))
    return out


#############################################
# SOURCES (bundled products from data_ready/README.md)
#############################################
@lru_cache(maxsize=1)
def _readme_products(path_str: str, mtime: float) -> list[dict]:
    rows = []
    for line in Path(path_str).read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 7 or cells[0] in ("Body", "") or set(cells[0]) <= {"-", ":"}:
            continue
        body, name, source, fmt, res, purpose, status = cells
        if body not in KEYS:
            continue
        rows.append({"body": body, "dataset": name, "provider": source, "format": fmt, "resolution": res,
                     "purpose": purpose, "status": status})
    return rows


def bundled_products() -> list[dict]:
    p = config.DATA_READY_DIR / "README.md"
    if not p.is_file():
        return []
    return _readme_products(str(p), p.stat().st_mtime)
