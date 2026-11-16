"""Provider registry: the only adapters C1 publishes for G2.

Deliberately narrow (submission-day slice): one Earth DEM, one Mars DEM.
Entries for other catalogued products are listed as NOT_INTEGRATED so callers
get an explicit refusal instead of a silent gap.
"""
from __future__ import annotations

from typing import Dict, Optional, Type

from .base import AcquisitionError, SourceAdapter
from .mola import MOLAMEGDRAdapter
from .srtm import SRTMGL1Adapter

ADAPTERS: Dict[str, Type[SourceAdapter]] = {
    SRTMGL1Adapter.source_id: SRTMGL1Adapter,
    MOLAMEGDRAdapter.source_id: MOLAMEGDRAdapter,
}

NOT_INTEGRATED = {
    "POWER": "documented public API reachable (HTTP 200 observed) but no adapter/QA implemented for G2",
    "MOD11A2": "requires Earthdata Login (EARTHDATA_TOKEN absent) and validated QC bit decoding",
    "LOLA_GDR": "public PDS archive reachable; adapter not implemented for G2 (Mars chosen as planetary target)",
    "DIVINER": "QA/local-time binning not validated",
    "COPDEM": "account/entitlement required",
}


def get(source_id: str, **kwargs) -> SourceAdapter:
    cls: Optional[Type[SourceAdapter]] = ADAPTERS.get(source_id)
    if cls is None:
        reason = NOT_INTEGRATED.get(source_id, "unknown source")
        raise AcquisitionError(f"source {source_id!r} is not integrated: {reason}", source_id=source_id)
    return cls(**kwargs)


def catalog() -> Dict[str, dict]:
    out = {sid: {"status": "INTEGRATED", **cls().describe()} for sid, cls in ADAPTERS.items()}
    out.update({sid: {"status": "NOT_INTEGRATED", "reason": r} for sid, r in NOT_INTEGRATED.items()})
    return out
