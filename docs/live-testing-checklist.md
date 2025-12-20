# Live Testing Checklist

## Pre-Flight Checks ✅

- [x] D/D* computation validated
- [x] Regime classification validated
- [x] Decodability persistence fixed
- [x] State endpoint working
- [x] UI components wired

## Live Detection Test Plan

### Step 1: Monitor Live Detection
1. Start engine (if not running)
2. Watch for new detections via `/v1/stream` or UI
3. Verify detection events include decodability metrics

### Step 2: Verify Manifest Persistence
1. Check newly created manifest files
2. Confirm `metrics.decodability` exists in manifest
3. Verify D/D* values are reasonable (not all null/zero)

### Step 3: Validate UI Display
1. Check `/tracks` page for new tracks
2. Verify decodability block appears in TrackCard
3. Confirm D-score visualization works in Chart.tsx
4. Check regime colors (scripted=green, organic=red, transitional=yellow)

### Step 4: State Endpoint Validation
1. Verify `/v1/state` returns D/D* arrays
2. Check regime distribution (should see all 3 types)
3. Confirm entropy/SNR values are computed

## Expected Results

### New Detections Should Have:
- `metrics.decodability.dScore`: number (not null)
- `metrics.decodability.regime`: 'scripted' | 'organic' | 'transitional'
- `metrics.decodability.entropy`: number
- `metrics.decodability.snr`: number

### UI Should Show:
- Decodability block in track detail view
- D-score line series (when toggle enabled)
- Regime color coding
- D* threshold display

## Troubleshooting

### If Decodability Missing:
1. Check engine logs for detection events
2. Verify `PowerTrackDetector.flagCandidate()` receives price context
3. Check manifest file for `metrics.decodability` field
4. Verify orchestration is using updated `writeLagManifest()`

### If Values Seem Wrong:
1. Check D-score calculation (should be z-scored)
2. Verify regime classification thresholds (D vs D*)
3. Check entropy/SNR computation in analytics module

## Success Criteria

✅ New detections include decodability in manifests
✅ UI displays decodability metrics correctly
✅ State endpoint computes D/D* for live data
✅ Regime classification shows all 3 types
✅ No errors in logs

