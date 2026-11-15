"""Server-side loader for AI provider credentials.

Source order: process environment (names matching known provider prefixes), then an
owner-only 0600 env file. Default file is .runtime/secrets/ai-providers.env (local dev);
production sets TWINSITE_AI_SECRET_ENV_FILE to a root-provisioned path outside the
deployed tree (e.g. /etc/twinsite/ai-providers.env, owned by the service user, 0600).
Values never leave this process: nothing here logs, prints or serialises them.
"""
import os
import re
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FILE = ROOT / '.runtime' / 'secrets' / 'ai-providers.env'
PREFIXES = ('CLOUDFLARE_API_TOKEN', 'CLOUDFLARE_ACCOUNT_ID', 'GOOGLE_API_KEY', 'GROQ_API_KEY', 'MISTRAL_API_KEY',
            'NVIDIA_NIM_API_KEY', 'OLLAMA_API_KEY', 'OPENROUTER_API_KEY', 'ELEVENLABS_API_KEY')
_LINE = re.compile(r'^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)=(.*)$')


class SecretFileError(RuntimeError):
    pass


def secret_file():
    """Only an explicitly configured file is read, so scrubbed/test environments are hermetic.
    Local dev: TWINSITE_AI_SECRET_ENV_FILE=.runtime/secrets/ai-providers.env (set by `make dev-ai`)."""
    value = os.environ.get('TWINSITE_AI_SECRET_ENV_FILE')
    return Path(value) if value else None


def _wanted(name):
    return any(name.startswith(p) for p in PREFIXES)


def read_env_file(path):
    """Parse an owner-only 0600 regular file (no symlinks). Missing file -> {}."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    except FileNotFoundError:
        return {}
    with os.fdopen(fd) as source:
        st = os.fstat(source.fileno())
        if not stat.S_ISREG(st.st_mode) or stat.S_IMODE(st.st_mode) & 0o077 or st.st_uid != os.getuid():
            raise SecretFileError('AI secret file must be a regular file owned by the service user with mode 0600')
        out = {}
        for line in source:
            match = _LINE.match(line.rstrip('\n'))
            if not match:
                continue
            value = match.group(2).strip().strip('"\'')
            if value and not any(c.isspace() for c in value) and _wanted(match.group(1)):
                out[match.group(1)] = value
        return out


def load_ai_secrets():
    path = secret_file()
    values = read_env_file(path) if path else {}
    for name, value in os.environ.items():
        if _wanted(name) and value.strip():
            values[name] = value.strip()
    return values
