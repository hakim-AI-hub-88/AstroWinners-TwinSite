# TwinSite execution roadmap — 15 Nov 2026

The global submission deadline described in the prior official event material is **23:59 local time, November 15**. The team must confirm any earlier venue cutoff in its registered event interface. Start clock for this document: ~02:00 Morocco time. This is a proposed plan, not a guarantee.

## Release statement

TwinSite must be a complete **competition release**: landing page, mission setup, bounded Earth/Moon/Mars exploration, real-data ingestion and evidence, no-AI scoring, comparisons, pros/cons, portfolios, timeline/mission activity, read-only Data Explorer with side-by-side viewing, scientific reports, and trustworthy failure states. **Advanced planetary 3D terrain, global exhaustive discovery, unrestricted PDF understanding, fully parallel 13-LLM swarm, real logistics pricing and calibrated probabilistic confidence remain staged** if not scientifically defensible.

## Workstreams / exclusive ownership

| Lane | Coding assistant | Owns | Must deliver |
|---|---|---|---|
| C0 | Codex 1 integrator | `/contracts`, `/scripts/integration`, root workspace config | Frozen API + merge validation + a single run command |
| C1 | Claude A, Fable 5.2 | `/backend/twinsite/sources`, `/backend/twinsite/processing`, `/backend/twinsite/vision` | Bounded NASA connector + immutable source snapshot + product-aware QA |
| C2 | Claude A subagent, Fable 5.1 | `/backend/twinsite/science`, `/backend/twinsite/portfolios` | Deterministic real-feature comparisons + strict gates + alternatives |
| C3 | Claude B, Opus 5.5 | `/backend/twinsite/api`, `/backend/twinsite/jobs`, `/backend/twinsite/storage`, `/backend/twinsite/ai` | HTTP job API + worker + progress + read-only evidence endpoints + optional AI router |
| C4 | Claude B subagent, Sonnet 5.5 | `/frontend` | Coherent scientist-first React app, maps, charts, results and Data Explorer |
| C5 | Codex 2 QA | `/tests/e2e`, `/tests/acceptance`, `/ops`, `/docs/release` | Smoke tests + reproducibility + deploy scripts + demo artifacts |

Only the integrator merges branches. Assistants do not modify another owner's files. Request a reviewed interface change instead.

## Timeline and hard gates

| Local time | Gate | Must be true before expansion |
|---|---|---|
| 02:00–02:45 | G0 Contracts frozen | Repo created, owners assigned, required endpoints and JSON shapes fixed |
| 02:45–05:00 | G1 Vertical slice | Mission submit -> worker -> deterministic result -> report -> frontend display, even if fixture-only at first |
| 05:00–09:00 | G2 Real NASA evidence | At least one Earth and one Moon or Mars source product actually downloaded/decoded, QA/provenance checked, real-feature comparison produced |
| 09:00–13:00 | G3 Complete core workflow | Rankings, strengths/weaknesses, alternatives, portfolio constraints, 2D map, data explorer, read-only side-by-side data comparison |
| 13:00–16:00 | G4 Product breadth | Polished landing/docs, mission activity, timeline/seasonality when sourced, Earth globe, PDF/JSON/CSV export, optional agent explanation |
| 16:00–19:30 | G5 Science & reliability | Independent negative/missing-data controls, strict failure gates, load tests, cached no-AI demo, responsive UI |
| 19:30–21:30 | G6 Freeze and demo | Working public URL, real dataset citation manifest, full screencast, 30-sec video/allowed deck, sources and AI disclosure |
| 21:30–22:30 | G7 Submit | Submission form complete, links public, confirmation recorded; avoid relying on 23:59 |
| 22:30–23:59 | Reserve | Only critical fixes and receipt verification if official system permits |

## Priority if behind

- At G1 fail: stop all advanced features; rescue one end-to-end execution path.
- At G2 fail: never pass synthetic as NASA evidence; display unsupported states and invest in one reliable product pair.
- At G3 fail: defer optional AI, advanced 3D terrain and PDF ingestion. Basic tables + report beat decorative features.
- At G4 fail: disable nonworking routes visibly, do not ship empty screens disguised as complete features.
- At G5 fail: freeze features, fix correctness and deployment; preserve recorded demo fallback.

## Workload policy

Fable 5.2 handles the most demanding and bounded data acquisition/decoding task; Fable 5.1 deterministic mathematical analysis; Opus 5.5 integration-heavy backend; Sonnet 5.5 UI; Codex for independent QA and merge checks. Copilot's 2,000 completions are *editor suggestions*, not 2,000 autonomous coding jobs. Never assign quotas based on unverified model entitlements.

## Scientific pass/fail criteria

1. Source product, version, download time, source granule/URL, checksum, licensing and footprint recorded.
2. Units, CRS, pixel/temporal resolution, calibration, masks and null flags decoded with product-aware rules.
3. Required features missing => scientific conclusion blocked in strict mode, not filled with guesses.
4. Negative controls, weight sensitivity and correlated input data checked.
5. Reports separate measured, derived, assumed/user-provided and unavailable values.
6. UI labeling matches actual backend state (no decorative '99% confidence').
7. No-AI path works even when every inference credential is absent.

## Demo story

Select a real Mars or Moon region. TwinSite retrieves a bounded, cited target dataset and Earth analog candidates; shows cleaning and quality gates; scores compatible terrain (plus measured thermal/time data if ready); explains one candidate and one rejection; produces a complementary portfolio; opens the evidence Data Explorer to compare original and cleaned records; shows workflow history; exports a source-backed report.
