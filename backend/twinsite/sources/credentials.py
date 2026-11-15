"""Environment-first credentials, optionally from an owner-only mounted env file."""
import os
import stat
from pathlib import Path

def earthdata_token():
    if os.environ.get("EARTHDATA_TOKEN"):
        return os.environ["EARTHDATA_TOKEN"].strip()
    path = Path(os.environ.get("TWINSITE_SECRET_ENV_FILE", Path(__file__).resolve().parents[3] / ".env"))
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return None
    with os.fdopen(fd) as source:
        st = os.fstat(source.fileno())
        if not stat.S_ISREG(st.st_mode) or stat.S_IMODE(st.st_mode) != 0o600 or st.st_uid != os.getuid():
            raise ValueError("Secret environment file must be a regular owner-owned file with mode 0600")
        for line in source:
            key, sep, value = line.strip().partition("=")
            if key == "EARTHDATA_TOKEN" and sep:
                token = value.strip().strip("\"'")
                if token and not any(c.isspace() for c in token):
                    return token
    return None
