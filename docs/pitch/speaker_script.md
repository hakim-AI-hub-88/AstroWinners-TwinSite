# TwinSite speaker script

Main pitch: approximately 5 minutes at a natural pace. Slides 15–18 are optional and excluded from the pitch timing.

## 01 — TwinSite

Before a mission reaches the Moon or Mars, teams need places on Earth where they can test an idea. TwinSite helps investigate those analog environments using scientific evidence, AI interpretation, and calculations that remain reproducible. This is our working prototype for the NASA Space Apps Challenge.

## 02 — The analog selection problem

The difficult part is deciding what resemblance means for a mission. A terrain map, a climate product and an image do not measure the same thing. Even two elevation models can use different scales and study areas. Teams also need practical constraints, such as field access and available time, before a scientific comparison can support a decision.

## 03 — Earth as a planetary laboratory

Earth provides accessible environments for investigating selected planetary processes. The comparison must follow the task: terrain morphology for mobility, environmental context for field operations, and constraints supplied by the mission team. No Earth site recreates lunar vacuum or Martian gravity. TwinSite makes those boundaries part of the investigation.

## 04 — Introducing TwinSite

TwinSite brings the investigation into one workspace. Users define a target and their mission priorities, inspect source evidence, and run an analysis. AI helps interpret that evidence. Deterministic software owns the numerical result. The interface connects the resulting assessment with its data, execution history, portfolio outcome and scientific report.

## 05 — How TwinSite works

The pipeline starts with mission objectives and pinned scientific sources. Preparation and quality checks establish whether values are usable. The deterministic engine then calculates features, scores and portfolio eligibility. AI interprets the evidence and proposes explicit scenarios that the engine can re-score. Review checks the claims and the release gate. If AI is unavailable, Simple Analysis preserves the computed result.

## 06 — Scientific data

The current build uses SRTM and MOLA for its Earth–Mars terrain comparison. Newer code and the live catalog also expose LOLA terrain and Diviner lunar temperatures. POWER supplies Earth climatology as model products. GIBS and Trek provide visual context. MODIS land-surface temperature is still discovery-only. These sources have different roles, and the deck does not imply complete coverage of every scientific domain.

## 07 — Thirteen roles

The original thirteen roles are implemented as a division of responsibility. Seven use AI to interpret imagery, develop scenarios, analyze domains, synthesize, review, recheck and write. Six perform deterministic curation, preparation, quality checks, auditing and release control. In the recorded measured mission, all seven AI roles executed, including one cached response from an earlier real call. That is execution evidence, not scientific certification.

## 08 — Scientific integrity

A real run shows why this separation matters. The AI reviewer accepted claims that a deterministic numeric cross-check flagged. Three claims remained unsupported, including a confusion between analysis-block counts and square kilometers. The report still needs human scrutiny, but the numerical result and blocked release remain protected. Every source asset carries a hash, and missing data remains visible.

## 09 — Measured terrain

Here are the actual Zagora and Gale terrain summaries, reproduced from cached source bytes at a common 1,852.3-metre analysis scale. The values differ in slope, roughness and relief. But equal analysis scale is not enough: the Earth study area is about 3.33 times larger by analysis-block count. Relief depends on extent, and distributions use different sample sizes. TwinSite therefore blocks a claim of direct equivalence or mission suitability.

## 10 — Explore and compare

Researchers can open the catalog and compare actual records side by side. The interface exposes units, source products, quality flags and distributions. It also explains when study-area differences limit interpretation. The current application includes Earth, Moon and Mars map views, while the data comparison remains grounded in the available observations.

## 11 — Mission planning and portfolios

The optimizer can enumerate combinations, reward complementary evidence and penalize redundancy while applying hard constraints. Its engineering behavior is covered by tests. In this measured preset, unknown access makes the only Earth candidate ineligible, and no feasible portfolio remains. A useful scientific tool must be able to return that outcome. Demonstrating complementary real-world portfolios needs additional measured sites and operational inputs.

## 12 — AI-Powered and Simple Analysis

AI-Powered Analysis adds interpretation and evidence-cited narrative. Simple Analysis provides the same deterministic scientific calculations without AI access. If a provider is unavailable, the system records the reason and falls back. This makes the core workflow usable under quota or connectivity constraints, while keeping the scientific result separate from the reliability of a language-model response.

## 13 — Impact and future potential

The potential value is a more inspectable starting point for planetary scientists, analog field teams and mission or robotics engineers. Educators can also use it to show how source evidence becomes an assessment. The next milestones are concrete: matched study areas, more measured Earth sites, operational data, named independent review and field validation. Those steps would strengthen the prototype into a more useful research platform.

## 14 — Closing and live demo

TwinSite connects planetary analog discovery with evidence that people can inspect. The prototype already links sources, deterministic computation, AI investigation and transparent limitations. We can now show the local application: define a mission, inspect the measured comparison, and follow the evidence into its report. Better analog choices begin with traceable evidence.

## 15 — Status snapshot

Optional technical discussion. The automated verification summary records seventeen passing automated suites and a separate blocked browser-smoke item, not a blanket all-green result. This presentation adds focused visual inspection and offline provenance recomputation. The lunar connectors pass seven current unit tests, but this does not independently validate their science. Recorded AI claims retain known limitations.

## 16 — Terrain methods

The terrain screenshot is the real cleaned SRTM display grid, not the analysis grid used for scoring. Slope uses Horn gradients on block means. Roughness is the mean local three-by-three population standard deviation. Relief is the range over the study area. Cross-body absolute elevation is excluded because the vertical datums differ. MOLA retains interpolated cells. About 25.7 percent of native cells have shots, while 74.1 percent of analysis blocks contain at least one shot.

## 17 — Current lunar work

The live catalog and published artifact include a newer lunar pair. These are the published terrain values, at a different analysis scale from the Mars pair, so the Earth values also differ. The implementation describes approximately matched metric areas, within its extent tolerance. Diviner temperatures are lunar context at a coarser scale. Independent numeric and scientific review remains pending. The Tycho photograph is context and does not depict the analyzed site.

## 18 — References

Full source URLs and attribution details are in SOURCES.md and in individual slide notes. Product screenshots are authentic captures of the local TwinSite application. Scientific photos are context images and are never used as evidence for the numeric comparisons. NASA Space Apps is event context and does not imply NASA endorsement.
