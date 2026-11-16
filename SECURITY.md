# Security policy

## Reporting a vulnerability

Please report security issues privately through GitHub's **Security → Report a vulnerability**
(private advisory) on this repository, not in a public issue. Include steps to reproduce and the
affected path or endpoint. We aim to acknowledge reports within a few days; this is a volunteer
research project, so there is no bug bounty.

## Scope and practices

- Supported: the latest commit of the default branch.
- Secrets: API keys are read server-side only, from the environment or a 0600 file named by
  `TWINSITE_AI_SECRET_ENV_FILE`; they are never sent to the browser or logged, and `.env` is git-ignored.
  The deployed services hold no NASA Earthdata credentials.
- Deployment hardening: loopback-only app ports behind nginx, systemd sandboxing, strict CSP on the
  console and `/v1`, rate limiting on `/v1` ([ops/vm/README.md](ops/vm/README.md)).
- Uploads are disabled (`TWINSITE_UPLOADS_ENABLED=false`).
- If you find a committed secret, report it privately; it will be revoked, not just deleted from history.
