# Contributing to TwinSite

Thanks for helping. TwinSite is an open-source NASA Space Apps 2026 project (MIT).

## Set up

```bash
make setup      # .venv + requirements.txt + requirements-integration.txt
make console    # build the React console (frontend/, Node.js 20+)
make dev        # Flask :5050 + platform API :8080 + worker (Ctrl+C stops all)
```

Layout: Flask site in `backend/app.py`, `backend/{routes,services,utils}`, `templates/`, `static/`;
platform API and worker in `backend/twinsite/`; JSON contracts in `contracts/`; console in `frontend/`;
deployment in `ops/`. See [docs/README.md](docs/README.md) and [docs/INTEGRATION_SPEC.md](docs/INTEGRATION_SPEC.md).

## Before you open a pull request

- `make test-all` passes (backend + Flask unit tests, acceptance checks, contract schemas, console typecheck and tests).
  CI runs the same checks plus `npm run build`.
- New behaviour has a test (`backend/tests/...` with `unittest`, `frontend/src/__tests__/` with Vitest).
- Contract changes go through `contracts/v1` schemas and examples (`make schemas`, `make types`).

## Rules that keep the project honest

1. **Accurate claims.** Docs, UI copy and the README describe only what the code does, with its limits.
   Planned work is labelled as planned.
2. **No fabricated data.** If a live source fails, return `status: "unavailable"` with a reason; never
   fill in, interpolate silently or reuse a synthetic value as measured.
3. **AI never owns a number.** Deterministic code computes every measurement, score and release decision;
   AI output explains and must cite evidence that exists.
4. **No secrets in git.** Keys live in `.env` (git-ignored) or a 0600 secret file; `.env.example` lists names only.
5. **Free tiers only** for AI providers; no paid inference paths.

Keep pull requests focused, describe what you verified, and keep `data_ready/` changes separate from code changes.
