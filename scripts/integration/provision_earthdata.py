"""Run interactively: secret input is never echoed or passed as a command argument."""
import getpass
import os
from pathlib import Path

path = Path(__file__).resolve().parents[2] / ".env"
if path.exists():
    raise SystemExit("Environment file already exists; rotate it securely without overwriting other settings.")
token = getpass.getpass("Earthdata token (hidden): ").strip()
if not token or any(c.isspace() for c in token):
    raise SystemExit("Invalid token format")
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as target:
    target.write("EARTHDATA_TOKEN=" + token + "\n")
print("Credential provisioned with mode 0600; value withheld.")
