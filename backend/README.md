# TwinSite backend

Flask serves the home page, dashboard, static assets and eleven API routes through five blueprints. The similarity engine is implemented. Run `python backend/app.py` from the repository root.

- [Launch and configuration](../README.md#launch)
- [Complete API reference](../docs/catalog.md#api)
- [All services and implementation limits](../docs/implementation.md)
- [Data contracts, sources and reports](../docs/catalog.md#data)
- [Architecture](../README.md#architecture)

`services/analysis.py` is the cached entry point shared by HTTP requests, assistant tools and reports. Normalized harmonized features drive scoring; physical harmonized features explain results; processed Earth data supports rover filtering and refinement. PCA/K-means and post-hoc reference-site checks provide additional views without modifying the similarity score.

See `utils/config.py` for paths, feature weights, targets, quality flags, server settings and the Groq model. Path and server overrides must be in the process environment before startup; the minimal `.env` reader runs later and is intended here for Groq settings.

## Data contract

Every harmonized DataFrame has `latitude`, `longitude`, nine features normalized 0–1 on a scale shared by all bodies (`elevation`, `slope`, `roughness`, `relief`, `temperature_day`, `temperature_night`, `albedo`, `thermal_inertia`, `mineral_index`) and a `quality_flags` bitmask. Missing values are `NaN`. Flag meanings and per-body coverage are in [`data_ready/harmonized/validation_report.md`](../data_ready/harmonized/validation_report.md).

## Quick checks

```bash
curl http://127.0.0.1:5050/api/targets
curl http://127.0.0.1:5050/api/status
curl -X POST http://127.0.0.1:5050/api/similarity \
     -H "Content-Type: application/json" -d '{"planet":"mars","location":"Jezero Crater"}'
```
