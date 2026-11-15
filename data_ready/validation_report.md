# Validation report - Earth / Mars / Moon features

Generated 2026-11-14T19:55:45+00:00.

## Overview

| Body | Resolution | Rows written | Available features | Missing features |
|---|---|---|---|---|
| earth | 0.01 deg Atacama box (300 x 400) | 120,000 | 7/9 | thermal_inertia, mineral_index |
| mars | 0.5 deg global (360 x 720) | 259,200 | 9/9 | - |
| moon | 0.5 deg global (360 x 720) | 259,200 | 7/9 | thermal_inertia, mineral_index |

## Earth

| Feature | Units | Valid % | Min | Mean | Max | Source |
|---|---|---|---|---|---|---|
| elevation | m | 91.67 | 624.5085 | 3279.3086 | 6387.5024 | NASADEM_HGT (30 m) via Earth pipeline |
| slope | degree | 91.67 | 0.0 | 7.3722 | 38.5669 | NASADEM_HGT (30 m) via Earth pipeline |
| roughness | m | 91.67 | 0.0 | 27.9622 | 215.0235 | NASADEM_HGT (30 m) via Earth pipeline |
| relief | m | 91.67 | 0.0 | 124.6207 | 883.0 | NASADEM_HGT (30 m) via Earth pipeline |
| temperature_day | K | 99.81 | 269.32 | 298.6627 | 315.15 | MODIS MOD11A2 LST day (~10:30 local), via Earth pipeline, degC -> K |
| temperature_night | K | 99.81 | 256.9 | 277.3307 | 296.44 | MODIS MOD11A2 LST night (~22:30 local), via Earth pipeline, degC -> K |
| albedo | 1 | 100.0 | 0.16 | 0.2033 | 0.23 | NASA POWER ALLSKY_SRF_ALB annual climatology (1 deg) |
| thermal_inertia | J m-2 K-1 s-1/2 | 0.0 |  |  |  | MISSING - no dataset yet |
| mineral_index | wt% | 0.0 |  |  |  | MISSING - no dataset yet |

Quality flags (cells): TEMP_FIXED_LOCAL_TIME=119,772, GAP_FILLED=7,162, COARSE_SOURCE=120,000, WATER=184

Processing steps:
- Read atacama_unified.h5 (cleaned, QA-masked, gap-filled 0.01 deg grid from the Earth pipeline)
- LST degC -> K
- NASA POWER albedo: 1 deg cell value assigned to each 0.01 deg cell

Notes:
- thermal_inertia: no Earth product yet (could be derived from albedo + LST amplitude)
- mineral_index: needs an Fe abundance source; ASTER GED (silica) still not downloaded

## Mars

| Feature | Units | Valid % | Min | Mean | Max | Source |
|---|---|---|---|---|---|---|
| elevation | m | 100.0 | -7694.5469 | -721.1071 | 20890.6406 | MGS MOLA MEGDR megt90n000eb (16 ppd, ~3.7 km) |
| slope | degree | 99.44 | 0.0054 | 1.1977 | 23.454 | MGS MOLA MEGDR megt90n000eb (16 ppd, ~3.7 km) |
| roughness | m | 100.0 | 0.4319 | 117.4317 | 3211.6616 | MGS MOLA MEGDR megt90n000eb (16 ppd, ~3.7 km) |
| relief | m | 100.0 | 2.0 | 463.8893 | 9489.0 | MGS MOLA MEGDR megt90n000eb (16 ppd, ~3.7 km) |
| temperature_day | K | 61.67 | 217.7118 | 271.8316 | 302.666 | ESTIMATED: linearised diurnal heat model from TES albedo + thermal inertia (equinox, no atmosphere) |
| temperature_night | K | 61.67 | 135.351 | 166.1694 | 201.5602 | ESTIMATED: linearised diurnal heat model from TES albedo + thermal inertia (equinox, no atmosphere) |
| albedo | 1 | 100.0 | 0.06 | 0.1987 | 0.32 | MGS TES bolometric albedo (8 ppd) |
| thermal_inertia | J m-2 K-1 s-1/2 | 61.67 | 32.7143 | 224.1953 | 795.75 | MGS TES thermal inertia (8 ppd, 60 N - 50 S only) |
| mineral_index | wt% | 58.18 | 10.632 | 14.4668 | 19.301 | Mars Odyssey GRS Fe (5 deg smoothed, wt%) |

Quality flags (cells): TEMP_DAY_ESTIMATED=159,840, TEMP_NIGHT_ESTIMATED=159,840, COARSE_SOURCE=150,800

Processing steps:
- MOLA: big-endian int16 metres -> mean/std/max-min per 0.5 deg cell; slope at 16 ppd
- TES: float32 maps, out-of-range values (TI = 0) -> NaN, mean per cell
- GRS: 9999.999 -> NaN, 5 deg bins copied to the 0.5 deg cells they contain
- Temperatures: modelled where both albedo and thermal inertia exist

Notes:
- Silicon (si_sr_5x5) downloaded but not in the schema; keep for later mineral ratios.

## Moon

| Feature | Units | Valid % | Min | Mean | Max | Source |
|---|---|---|---|---|---|---|
| elevation | m | 100.0 | -8269.5938 | -519.2021 | 9690.1406 | LRO LOLA LDEM_16 (16 ppd, ~1.9 km) |
| slope | degree | 99.44 | 0.0334 | 5.3577 | 28.014 | LRO LOLA LDEM_16 (16 ppd, ~1.9 km) |
| roughness | m | 100.0 | 1.2624 | 283.5551 | 1714.536 | LRO LOLA LDEM_16 (16 ppd, ~1.9 km) |
| relief | m | 100.0 | 6.0 | 1067.1068 | 6391.5 | LRO LOLA LDEM_16 (16 ppd, ~1.9 km) |
| temperature_day | K | 100.0 | 40.2316 | 337.4879 | 405.1021 | Diviner GCP daily max where downloaded (bands: 00n10n, 90s80s); elsewhere ESTIMATED 392 K x cos(lat)^0.25 |
| temperature_night | K | 72.22 | 20.1596 | 91.4444 | 143.1945 | Diviner GCP nightly min > Diviner L3 regolith T at 00:30 > constant 95 K (|lat| <= 60) |
| albedo | 1 | 100.0 | 0.0004 | 0.12 | 0.6963 | PROXY: LROC WAC 643 nm normalised reflectance (16 ppd), rescaled to a global mean of 0.12 (bolometric albedo) |
| thermal_inertia | J m-2 K-1 s-1/2 | 0.0 |  |  |  | MISSING - no dataset yet |
| mineral_index | wt% | 0.0 |  |  |  | MISSING - no dataset yet |

Quality flags (cells): TEMP_DAY_ESTIMATED=230,400, TEMP_NIGHT_ESTIMATED=56,443, TEMP_FIXED_LOCAL_TIME=101,957, ALBEDO_PROXY=259,200

Processing steps:
- LOLA: int16 x 0.5 + 1737.4 km (label) - 1737.4 km = height; stats per 0.5 deg cell
- WAC: float32 with attached label, ISIS nulls/negatives -> NaN, mean per cell, rescaled
- Temperatures: GCP tbol (-9999 -> NaN) max over 10-14 h / min over 18-06 h; fall-backs flagged

Notes:
- Temperature source coverage (% of cells): {'day_measured_pct': 11.11, 'night_gcp_pct': 11.11, 'night_l3_pct': 39.34, 'night_constant_pct': 21.78}

## Model checks

```json
{
  "mars": {
    "site": "jezero_Ls90.txt (18.4 N, 77.5 E)",
    "reference": "Mars Climate Database v6.2, Ls 90 (validation only, not an input)",
    "model_day_max_K": 276.1,
    "model_night_min_K": 179.2,
    "tes_albedo": 0.183,
    "tes_thermal_inertia": 301.9,
    "reference_day_max_K": 276.0,
    "reference_night_min_K": 193.8,
    "reference_albedo": 0.171,
    "reference_thermal_inertia": 275.1
  },
  "moon": {
    "temperature_sources_pct": {
      "day_measured_pct": 11.11,
      "night_gcp_pct": 11.11,
      "night_l3_pct": 39.34,
      "night_constant_pct": 21.78
    },
    "day_max_check": {
      "reference": "Diviner GCP measured daily maximum, |lat| <= 10 deg",
      "cells": 14400,
      "measured_mean_K": 391.5,
      "constant_model_mean_K": 391.5,
      "mean_abs_difference_K": 2.0
    }
  }
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
