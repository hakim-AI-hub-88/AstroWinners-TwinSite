# Backend

Flask API and page server. Run it from the `app/` folder: `python backend/app.py`.

| Module | Role | Extend by |
|---|---|---|
| `app.py` | `create_app()`: registers blueprints, serves `templates/index.html`, preloads data | Registering new blueprints |
| `routes/similarity_routes.py` | Thin HTTP layer: validates input, calls services, returns JSON | Adding endpoints |
| `services/data_loader.py` | Reads the harmonized normalized CSVs once (cached, float32). Also `extract_target_window()` and `target_profile()`. | Adding bodies or formats |
| `services/similarity_engine.py` | `compute(SimilarityRequest) -> dict`, **placeholder** for now | The weighted similarity model (next step) |
| `utils/config.py` | Paths, targets (lat/lon, window), feature list, body radii, host/port | Adding targets or features |

## Data contract

Every DataFrame has these columns:
- `latitude`, `longitude`
- the 9 features, normalized 0–1 on a scale shared by all bodies: `elevation`, `slope`, `roughness`, `relief`, `temperature_day`, `temperature_night`, `albedo`, `thermal_inertia`, `mineral_index`
- `quality_flags` (bitmask; see `pipeline/data_ready/harmonized/validation_report.md`)

Missing values are `NaN`.

## Quick checks

```bash
curl http://127.0.0.1:5050/api/targets
curl http://127.0.0.1:5050/api/status
curl -X POST http://127.0.0.1:5050/api/similarity \
     -H "Content-Type: application/json" -d '{"planet":"mars","location":"Jezero Crater"}'
```
