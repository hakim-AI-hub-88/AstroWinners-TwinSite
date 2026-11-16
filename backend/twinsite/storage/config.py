"""Runtime configuration from environment variables only. No secret values here."""
import os
from dataclasses import dataclass, field
from pathlib import Path

# backend/twinsite/storage/config.py -> workspace root is parents[3]
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
REFERENCE_ENGINE_RELATIVE = Path('references/extracted/ARES_NASA_Feasibility_Architecture/ARES/implementation')

TRUE = {'1', 'true', 'yes', 'on'}


def _flag(name):
    return os.environ.get(name, '').strip().lower() in TRUE


def _int(name, default, minimum, maximum):
    raw = os.environ.get(name, '').strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    host: str = '127.0.0.1'
    port: int = 8080
    queue_limit: int = 20
    max_attempts: int = 3
    lease_seconds: int = 30
    max_body_bytes: int = 1_000_000
    ai_enabled: bool = False
    uploads_enabled: bool = False
    cors_origins: tuple = field(default_factory=tuple)

    @property
    def db_path(self):
        return self.data_dir / 'twinsite.sqlite'

    @property
    def artifact_root(self):
        return self.data_dir / 'artifacts'


def load_settings(data_dir=None):
    root = Path(data_dir or os.environ.get('TWINSITE_DATA_DIR') or (WORKSPACE_ROOT / '.runtime'))
    origins = os.environ.get('TWINSITE_CORS_ORIGINS', 'http://127.0.0.1:5173,http://localhost:5173')
    return Settings(
        data_dir=root,
        host=os.environ.get('TWINSITE_API_HOST') or '127.0.0.1',
        port=_int('TWINSITE_API_PORT', 8080, 1024, 65535),
        queue_limit=_int('TWINSITE_QUEUE_LIMIT', 20, 1, 20),
        lease_seconds=_int('TWINSITE_LEASE_SECONDS', 30, 2, 600),
        # Legacy field: live AI availability is reported by twinsite.ai (free-provider router), not by this flag.
        ai_enabled=False,
        # Private uploads stay disabled until C3/C5 verify capability isolation.
        uploads_enabled=False,
        cors_origins=tuple(o.strip() for o in origins.split(',') if o.strip()),
    )


def reference_engine_dir():
    """Directory holding the historical ARES `ares` package (synthetic-only fallback)."""
    explicit = os.environ.get('TWINSITE_REFERENCE_ENGINE_DIR')
    if explicit:
        return Path(explicit)
    return WORKSPACE_ROOT / REFERENCE_ENGINE_RELATIVE
