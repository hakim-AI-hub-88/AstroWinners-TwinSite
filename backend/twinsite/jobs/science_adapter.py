"""C2 is the sole production engine; missing C2 fails closed."""
from dataclasses import dataclass
from twinsite.science import analyze_mission, ENGINE_VERSION
from twinsite.science.core import validate

class ScienceUnavailable(RuntimeError):
    pass

@dataclass(frozen=True)
class Engine:
    name: str
    version: str
    analyze: object
    validate: object
    synthetic_only: bool

def analyze(payload, progress=None):
    if payload.get("data_status") != "synthetic":
        raise ScienceUnavailable("Measured analysis requires server-resolved evidence")
    if progress:
        progress("P30_CLEAN", 0)
        progress("P40_QUALITY", 0)
    output = analyze_mission(payload, mode="exploratory")
    if progress:
        for stage in ("P60_ANALYZE", "P70_PORTFOLIO", "P80_REVIEW"):
            progress(stage, 1)
    return output["result"]

def load_engine(refresh=False):
    return Engine("twinsite.science", ENGINE_VERSION, analyze, validate, False)
