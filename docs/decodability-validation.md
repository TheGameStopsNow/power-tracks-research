# D/D* & Regime Classification Validation

## Overview

This document summarizes the validation status of the D/D* decodability scoring and regime classification system.

## Smoke Test Results

Run the smoke test:
```bash
npm run smoke:decodability
```

### Test Results

✅ **All tests passing** as of validation run:

1. **/v1/state D/D* computation**
   - Computes D scores for all bars (307 valid out of 308 bars)
   - Computes entropy, SNR, and D* threshold
   - Returns regime classifications (scripted/organic/transitional)
   - Sample: 3 regimes detected (scripted: 79, organic: 97, transitional: 131)

2. **/v1/tracks decodability metrics**
   - Returns track structure correctly
   - Extracts decodability from manifests when available
   - Note: Historical tracks without backfill will have null decodability (expected)

3. **Regime classification logic**
   - Correctly classifies bars based on D score and D* threshold
   - Regimes: scripted (D > D*), organic (D < D*), transitional (otherwise)

## Data Flow

### Live Data (Real-time)
- `/v1/state`: Computes rolling D/D* for each bar using 60-bar windows
- D scores computed from spectral bandpower, entropy, SNR, varint success
- Regime classification based on D vs D* threshold and slope

### Historical Tracks
- `PowerTrackDetector`: Computes D/D* during detection (new tracks)
- `backfillDecodability.ts`: Can backfill historical tracks if minute bars CSV available
- Manifests store decodability in `metrics.decodability`

### UI Display
- `Chart.tsx`: D-score line series (toggleable), D* threshold overlay
- `TrackCard`: Decodability metrics block (D, regime, entropy, SNR)
- `SummaryCard`: D* threshold display

## Backfill Prerequisites

Historical backfill requires minute bars CSV:
- Path: `{DATA_PATH}/data/polygon_min/{SYMBOL}.csv`
- Format: CSV with columns `ts, open, high, low, close, volume`
- Must cover detection window (window_start to window_end)

If CSV not available:
- Historical tracks will have null decodability (expected)
- New detections automatically compute D/D* during detection
- No action needed for new tracks

## Next Steps

1. ✅ D/D* computation validated
2. ✅ Regime classification validated
3. ✅ UI components wired
4. ⏸️ Paused: Rolling entropy/MI curves enhancement (ready for next milestone)
5. ⏸️ Paused: Options/GEX enrichment (ready for next milestone)

## Validation Commands

```bash
# Smoke test
npm run smoke:decodability

# Check state endpoint
curl http://localhost:8001/v1/state?symbol=GME&date=today | jq '{D: (.D | length), regimes: (.state | unique)}'

# Check tracks endpoint
curl 'http://localhost:8001/v1/tracks?symbol=GME&limit=3' | jq '.tracks[] | {trackId, decodability}'
```
