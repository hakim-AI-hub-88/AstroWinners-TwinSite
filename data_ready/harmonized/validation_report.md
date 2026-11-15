# Validation report - Earth / Mars / Moon features

Generated 2026-11-15T10:31:32+00:00.

## Overview

| Body | Resolution | Rows written | Available features | Missing features |
|---|---|---|---|---|
| earth | 0.1 deg (~11.1 km) Atacama box (30 x 40) | 1,200 | 7/9 | thermal_inertia, mineral_index |
| mars | 0.1875 deg (~11.1 km) global (960 x 1920) | 1,843,200 | 9/9 | - |
| moon | 0.375 deg (~11.4 km) global (480 x 960) | 460,800 | 7/9 | thermal_inertia, mineral_index |
| merzouga | 0.1 deg (~11.1 km) Merzouga - Erg Chebbi (Morocco) box (20 x 20) | 400 | 7/9 | thermal_inertia, mineral_index |

## Earth

| Feature | Units | Valid % | Min | Mean | Max | Source |
|---|---|---|---|---|---|---|
| elevation | m | 91.67 | 662.1567 | 3279.3086 | 5221.7212 | NASADEM 30 m averaged to 120x120 px (~3.7 km), 3x3 px cells |
| slope | degree | 91.67 | 0.0037 | 2.4288 | 9.5967 | NASADEM 30 m averaged to 120x120 px (~3.7 km), 3x3 px cells |
| roughness | m | 91.67 | 0.1313 | 130.6675 | 598.8158 | NASADEM 30 m averaged to 120x120 px (~3.7 km), 3x3 px cells |
| relief | m | 91.67 | 0.4143 | 406.3932 | 1652.9912 | NASADEM 30 m averaged to 120x120 px (~3.7 km), 3x3 px cells |
| temperature_day | K | 99.92 | 277.3995 | 298.6603 | 313.3216 | MODIS MOD11A2 LST day (~10:30 local), via Earth pipeline, degC -> K |
| temperature_night | K | 99.92 | 264.3083 | 277.3339 | 290.3434 | MODIS MOD11A2 LST night (~22:30 local), via Earth pipeline, degC -> K |
| albedo | 1 | 100.0 | 0.16 | 0.2033 | 0.23 | NASA POWER ALLSKY_SRF_ALB annual climatology (1 deg) |
| thermal_inertia | J m-2 K-1 s-1/2 | 0.0 |  |  |  | MISSING - no dataset yet |
| mineral_index | wt% | 0.0 |  |  |  | MISSING - no dataset yet |

Quality flags (cells): TEMP_FIXED_LOCAL_TIME=1,199, GAP_FILLED=407, COARSE_SOURCE=1,200, WATER=42

Processing steps:
- Read atacama_unified.h5 (cleaned, QA-masked, gap-filled 0.01 deg grid from the Earth pipeline)
- LST degC -> K
- NASA POWER albedo: 1 deg cell value assigned to each 0.01 deg cell
- HARMONIZED: NASADEM block-mean x120 -> 3.7 km pixels; slope at that baseline; roughness/relief over 3x3 px; other features = mean of 10x10 fine cells

Notes:
- thermal_inertia: no Earth product yet (could be derived from albedo + LST amplitude)
- mineral_index: needs an Fe abundance source; ASTER GED (silica) still not downloaded

## Mars

| Feature | Units | Valid % | Min | Mean | Max | Source |
|---|---|---|---|---|---|---|
| elevation | m | 100.0 | -8043.8887 | -721.1069 | 21145.666 | MGS MOLA MEGDR megt90n000eb (16 ppd, ~3.7 km) |
| slope | degree | 99.58 | 0.0 | 1.2016 | 48.5878 | MGS MOLA MEGDR megt90n000eb (16 ppd, ~3.7 km) |
| roughness | m | 100.0 | 0.0 | 55.4812 | 1837.2922 | MGS MOLA MEGDR megt90n000eb (16 ppd, ~3.7 km) |
| relief | m | 100.0 | 0.0 | 167.1241 | 6017.0 | MGS MOLA MEGDR megt90n000eb (16 ppd, ~3.7 km) |
| temperature_day | K | 61.35 | 215.908 | 272.076 | 309.0743 | ESTIMATED: linearised diurnal heat model from TES albedo + thermal inertia (equinox, no atmosphere) |
| temperature_night | K | 61.35 | 133.7657 | 166.1142 | 204.1235 | ESTIMATED: linearised diurnal heat model from TES albedo + thermal inertia (equinox, no atmosphere) |
| albedo | 1 | 100.0 | 0.06 | 0.1986 | 0.32 | MGS TES bolometric albedo (8 ppd) |
| thermal_inertia | J m-2 K-1 s-1/2 | 61.35 | 26.0 | 223.3819 | 800.0 | MGS TES thermal inertia (8 ppd, 60 N - 50 S only) |
| mineral_index | wt% | 58.15 | 10.632 | 14.4674 | 19.301 | Mars Odyssey GRS Fe (5 deg smoothed, wt%) |

Quality flags (cells): TEMP_DAY_ESTIMATED=1,130,878, TEMP_NIGHT_ESTIMATED=1,130,878, COARSE_SOURCE=1,071,831

Processing steps:
- MOLA: big-endian int16 metres -> mean/std/max-min per 0.5 deg cell; slope at 16 ppd
- TES: float32 maps, out-of-range values (TI = 0) -> NaN, mean per cell
- GRS: 9999.999 -> NaN, 5 deg bins copied to the 0.5 deg cells they contain
- Temperatures: modelled where both albedo and thermal inertia exist
- HARMONIZED: DEM block-mean x1 -> 3.7 km pixels; slope at that baseline; roughness/relief over 3x3 px

Notes:
- Silicon (si_sr_5x5) downloaded but not in the schema; keep for later mineral ratios.

## Moon

| Feature | Units | Valid % | Min | Mean | Max | Source |
|---|---|---|---|---|---|---|
| elevation | m | 100.0 | -8451.6807 | -519.2021 | 9922.6113 | LRO LOLA LDEM_16 (16 ppd, ~1.9 km) |
| slope | degree | 99.58 | 0.0187 | 4.5569 | 29.7139 | LRO LOLA LDEM_16 (16 ppd, ~1.9 km) |
| roughness | m | 100.0 | 0.5318 | 207.8171 | 1472.9114 | LRO LOLA LDEM_16 (16 ppd, ~1.9 km) |
| relief | m | 100.0 | 1.75 | 623.2515 | 4861.0 | LRO LOLA LDEM_16 (16 ppd, ~1.9 km) |
| temperature_day | K | 100.0 | 40.2316 | 337.4991 | 405.1021 | Diviner GCP daily max where downloaded (bands: 00n10n, 90s80s); elsewhere ESTIMATED 392 K x cos(lat)^0.25 |
| temperature_night | K | 72.29 | 20.1596 | 91.4729 | 143.1945 | Diviner GCP nightly min > Diviner L3 regolith T at 00:30 > constant 95 K (|lat| <= 60) |
| albedo | 1 | 100.0 | 0.0004 | 0.12 | 0.9812 | PROXY: LROC WAC 643 nm normalised reflectance (16 ppd), rescaled to a global mean of 0.12 (bolometric albedo) |
| thermal_inertia | J m-2 K-1 s-1/2 | 0.0 |  |  |  | MISSING - no dataset yet |
| mineral_index | wt% | 0.0 |  |  |  | MISSING - no dataset yet |

Quality flags (cells): TEMP_DAY_ESTIMATED=408,960, TEMP_NIGHT_ESTIMATED=124,655, TEMP_FIXED_LOCAL_TIME=156,625, ALBEDO_PROXY=460,800

Processing steps:
- LOLA: int16 x 0.5 + 1737.4 km (label) - 1737.4 km = height; stats per 0.5 deg cell
- WAC: float32 with attached label, ISIS nulls/negatives -> NaN, mean per cell, rescaled
- Temperatures: GCP tbol (-9999 -> NaN) max over 10-14 h / min over 18-06 h; fall-backs flagged
- HARMONIZED: DEM block-mean x2 -> 3.79 km pixels; slope at that baseline; roughness/relief over 3x3 px

Notes:
- Temperature source coverage (% of cells): {'day_measured_pct': 11.25, 'night_gcp_pct': 11.25, 'night_l3_pct': 33.99, 'night_constant_pct': 27.05}

## Merzouga

| Feature | Units | Valid % | Min | Mean | Max | Source |
|---|---|---|---|---|---|---|
| elevation | m | 100.0 | 546.2193 | 827.302 | 1504.3516 | NASADEM 30 m averaged to 120x120 px (~3.7 km), 3x3 px cells |
| slope | degree | 100.0 | 0.0948 | 0.4785 | 3.7563 | NASADEM 30 m averaged to 120x120 px (~3.7 km), 3x3 px cells |
| roughness | m | 100.0 | 3.9393 | 24.8085 | 210.3201 | NASADEM 30 m averaged to 120x120 px (~3.7 km), 3x3 px cells |
| relief | m | 100.0 | 12.8087 | 76.9944 | 591.7391 | NASADEM 30 m averaged to 120x120 px (~3.7 km), 3x3 px cells |
| temperature_day | K | 100.0 | 289.5622 | 296.881 | 302.4228 | MODIS MOD11A2 LST day (~10:30 local), via Earth pipeline, degC -> K |
| temperature_night | K | 100.0 | 284.0938 | 289.5216 | 292.7986 | MODIS MOD11A2 LST night (~22:30 local), via Earth pipeline, degC -> K |
| albedo | 1 | 100.0 | 0.25 | 0.28 | 0.31 | NASA POWER ALLSKY_SRF_ALB annual climatology (1 deg) |
| thermal_inertia | J m-2 K-1 s-1/2 | 0.0 |  |  |  | MISSING - no dataset yet |
| mineral_index | wt% | 0.0 |  |  |  | MISSING - no dataset yet |

Quality flags (cells): TEMP_FIXED_LOCAL_TIME=400, GAP_FILLED=12, COARSE_SOURCE=400, WATER=1

Processing steps:
- Read atacama_unified.h5 (cleaned, QA-masked, gap-filled 0.01 deg grid from the Earth pipeline)
- LST degC -> K
- NASA POWER albedo: 1 deg cell value assigned to each 0.01 deg cell
- HARMONIZED: NASADEM block-mean x120 -> 3.7 km pixels; slope at that baseline; roughness/relief over 3x3 px; other features = mean of 10x10 fine cells

Notes:
- thermal_inertia: no Earth product yet (could be derived from albedo + LST amplitude)
- mineral_index: needs an Fe abundance source; ASTER GED (silica) still not downloaded
- Second Earth zone: the common 0-1 scale covers both Earth zones.

## Model checks

```json
{
  "harmonization_scales": [
    {
      "body": "earth",
      "native_pixel_km": 0.031,
      "aggregation_factor": 120,
      "common_pixel_km": 3.71,
      "cell_deg": 0.1,
      "cell_km": 11.1
    },
    {
      "body": "mars",
      "native_pixel_km": 3.704,
      "aggregation_factor": 1,
      "common_pixel_km": 3.7,
      "cell_deg": 0.1875,
      "cell_km": 11.1
    },
    {
      "body": "moon",
      "native_pixel_km": 1.895,
      "aggregation_factor": 2,
      "common_pixel_km": 3.79,
      "cell_deg": 0.375,
      "cell_km": 11.4
    }
  ]
}
```

## Quality flag bits

| Flag | Value |
|---|---|
| TEMP_DAY_ESTIMATED | 1 |
| TEMP_NIGHT_ESTIMATED | 2 |
| TEMP_FIXED_LOCAL_TIME | 4 |
| GAP_FILLED | 8 |
| ALBEDO_PROXY | 16 |
| COARSE_SOURCE | 32 |
| WATER | 64 |
