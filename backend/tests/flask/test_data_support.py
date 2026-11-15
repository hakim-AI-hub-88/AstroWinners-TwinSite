"""Shared helpers for the data-lane Flask tests (skip cleanly when data files are missing)."""
from __future__ import annotations

import contextlib
import os
import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from utils import config  # noqa: E402  (DATA_READY_DIR must be set before this import)

CUSTOM = "Selected region @ 31.000, -4.000 / 50 km"     # a Merzouga-area point used as stand-in target


def zone_files_present(zone: str) -> bool:
    z = config.EARTH_ZONES[zone]
    return all((config.HARMONIZED_DATA_DIR / z[r]).is_file() for r in ("normalized", "physical")) \
        and Path(z["processed"]).is_file()


def body_files_present(body: str) -> bool:
    return all((config.HARMONIZED_DATA_DIR / f[body]).is_file() for f in (config.DATASET_FILES, config.PHYSICAL_FILES))


def require_zones(*zones):
    missing = [z for z in zones if not zone_files_present(z)]
    if missing:
        raise unittest.SkipTest(f"data_ready files missing for {missing} (set DATA_READY_DIR)")


@contextlib.contextmanager
def merzouga_as_mars():
    """Run 'mars' analyses on the Merzouga harmonized frames so the engine can be exercised even while
    the Mars files are not downloaded. Patches are always restored and the analysis cache cleared."""
    from services import analysis, data_loader
    orig_loader, orig_phys = data_loader.LOADERS["mars"], data_loader.load_physical
    data_loader.LOADERS["mars"] = lambda: data_loader.load_zone("merzouga", "normalized")
    data_loader.load_physical = lambda b: data_loader.load_zone("merzouga", "physical") if b == "mars" else orig_phys(b)
    analysis.run.cache_clear()
    try:
        yield
    finally:
        data_loader.LOADERS["mars"], data_loader.load_physical = orig_loader, orig_phys
        analysis.run.cache_clear()


def app_client():
    os.environ.setdefault("TWINSITE_API_URL", "http://127.0.0.1:9")   # unreachable: live calls must degrade
    from app import create_app
    return create_app(preload=False).test_client()
