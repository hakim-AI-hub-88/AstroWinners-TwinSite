# TwinSite: AI and scientific data status (2026-11-15)

Generated from the AI usage ledger (`.runtime/ai_ledger.sqlite`), probe facts and `docs/release/COVERAGE_MATRIX.json`. No secret values appear here.

## Architecture as implemented
- **Default: AI-Powered Analysis.** Selected per mission with `POST /v1/missions?analysis_mode=ai|simple`. AI is the default in the API, the UI toggle and `scripts/integration/dev.py`.
- **Deterministic engine** computes every measurement, score, eligibility decision, portfolio and the release gate. A08 asserts that the result hash is unchanged by AI stages.
- **13 roles** (`backend/twinsite/ai/agents.py`):
  - AI roles: A02 vision, A05 scenarios (re-scored by the real engine and labelled as assumptions), A06 domains, A07 synthesis, A09 independent-provider review plus a deterministic numeric cross-check, A12 targeted recheck, and A13 narrative.
  - Deterministic roles: A01, A03, A04, A08, A10, A11.
- **Fallback.** If AI is unavailable, every AI role is recorded as `fallback` with the real reason, and the Simple Analysis result is delivered unchanged.
- **Free only.** No paid model exists in the catalog. HTTP 402 opens a 24 h breaker. OpenRouter is allowed only `:free` models, and only while `/key` reports `is_free_tier=true`.
- **Usage controls.** Per-quota-group daily caps; `dev` priority is limited to 50% of each cap, keeping a demo reserve.

## AI provider status
Credentials were migrated with `ops/migrate_vesper_credentials.py` into `.runtime/secrets/ai-providers.env` (directory 0700, file 0600, gitignored). Probes were made with `ops/ai_probe.py`: one call per quota group.

| Provider | Discovered | Migrated | Quota groups | Verified free models (real inference) | State / errors |
|---|---|---|---|---|---|
| Groq | 5 | 5 | 5 | openai/gpt-oss-120b | inference_verified (5/5 groups) |
| Cloudflare Workers AI | 6 pairs | 6 | 6 accounts | @cf/openai/gpt-oss-120b | inference_verified (6/6); usage fields unreliable, so request caps are used |
| Google Gemini | 6 + 2 reserved | 6 | 6 projects | gemini-3.6-flash (text + vision) | inference_verified (6/6); public data only (free tier trains on inputs) |
| OpenRouter | 2 | 2 | 2 | nvidia/nemotron-3.5-super-vl:free | inference_verified; both accounts `is_free_tier=true`, usage 0 |
| NVIDIA NIM | 2 | 2 | 2 | nvidia/nemotron-3-ultra-550b-a55b | inference_verified; nemotron-3-super returned 404 (not enabled) |
| Mistral | 9 | 9 | 9 | none | **quota_limited**: HTTP 429 on all keys; retried after cooldown |
| Ollama Cloud | 3 | 3 | 3 | none | **blocked**: HTTP 402 "payment required" on gpt-oss:120b for all 3 keys; treated as non-free and fail-closed (24 h breaker) |
| ElevenLabs | 6 | 6 | 6 | n/a | registered for speech only; no TwinSite feature invokes it |
| Excluded | GEMINI_API_KEY, GOOGLE_API_KEY | – | – | – | reserved by owner for tooling in VESPER |
| Excluded | VESPER_CLAUDE_TOKEN, VESPER_CLAUDE_ADVISOR_TOKEN | – | – | – | subscription session tokens, not API credentials |

Corrections against VESPER's `provider_supply.toml`:
- google-navigator, google-briefer, openrouter-auditor and nvidia-researcher are E2 (public data only), not E1.
- `GOOGLE_API_KEY_SCHOLAR` does not exist.
- Stale model IDs were replaced after checking each provider's list-models endpoint.

Caveat: VESPER still uses these same accounts, and its usage is not visible to TwinSite's ledger. Provider 429 responses are treated as authoritative.

## Real AI mission (measured Zagora to Gale)
`run-d7b84f7f350ac24de32b069e` executed **7 AI roles for real** across Groq, Cloudflare and Gemini:

| Role | Provider / model | Result |
|---|---|---|
| A02 | Gemini 3.6 flash | Qualitative reading of the GIBS image |
| A05 | Groq gpt-oss-120b | 2 scenarios, re-scored by the engine |
| A06 | Groq gpt-oss-120b | 10 evidence-linked findings |
| A07 | Cloudflare gpt-oss-120b | Synthesis |
| A09 | Gemini (independent provider) | Review of the synthesis claims |
| A12 | Groq gpt-oss-120b | Recheck of the 3 flagged claims |
| A13 | Groq gpt-oss-120b | Evidence-cited narrative |

In that run, the deterministic A09 numeric cross-check flagged 3 claims, including one that presented analysis-block counts as km², which the AI reviewer had accepted. The cross-check was later tightened: numbers embedded in free-text strings no longer count as evidence, so such re-labelled counts stay flagged.

The release gate stays **BLOCK**, by the deterministic gate: AOI extent mismatch, independent C5 review required, no qualified candidate.

## Scientific data status
| Source | Body | Real retrieval | Decode / QA | Persisted (lineage, SHA-256) | Used by engine | AI agents | Data Explorer |
|---|---|---|---|---|---|---|---|
| LP DAAC SRTMGL1 (cached; old Earthdata token not reused) | Earth | cached verified tile | yes | published pairs | yes (slope, roughness, relief) | yes | yes |
| AWS Terrain Tiles terrarium z11 / skadi (keyless) | Earth | **live, any point** | PNG CRC, terrarium decode, void/range QA | sites + science.sqlite | yes (match missions) | yes | yes |
| NASA POWER climatology (MERRA-2/CERES) | Earth | **live, any point** | fill mask, unit check | science.sqlite | context only (model data) | yes | yes |
| NASA GIBS true colour | Earth | **live** | JPEG check | science.sqlite | no (visual) | A02 qualitative | yes (image) |
| OpenStreetMap Overpass (mapped roads/tracks) | Earth | **live** | count parse; completeness flagged | science.sqlite | no (context) | yes | yes |
| MODIS MOD11A2 LST (CMR) | Earth | discovery only | – | metadata row | no | no | listed as gap |
| MGS MOLA MEGDR 128 ppd | Mars | **live, any point** (byte ranges) | shot-support QA | pairs + sites | yes | yes | yes |
| LRO LOLA LDEM_64 | Moon | **live, any point** (byte ranges) | label-driven decode, range QA, interpolation flagged | pairs + sites | yes | yes | yes |
| LRO Diviner GCP (bolometric T) | Moon | **live, any point** (row ranges, every row bin-verified) | fill/negative masked, day max / night min | pairs + sites | not weighted (no comparable Earth LST) | yes | yes |
| NSSDCA planetary constants | all | reference | – | science.sqlite | no | yes | yes |
| Diviner rock abundance, LEND/LP-NS hydrogen, CRISM, EMIT, THEMIS, MEDA/REMS, MCS, HLS, SPICE | – | **not implemented** | – | – | – | – | gaps in coverage matrix |

Seeded real sites: 36 Earth analog sites, 15 Moon targets, 14 Mars targets (`ops/seed_sites.py`), each characterised from real data at a common 1900 m scale over a metric-matched ~33 km area. Any other point can be characterised on demand (`POST /v1/science/characterize`) or matched (`POST /v1/missions/match`: target characterised live, all stored Earth sites pre-ranked, extent-incompatible sites excluded by the gate's own rule, full mission on the top 12).

Coverage: `docs/release/COVERAGE_MATRIX.json` (generated from persisted evidence). **Not all 14 domains are covered**: geology/mineralogy, resources/volatiles and mechanics have no real source yet; Mars thermal/atmosphere and Earth calibrated LST are missing.

## Verification and deployment
- `make verify` (`ops/verify_current.py`): all 17 automated checks PASS, including the `ai_router_agents_gateway` suite (offline, AI-free, no network). The command still exits 1 because the script always records `browser_smoke` as BLOCKED ("requires separate browser verification"), exactly as in the original baseline; browser checks were done manually (below).
- Browser: verified manually in the in-app browser against an AI-enabled stack: Workspace AI/Simple toggle, a measured AI-mode run with live agent events and the agent panel, and the Data Explorer multi-site comparison with a live NASA POWER retrieval (Atacama).
- Deployment: VM systemd units read AI keys from `/etc/twinsite/ai-providers.env` (owner twinsite, 0600). **Not deployed.** No VM access has been provided, so no deployed URL exists.
