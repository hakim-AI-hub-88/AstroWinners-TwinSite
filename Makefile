PYTHON ?= python3.13
VENV_PYTHON := $(if $(wildcard .venv/bin/python),.venv/bin/python,$(PYTHON))
.PHONY: setup bootstrap dev reference-dev test schemas smoke check checkpoint worktrees types
setup:
	$(PYTHON) -m venv .venv
	PIP_CACHE_DIR="$(CURDIR)/.runtime/pip-cache" .venv/bin/python -m pip install -r requirements-integration.txt
bootstrap:
	$(VENV_PYTHON) scripts/integration/bootstrap.py
worktrees:
	$(VENV_PYTHON) scripts/integration/worktrees.py
dev:
	$(VENV_PYTHON) scripts/integration/dev.py
reference-dev:
	$(VENV_PYTHON) scripts/integration/dev.py --reference
test:
	$(VENV_PYTHON) -m unittest discover -s scripts/integration/tests -v
schemas:
	$(VENV_PYTHON) scripts/integration/validate_contracts.py
smoke:
	$(VENV_PYTHON) scripts/integration/smoke.py
types:
	$(VENV_PYTHON) scripts/integration/generate_types.py --check
check:
	$(VENV_PYTHON) scripts/integration/checkpoint.py
checkpoint: check
