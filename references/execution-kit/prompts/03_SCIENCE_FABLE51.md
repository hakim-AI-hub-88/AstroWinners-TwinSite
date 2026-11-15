# PROMPT — Claude account A subagent / Fable 5.1: TWIN-SCIENCE

Own `/backend/twinsite/science` and `/backend/twinsite/portfolios` only. Read the TwinSite locked data architecture, `TwinSite_Engineering_Handoff/reports/03_Simple_Analysis_Engine.md`, old ARES `implementation/ares/engine.py`, its existing tests, and the frozen shared contracts. The reference scoring fixture is synthetic, so clearly distinguish engineering tests from scientific validation.

Build the no-AI Simple Analysis engine: feature registry with body/units/scale/time and missingness policy; Earth-to-Moon and Earth-to-Mars comparisons; normalized weighted scientific similarity; observed coverage and conservative bounds; hard feasibility gates (pass/fail/unknown); source-evidence-linked strengths and weaknesses; temporal evaluation where real time-series evidence exists; sensitivity checks (weights +/- documented change; leave-one-source-out); strict and exploratory modes.

Build candidate and portfolio selection. For small pools enumerate combinations exactly; enforce site-count, budget if user-provided, eligibility and required mission features; reward complementary testing coverage; penalize redundant site sets; report Pareto alternatives. Cost/permissions/field duration without sourced agency evidence are user-supplied parameters or unknown, never inferred silently from maps. Don't confuse missing information with physical dissimilarity.

Inputs must be typed feature observations from DATA lane with source IDs. Output must follow shared result/portfolio contract. All deterministic; no network inference dependency. Put numeric tests covering easy ranking, duplicate sources, missing required feature, impossible units, one negative control, sensitivity and a two-site complementary portfolio. Verify reproducibility with fixed random seeds and tracked versions.

DELIVERABLE G2–G3: 2 real data-derived candidate comparisons and 1 portfolio from actual NASA evidence if source lane supplies it; if not, provide tagged synthetic engineering tests while waiting and explicitly block 'real science' release. Send `SCIENCE_STATUS.md` and test command to integrator.
