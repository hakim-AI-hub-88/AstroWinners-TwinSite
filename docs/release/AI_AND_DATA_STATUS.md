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
| Source | Discovery | Auth | Real retrieval | Decoded / QA | Evidence persisted | Used by analysis | Data Explorer |
|---|---|---|---|---|---|---|---|
| SRTMGL1 (LP DAAC) | yes | Earthdata (old token compromised, not reused) | cached verified tile | yes | G2 pair | Simple + AI | yes |
| MOLA MEGDR (PDS) | yes | none | cached | yes | G2 pair | Simple + AI | yes |
| NASA POWER climatology | yes | none | **live** | fill mask, unit check | science.sqlite + asset SHA-256 | AI agents (context evidence) | yes, any Earth point, side by side |
| NASA GIBS WMS | yes | none | **live** | JPEG check; visualization only | yes | A02 (qualitative) | yes (image) |
| MODIS MOD11A2 (CMR) | **discovery only** | needs a new Earthdata token | no | – | metadata row | no | yes (as missing) |
| NSSDCA constants | – | none | transcribed | – | yes | AI context | yes |
| LOLA, Diviner, LROC, LEND, MEDA/REMS, MCS, THEMIS, CRISM, HLS, EMIT, OSM, SPICE | not implemented | – | no | – | – | – | listed as gaps in the coverage matrix |

Coverage across the 42 domain × body cells:

| Status | Cells |
|---|---|
| real_data | 6 |
| implemented (contract-level) | 6 |
| reference_constant | 2 |
| visualization_only | 1 |
| user_input | 3 |
| user_input_only | 3 |
| missing | 21 |

**Not all 14 domains are covered.**

## Verification and deployment
- `make verify` (`ops/verify_current.py`): all automated checks pass and it exits 0, including the new `ai_router_agents_gateway` suite (offline, AI-free, no network).
- Browser: verified manually in the in-app browser against an AI-enabled stack: Workspace AI/Simple toggle, a measured AI-mode run with live agent events and the agent panel, and the Data Explorer multi-site comparison with a live NASA POWER retrieval (Atacama).
- Deployment: VM systemd units read AI keys from `/etc/twinsite/ai-providers.env` (owner twinsite, 0600). **Not deployed.** No VM access has been provided, so no deployed URL exists.
