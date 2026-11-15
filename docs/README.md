# TwinSite documentation

[← Project README](../README.md)

## Guides

| Document | What it covers |
| --- | --- |
| [Project README](../README.md) | What ships, quick start (`make setup`, `make dev`), configuration, deployment links |
| [CONTRIBUTING](../CONTRIBUTING.md) | Dev setup, tests, accurate-claims rule, pull requests |
| [SECURITY](../SECURITY.md) | Reporting vulnerabilities, secrets handling |
| [Platform dev notes](PLATFORM_DEV_NOTES.md) | Platform API, worker, gates and reference baseline (developer notes) |
| [backend/README.md](../backend/README.md) | Flask backend layout |
| Web pages | `/resources` (guides, stack, APIs, agents), `/sitemap`, `/policy` in the running app |

## Architecture and reference

| Document | What it covers |
| --- | --- |
| [Integration spec](INTEGRATION_SPEC.md) | Process layout (web 5050, API 8080, worker), routes, JSON APIs, lane ownership |
| [Resource atlas](catalog.md) | HTTP APIs, data sources, AI and models, reports, research links |
| [Implementation audit](implementation.md) | Which paths are executable vs. described or planned |
| [Repository inventory](inventory.md) | Every tracked file of the audited base commit |
| [README assets](readme/README.md) · [Verification notes](readme/VERIFICATION.md) | How the README visuals were built and checked |
| [Pitch](pitch/README.md) · [Sources](pitch/SOURCES.md) | Pitch deck material and its sources |

## Deployment

| Document | What it covers |
| --- | --- |
| [VM runbook](../ops/vm/README.md) | Provision → `install.sh` → seed sites → smoke test → TLS (nginx + gunicorn + systemd) |
| [Vercel edge](deployment/VERCEL.md) | Why Vercel is the edge only, `vercel.json` rewrite to the VM, exact steps |
| [Release deployment notes](release/DEPLOYMENT.md) | Historical C5 rationale for a single persistent VM |
| [Environment template (VM)](../ops/vm/env.example) · [Environment template (local)](../.env.example) | Every variable, names only |

## Status and release

| Document | What it covers |
| --- | --- |
| [Integration status](status/INTEGRATION_STATUS.md) | Gate results across lanes |
| [API status](status/API_STATUS.md) | Platform API and worker |
| [Data status](status/DATA_STATUS.md) | NASA sources, acquisition, QA |
| [Science status](status/SCIENCE_STATUS.md) | Scoring engine, release gate |
| [AI and data status](release/AI_AND_DATA_STATUS.md) | Providers, agents, coverage |
| [Scientific review](release/SCIENTIFIC_REVIEW.md) | Why the scientific release is BLOCK |
| [QA status](release/QA_STATUS.md) · [Live acceptance](release/LIVE_ACCEPTANCE.md) · [Demo checklist](release/DEMO_CHECKLIST.md) | QA snapshots and demo rules |
| [C0 integration report](release/C0_INTEGRATION_REPORT.md) · [C0 API extensions](release/C0_API_EXTENSIONS.md) · [Coverage matrix](release/COVERAGE_MATRIX.json) | Integration checkpoints |

## Contracts

| Path | What it covers |
| --- | --- |
| [contracts/SHARED_CONTRACT.md](../contracts/SHARED_CONTRACT.md) | The shared mission contract between lanes |
| [contracts/v1/](../contracts/v1) | Frozen JSON Schemas (Draft 2020-12) for `/v1` |
| [contracts/examples/](../contracts/examples) | Shared examples validated by `make schemas` |
| [contracts/types.ts](../contracts/types.ts) | Generated TypeScript types used by the console (`make types` checks drift) |
| [contracts/FRONTEND_ROUTES.json](../contracts/FRONTEND_ROUTES.json) | Console routes (served under `/console/`) |
