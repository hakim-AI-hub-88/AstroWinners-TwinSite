# TwinSite handoff index (read this before starting)

This is a time-boxed build plan, not proof that the full application is already implemented. Target: a scientifically defensible, complete competition release before Sunday 15 November 2026 submission cutoff, with a fallback mode even when all AI quota is unavailable.

## Files to open first

1. `TwinSite_Execution_Roadmap.pdf` — printable execution plan and agent briefs.
2. `00_START_HERE.md` — exact order to launch coding chats and manage merges.
3. `contracts/SHARED_CONTRACT.md` — frozen backend/frontend scientific meanings.
4. `01_EXECUTION_ROADMAP.md` — timed gates and ownership.
5. `execution_board.csv` — tasks and assigned leads.

## Paste these prompts into coding sessions

| Session | Prompt | Owns |
|---|---|---|
| Codex 1 | `prompts/01_INTEGRATOR.md` | Repo, interfaces, merges |
| Claude A (Fable 5.2) | `prompts/02_DATA_FABLE52.md` | Real NASA acquisition, decoding, cleaning |
| Claude A science subagent (Fable 5.1) | `prompts/03_SCIENCE_FABLE51.md` | Deterministic scoring and portfolio math |
| Claude B (Opus 5.5) | `prompts/04_BACKEND_OPUS55.md` | API, job worker, evidence endpoints, quota router |
| Claude B UI subagent (Sonnet 5.5) | `prompts/05_FRONTEND_SONNET55.md` | Scientist-oriented frontend |
| Codex 2 | `prompts/06_QA_CODEX.md` | Independent tests, deployment, evidence checks |
| Reviewer before submission | `prompts/07_FINAL_REVIEW.md` | Skeptical judge/release audit |

## Source documents to keep attached in the coding environment

- `ARES_NASA_Feasibility_Architecture.zip` — includes runnable synthetic-reference backend, API/JSON schemas, tests, source validation probes. Keep as READ-ONLY input reference.
- `TwinSite_Engineering_Handoff.zip` — agent definitions, no-AI reference tests, provider registry and historical data source catalog.
- `ARES_Locked_Data_Architecture_2026-11-14.pdf` — earlier locked data types/domains and source classifications; keep all naming in new code as TwinSite.
- `VESPER_credentials_inventory(1).md` — **credential names and provider status only**. Never upload `.env` values to agents or repo.
- User's third visual reference (black, ivory, restrained orange) for frontend design. Ignore blue-neon iterations.

## What gets reviewed at every gate

Use `checklists/STATUS_TEMPLATE.md`, then `checklists/RELEASE_GATES.md`; do not accept 'finished' without commands, test output and a real screenshot. `checklists/DEMO_SCRIPT.md` supplies the 30-second story.

## Caveat

With 22 hours or less, a competition-grade end-to-end release may be possible if integrations behave, but **not** an exhaustive global scientifically validated planetary research platform. Cut advanced features before cutting source data fidelity, evidence transparency, Data Explorer or a working demo.
