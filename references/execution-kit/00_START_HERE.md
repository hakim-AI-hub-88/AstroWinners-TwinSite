# TwinSite — November 15 execution kit

**Objective:** A fully navigable, scientifically honest NASA Space Apps competition release by the November 15, 2026 submission cutoff. Not a claim of production-grade automation across the whole Earth.

## Who does what

- **You:** project director and dispatcher. Give each coding session its prompt, enforce folder ownership and merge gates, supply credentials through secure local environment configuration only, review screenshots and the final demo.
- **Claude account A / Fable 5.2 + Fable 5.1 subagent:** source products, data preparation, quality gates and scientific analysis. Keep these as separate working directories/branches.
- **Claude account B / Opus 5.5 + Sonnet 5.5 subagent:** API/orchestration/worker and frontend. Different folder ownership.
- **Codex session 1:** repository integrator, contract keeper, merge reviewer.
- **Codex session 2:** QA, reproducibility, deployment, acceptance scripts.
- **This ChatGPT conversation:** specification and independent review of error logs, screenshots, tests, scientific claims and integration decisions when shared; cannot control external sessions directly.

## Quick start, first 20 minutes

1. Create **one Git repository** named `twinsite`, with a `main` branch and separate branches/worktrees for each worker. Never let assistants rewrite the same files concurrently.
2. Put `ARES_NASA_Feasibility_Architecture.zip` and `TwinSite_Engineering_Handoff.zip` in a **reference-only** `references/` folder (do not blindly copy synthetic observations into production).
3. Paste `prompts/01_INTEGRATOR.md` into Codex 1. It freezes paths, API shapes, schema versions and git ownership.
4. Paste `prompts/02_DATA_FABLE52.md` into Claude account A. Delegate the science engine to Fable 5.1 using `prompts/03_SCIENCE_FABLE51.md` only with separate file ownership.
5. Paste `prompts/04_BACKEND_OPUS55.md` into Claude account B. Delegate UI to Sonnet 5.5 using `prompts/05_FRONTEND_SONNET55.md` with separate ownership.
6. Paste `prompts/06_QA_CODEX.md` into Codex 2.
7. Keep the first success condition narrow: **one Earth site, one planetary target, one real data product per side, one validated comparison, one report.**

## Hard rules

- No fabricated NASA values or fabricated scientific confidence. Synthetic fixtures stay clearly labeled and must never enter live scientific results.
- Source snapshot + native unit + coordinate reference + QA + processing version + resolution + time must travel with every scientific measurement.
- No UI login, RBAC or settings screen. Public agency records can be read-only explored. User-uploaded data require a separate ephemeral per-mission access capability and must not be openly listed.
- No paid AI fallback. AI is optional, bounded, disclosed for user uploads, and **never** produces core measurements, cost estimates disguised as facts, or final eligibility decisions.
- Protect the last remaining demo credits; cached real outputs must give an end-to-end demo with AI completely disabled.
- Do not repeatedly ingest NASA files when only scoring weights change.
- Stop feature additions before recording/submitting the competition entry. Submission is a milestone, not the last-minute afterthought.

## Start-of-shift status request

Ask each coding assistant to return these five fields every checkpoint:
`DONE`, `FILES CHANGED`, `TESTS RUN + RESULTS`, `BLOCKERS`, `NEXT GATE`.

**Reference note:** The old ARES implementation is a **synthetic-data reference**, not a validated scientific product. Reuse its job and scoring contracts where sound; replace source acquisition, product decoding and scientifically unsupported assertions.
