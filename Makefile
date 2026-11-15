# TwinSite: Flask web app (5050) + platform API (8080) + worker. Run from the repo root.
PYTHON ?= python3.13
VENV_PYTHON := $(if $(wildcard .venv/bin/python),.venv/bin/python,$(PYTHON))
WEB_PORT ?=
API_PORT ?=
DEV_ARGS := $(if $(WEB_PORT),--web-port $(WEB_PORT)) $(if $(API_PORT),--api-port $(API_PORT))
PYPATH := PYTHONPATH=backend:.

.PHONY: setup bootstrap dev web api worker console console-dev reference-dev test test-backend test-acceptance test-frontend \
        test-all schemas smoke check checkpoint worktrees types verify

## setup: create .venv and install every Python dependency (web app + platform + contract checks)
setup:
	$(PYTHON) -m venv .venv
	PIP_CACHE_DIR="$(CURDIR)/.runtime/pip-cache" .venv/bin/python -m pip install -r requirements.txt -r requirements-integration.txt
bootstrap:
	$(VENV_PYTHON) scripts/integration/bootstrap.py
worktrees:
	$(VENV_PYTHON) scripts/integration/worktrees.py

## dev: Flask (5050) + platform API (8080) + worker; Ctrl+C stops all. Ports: make dev WEB_PORT=5051 API_PORT=8091
dev:
	$(VENV_PYTHON) scripts/integration/dev.py $(DEV_ARGS)
## web: Flask site only (proxies /v1 to TWINSITE_API_URL)
web:
	$(VENV_PYTHON) scripts/integration/dev.py --only web $(DEV_ARGS)
api:
	$(VENV_PYTHON) scripts/integration/dev.py --only api $(DEV_ARGS)
worker:
	$(VENV_PYTHON) scripts/integration/dev.py --only worker $(DEV_ARGS)
## console: build the React mission console into frontend/dist (served by Flask at /console/)
console:
	cd frontend && { [ -d node_modules ] || npm ci; } && npm run build
## console-dev: full stack plus the Vite dev server (http://127.0.0.1:5173/console/)
console-dev:
	$(VENV_PYTHON) scripts/integration/dev.py --vite $(DEV_ARGS)
reference-dev:
	$(VENV_PYTHON) scripts/integration/dev.py --reference $(DEV_ARGS)

## test: integration harness tests (needs `make bootstrap` for the extracted reference engine)
test:
	$(VENV_PYTHON) -m unittest discover -s scripts/integration/tests -v
## test-backend: platform + Flask unit tests (backend/tests, incl. backend/tests/flask)
test-backend:
	$(PYPATH) $(VENV_PYTHON) -m unittest discover -s backend/tests -t .
## test-acceptance: provenance / terrain reference checks
test-acceptance:
	$(PYPATH) $(VENV_PYTHON) -m unittest discover -s tests/acceptance
## test-frontend: console typecheck + unit tests
test-frontend:
	cd frontend && npm run typecheck && npm test
## test-all: backend unit tests (platform + Flask), acceptance checks, contract checks, frontend tests
test-all: test-backend test-acceptance schemas test-frontend
schemas:
	$(VENV_PYTHON) scripts/integration/validate_contracts.py
smoke:
	$(VENV_PYTHON) scripts/integration/smoke.py
types:
	$(VENV_PYTHON) scripts/integration/generate_types.py --check
check:
	$(VENV_PYTHON) scripts/integration/checkpoint.py
checkpoint: check
verify:
	$(VENV_PYTHON) ops/verify_current.py
