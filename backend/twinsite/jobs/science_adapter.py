"""Adapter to the deterministic scoring engine. C3 never implements scoring.

Resolution order:
1. C2's library `twinsite.science` if it exposes `analyze(payload, progress=None)`
   (optional `validate(payload)`, `VERSION`/`ALGORITHM_VERSION`).
2. The pinned historical ARES reference engine (`ares.engine`) from the
   extracted reference archive — SYNTHETIC INPUTS ONLY. It is loaded, not copied,
   and is never used for a measured run.
"""
from dataclasses import dataclass
import importlib
import sys
import threading

from twinsite.storage.config import reference_engine_dir


class ScienceUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Engine:
    name: str
    version: str
    analyze: object
    validate: object
    synthetic_only: bool


_lock = threading.Lock()
_cached = None


def _from_c2():
    try:
        module = importlib.import_module('twinsite.science')
    except ImportError:
        return None
    analyze = getattr(module, 'analyze', None)
    if not callable(analyze):
        return None
    validate = getattr(module, 'validate', None)
    version = str(getattr(module, 'ALGORITHM_VERSION', None) or getattr(module, 'VERSION', 'unversioned'))
    return Engine('twinsite.science', version, analyze, validate if callable(validate) else None, False)


def _from_reference():
    folder = reference_engine_dir()
    if not (folder / 'ares' / 'engine.py').is_file():
        return None
    if str(folder) not in sys.path:
        sys.path.append(str(folder))
    engine = importlib.import_module('ares.engine')
    package = importlib.import_module('ares')
    return Engine('ares-reference', str(getattr(package, 'VERSION', 'unknown')), engine.analyze, engine.validate, True)


def load_engine(refresh=False):
    global _cached
    with _lock:
        if _cached is None or refresh:
            _cached = _from_c2() or _from_reference()
        if _cached is None:
            raise ScienceUnavailable('No scoring engine: twinsite.science lacks analyze() and the ARES reference '
                                     'engine is not extracted (run `make bootstrap` or set TWINSITE_REFERENCE_ENGINE_DIR).')
        return _cached


def validate(payload):
    """Cross-field checks beyond JSON Schema. Raises ValueError/KeyError/TypeError."""
    engine = load_engine()
    if engine.validate is not None:
        engine.validate(payload)
