"""Source adapter contracts for the TwinSite data lane (C1).

Standard library only.  SRTM ``.hgt`` and PDS3 ``.IMG`` are raw fixed-layout
binaries, so explicit label-driven decoding is used instead of GDAL/Rasterio
(neither is installed here and PyPI is not reliably reachable); every
assumption a GDAL driver would make implicitly is recorded here as data.

Rules enforced by every adapter:

* values are never fabricated: a missing or masked sample stays missing;
* Earth geodesy (WGS84 / EGM96) and planetary geodesy (IAU spheres, areoid)
  never share a code path that could silently mix them;
* a failed step raises a typed :class:`SourceError` that is preserved in the
  acquisition transcript as evidence.
"""
from __future__ import annotations

import abc
import dataclasses
import datetime as _dt
from typing import Any, Dict, List, Optional, Sequence, Tuple

ADAPTER_VERSION = "twinsite-data/1.0.0"

BODIES = ("Earth", "Moon", "Mars")

#: CRS identifiers accepted per body.  A request in any other CRS is rejected,
#: never re-interpreted.
BODY_CRS = {
    "Earth": ("EPSG:4326",),
    "Mars": ("IAU_2000:49900",),
    "Moon": ("IAU_2000:30100",),
}


# --------------------------------------------------------------------------- errors
class SourceError(Exception):
    """Base class.  ``code`` is stable and appears in transcripts / verdicts."""

    code = "SOURCE_ERROR"

    def __init__(self, message: str, **evidence: Any) -> None:
        super().__init__(message)
        self.evidence = evidence

    def as_record(self) -> Dict[str, Any]:
        return {"code": self.code, "message": str(self), "evidence": {k: str(v) for k, v in self.evidence.items()}}


class InvalidCRSError(SourceError):
    code = "INVALID_CRS"


class BodyMismatchError(SourceError):
    code = "BODY_MISMATCH"


class OutOfFootprintError(SourceError):
    code = "OUT_OF_FOOTPRINT"


class TimeMismatchError(SourceError):
    code = "TIME_MISMATCH"


class TruncatedAssetError(SourceError):
    code = "TRUNCATED_BYTES"


class ChecksumMismatchError(SourceError):
    code = "CHECKSUM_MISMATCH"


class ByteBudgetExceededError(SourceError):
    code = "BYTE_BUDGET_EXCEEDED"


class VerticalDatumError(SourceError):
    code = "VERTICAL_DATUM_MISMATCH"


class ResolutionError(SourceError):
    code = "TARGET_RESOLUTION_FINER_THAN_NATIVE"


class CredentialMissingError(SourceError):
    code = "CREDENTIAL_MISSING"


class AcquisitionError(SourceError):
    code = "ACQUISITION_FAILED"


class DecodeError(SourceError):
    code = "DECODE_FAILED"


class UnapprovedRuleError(SourceError):
    code = "UNAPPROVED_CLEANING_RULE"


# --------------------------------------------------------------------------- value types
@dataclasses.dataclass(frozen=True)
class AOI:
    """Bounded area of interest: (west, south, east, north) in degrees.

    Earth: geodetic WGS84 longitude/latitude (EPSG:4326), east-positive -180..180.
    Mars:  planetocentric latitude, east-positive longitude (IAU 2000); the
    -180..180 and 0..360 conventions are both accepted and normalised by the
    Mars adapter, never by an Earth code path.
    """

    body: str
    west: float
    south: float
    east: float
    north: float
    crs: str

    def __post_init__(self) -> None:
        if self.body not in BODIES:
            raise BodyMismatchError(f"unknown body {self.body!r}", body=self.body)
        if self.crs not in BODY_CRS[self.body]:
            raise InvalidCRSError(
                f"CRS {self.crs!r} is not an accepted {self.body} CRS {BODY_CRS[self.body]}",
                body=self.body,
                crs=self.crs,
            )
        vals = (self.west, self.south, self.east, self.north)
        if any(not isinstance(v, (int, float)) or v != v or abs(v) == float("inf") for v in vals):
            raise InvalidCRSError("AOI coordinates must be finite numbers", bbox=vals)
        if not (-90.0 <= self.south < self.north <= 90.0):
            raise OutOfFootprintError("AOI latitude range is invalid", south=self.south, north=self.north)
        if not self.west < self.east:
            raise OutOfFootprintError("AOI must have west < east (no antimeridian wrap)", west=self.west, east=self.east)
        if not (-180.0 <= self.west and self.east <= 360.0):
            raise OutOfFootprintError("AOI longitude out of range", west=self.west, east=self.east)

    @property
    def bbox(self) -> List[float]:
        return [self.west, self.south, self.east, self.north]


@dataclasses.dataclass(frozen=True)
class TimeWindow:
    start: _dt.datetime
    end: _dt.datetime

    def overlaps(self, other: "TimeWindow") -> bool:
        return self.start <= other.end and other.start <= self.end


def parse_utc(text: str) -> _dt.datetime:
    text = text.strip().rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return _dt.datetime.strptime(text, fmt).replace(tzinfo=_dt.timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"unparseable UTC time {text!r}")


def iso_utc(value: _dt.datetime) -> str:
    return value.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclasses.dataclass(frozen=True)
class Candidate:
    """One way to obtain a file: a URL plus an optional byte-range plan."""

    url: str
    role: str  # "data", "label", "count", ...
    filename: str
    requires_credential: Optional[str] = None  # env var NAME, never a value
    ranges: Optional[Tuple[Tuple[int, int], ...]] = None  # inclusive (first, last) byte offsets
    expected_bytes: Optional[int] = None
    note: str = ""


@dataclasses.dataclass(frozen=True)
class Granule:
    source_id: str
    product_id: str
    product_version: str
    granule_id: str
    body: str
    footprint: Tuple[float, float, float, float]  # west, south, east, north (native convention)
    observation: TimeWindow
    candidates: Tuple[Candidate, ...]
    license_url: str
    crs: str
    coordinate_conventions: str
    catalog_evidence: Dict[str, Any] = dataclasses.field(default_factory=dict, compare=False, hash=False)


@dataclasses.dataclass(frozen=True)
class RawAsset:
    """Immutable original bytes exactly as received, addressed by SHA-256."""

    asset_id: str
    source_id: str
    product_id: str
    product_version: str
    granule_id: str
    body: str
    role: str
    source_url: str
    object_key: str  # relative to the artifact root
    path: str  # absolute local path (private; never exported)
    sha256: str
    byte_size: int
    retrieved_at: str
    observation: TimeWindow
    fmt: str
    crs: str
    coordinate_conventions: str
    license_url: str
    byte_ranges: Optional[Tuple[Tuple[int, int], ...]] = None
    parent_asset_ids: Tuple[str, ...] = ()
    from_cache: bool = False


@dataclasses.dataclass
class Grid:
    """North-up regular lon/lat grid of optional values (row 0 = northernmost).

    ``lat0``/``lon0`` are the coordinates of the *centre* of sample (0, 0).
    ``registration`` is ``"point"`` (SRTM posts) or ``"area"`` (MOLA cell medians).
    """

    nrows: int
    ncols: int
    lat0: float
    lon0: float
    dlat: float  # positive degrees between rows (going south)
    dlon: float  # positive degrees between columns (going east)
    values: List[Optional[float]]
    registration: str

    def at(self, r: int, c: int) -> Optional[float]:
        return self.values[r * self.ncols + c]

    def lat(self, r: int) -> float:
        return self.lat0 - r * self.dlat

    def lon(self, c: int) -> float:
        return self.lon0 + c * self.dlon

    @property
    def n(self) -> int:
        return self.nrows * self.ncols

    def valid_count(self) -> int:
        return sum(1 for v in self.values if v is not None)


@dataclasses.dataclass
class Decoded:
    """Decoded AOI subset in native units (fill already None), before cleaning."""

    granule: Granule
    assets: Tuple[RawAsset, ...]
    aoi: AOI
    grid: Grid
    unit: str
    vertical_datum: str
    horizontal_datum: str
    body_radius_m: float  # radius used for metric distances on THIS body only
    radius_model: str
    native_resolution_m: float
    fill_value: Optional[int]
    fill_count: int
    support: Optional[Grid] = None  # e.g. MOLA shots-per-cell
    notes: List[str] = dataclasses.field(default_factory=list)
    transformations: List[str] = dataclasses.field(default_factory=list)
    stage: str = "decoded"
    quality_flags: List[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(frozen=True)
class Issue:
    code: str
    severity: str  # info | warning | critical
    evidence: Tuple[str, ...]
    rule_id: Optional[str] = None

    def as_record(self) -> Dict[str, Any]:
        return {"code": self.code, "severity": self.severity, "evidence": list(self.evidence), "rule_id": self.rule_id}


@dataclasses.dataclass
class Validation:
    verdict: str  # ACCEPT | REPAIR_ALLOWED | QUARANTINE | INSUFFICIENT
    issues: List[Issue]
    valid_coverage_fraction: float
    metrics: Dict[str, Any]


@dataclasses.dataclass(frozen=True)
class Feature:
    feature_id: str
    value: Optional[float]
    unit: str
    evidence_kind: str
    uncertainty: Dict[str, Any]
    missing_reason: Optional[str]
    definition: str
    detail: Dict[str, Any] = dataclasses.field(default_factory=dict, compare=False, hash=False)


@dataclasses.dataclass
class FeatureSet:
    decoded: Decoded
    analysis_scale_m: float
    cell_size_m: Tuple[float, float]  # (dx, dy) actually used at analysis scale
    valid_coverage_fraction: float
    quality_flags: List[str]
    features: List[Feature]
    transformations: List[str]


# --------------------------------------------------------------------------- adapter interface
class SourceAdapter(abc.ABC):
    """Six-stage adapter.  Stages never mutate earlier-stage artifacts."""

    source_id: str
    body: str
    product_id: str
    product_version: str
    crs: str
    unit: str
    vertical_datum: str
    license_url: str
    doc_url: str
    approved_rules: Tuple[str, ...] = ()

    def check_aoi(self, aoi: AOI) -> None:
        if aoi.body != self.body:
            raise BodyMismatchError(
                f"{self.source_id} serves {self.body}; AOI is for {aoi.body}", adapter=self.source_id, aoi_body=aoi.body
            )
        if aoi.crs != self.crs:
            raise InvalidCRSError(f"{self.source_id} requires CRS {self.crs}; got {aoi.crs}", crs=aoi.crs)

    @abc.abstractmethod
    def discover(self, aoi: AOI, time: Optional[TimeWindow], product: Optional[str] = None) -> List[Granule]:
        """Return granules intersecting the AOI/time or raise a typed error."""

    @abc.abstractmethod
    def acquire(self, granules: Sequence[Granule], byte_budget: int, aoi: Optional[AOI] = None) -> List[RawAsset]:
        """Fetch original bytes within ``byte_budget``; cache hits are verified by SHA-256."""

    @abc.abstractmethod
    def decode(self, assets: Sequence[RawAsset], aoi: AOI, granule: Granule) -> Decoded:
        """Decode the AOI subset using the product's own layout / label."""

    @abc.abstractmethod
    def validate(self, decoded: Decoded) -> Validation:
        """Product-specific QA.  Never repairs."""

    @abc.abstractmethod
    def clean(self, decoded: Decoded, approved_rules: Sequence[str]) -> Decoded:
        """Apply only approved, product-specific masks.  Returns a new object."""

    @abc.abstractmethod
    def features(self, clean: Decoded, scale: float) -> FeatureSet:
        """Summarised numeric features at analysis scale ``scale`` metres."""

    def describe(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "body": self.body,
            "product_id": self.product_id,
            "product_version": self.product_version,
            "crs": self.crs,
            "unit": self.unit,
            "vertical_datum": self.vertical_datum,
            "license_url": self.license_url,
            "doc_url": self.doc_url,
            "approved_rules": list(self.approved_rules),
            "adapter_version": ADAPTER_VERSION,
        }
