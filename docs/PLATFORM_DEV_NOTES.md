# TwinSite

NASA Space Apps competition build. Current state: integration scaffolding with a runnable **synthetic ARES reference**. No real NASA comparison or deployed TwinSite frontend is claimed.

## Setup

Use Python 3.13 (3.11+ supported), Git, and Node/npm when the frontend lane lands. Python integration dependency is pinned in `requirements-integration.txt`. The backend/frontend owners supply their own package dependencies and lockfiles before G1.

```sh
make setup
make bootstrap
make worktrees
make check
```

If this sandbox cannot modify `.git`, run `make worktrees` from a normal terminal in this folder. The script uses your configured Git identity, initializes main, commits only the enumerated scaffold and creates separate branches/worktrees. It never chooses an identity or stages the entire folder. Existing author changes are preserved. Inspect `git diff --cached` before retrying a failed bootstrap commit.

| Lane | Branch | Working directory | Ownership |
| --- | --- | --- | --- |
| C0 integration | `main` | project root | root configuration, contracts, integration scripts |
| C1 data | `lane/data` | `.worktrees/data` | sources, processing, vision |
| C2 science | `lane/science` | `.worktrees/science` | science, portfolios |
| C3 backend | `lane/backend` | `.worktrees/backend` | api, jobs, storage, ai |
| C4 frontend | `lane/frontend` | `.worktrees/frontend` | frontend |
| C5 QA | `lane/qa` | `.worktrees/qa` | tests/e2e, tests/acceptance, ops, docs/release |

Read [contracts/SHARED_CONTRACT.md](contracts/SHARED_CONTRACT.md) before coding. C0 alone merges; no owner modifies another lane without consent. C0 reviews changed paths and checks on a candidate integration branch before merging main. Keep the contract freeze identical in all worktrees. Worktree creation does not launch coding agents or synchronize later commits automatically.

## Run

```sh
make dev
```

This starts the Flask site (`backend/app.py`, port 5050), the platform API (`python -m twinsite.api`, port 8080) and the worker (`python -m twinsite.jobs`) with `PYTHONPATH=backend:.`; Flask serves the built console at `/console/` and proxies `/v1` to the API. Ports: `make dev WEB_PORT=5051 API_PORT=8091`. The Vite dev server (5173, `/console/`, proxying `/v1`) is opt-in: `make console-dev`. Backend imports `contracts.validation` from the workspace root. Processes share `.runtime` storage. Ctrl+C stops the stack. No automatic synthetic fallback.

For the existing unmodified historical reference:

```sh
make reference-dev
# Open http://127.0.0.1:8080
```

That command runs the historical API/worker/UI with synthetic examples and a separate local SQLite database. It is NOT a NASA-validated service; never deploy it publicly. All core calculations in that reference run without AI keys. The reference map requires external assets; tables and reports are separate. Visual UI acceptance is still pending.

`.env.example` lists placeholder names only. The launcher loads an optional repo-root `.env` (shell variables win; values are never printed). Configure server secrets locally outside Git; never use frontend-prefixed variables for secrets. Private uploads stay disabled. AI is enabled only when free-provider keys or the 0600 secret file are present (`--no-ai` forces Simple Analysis). No paid fallback.

## Checkpoints

```sh
make test
make schemas
make types
python3.13 scripts/integration/smoke.py --reference
make check
# After make dev is running:
make smoke
# In a separate terminal for the active build shift:
python3.13 scripts/integration/checkpoint.py --watch
```

The watcher reruns every 75 minutes; stopping that process stops monitoring. `make check` records exact PASS/FAIL/BLOCKED values in `.runtime/checkpoint.json` and exits nonzero if anything is missing. It does not pretend an absent frontend build or API is a pass. The synthetic reference smoke verifies submission, idempotency, worker execution, deterministic output, event ordering/cursor, report labeling and failure responses. It is not G2 evidence.

See [INTEGRATION_STATUS.md](status/INTEGRATION_STATUS.md) for current gate results. The original roadmap and prompts are in `references/execution-kit`. The three archives are pinned by SHA-256 in `references/SNAPSHOT.json`; `make bootstrap` verifies them before extraction and refuses to overwrite modified reference code.
