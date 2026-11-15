# PROMPT — Codex session 2: TWIN-QA, reproducibility and deployment

Own only `/tests/e2e`, `/tests/acceptance`, `/ops`, `/docs/release`. Do not rewrite data, science, API or frontend files unless the integrator approves. Read the shared contract and TwinSite project handoffs. Serve as independent skeptic; aggressively test claims and preserve evidence.

At G1 write a smoke test for submission -> worker events -> result/report -> frontend. At G2 verify downloaded files have real NASA product/granule IDs and raw checksums; compare an independently computed representative feature or source number; ensure examples marked synthetic never enter live output. At G3 validate strict missing-required feature blocks, preservation of units/CRS, duplicate-source handling, cost assumption disclosure, alternate portfolios without re-downloads, data explorer pagination/compare and security (no arbitrary SQL or secret exposure). At G5 verify AI-free path with all provider keys absent and server restart behavior.

Prepare deployment using the available VM and host; test actual command and set persistent disk / worker lifecycle. Do not assume free hosting has durable background worker. Use minimal CI and lockfiles. Produce one `make verify` or equivalent, failure summary, environment requirements, and a 30-second demo shot checklist with capture of real provenance.

For external-AI consent tests: ensure default is NO external upload transmission, require per-provider opt-in, preserve audit record and block accidental upload. No public listing of private uploaded data. Verify client search paths and UI route 404 behavior.

At each gate return `QA_STATUS.md` showing P0 blocker count, tests pass/fail, actual deployed URL if any, unresolved provenance gaps, and a one-line RELEASE / HOLD recommendation. Treat UI beauty as secondary to accurate evidence.
