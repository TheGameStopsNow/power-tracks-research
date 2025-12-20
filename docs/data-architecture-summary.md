# Data Architecture: Current State & Recommendations

## Summary

After analyzing the data handling, storage, and access patterns, here's what I found:

### ✅ What Works Well

1. **Manifest Discovery**: Engine successfully scans multiple paths to find manifests
2. **Live Data**: REST fallback for minute bars works for real-time data
3. **State Computation**: `/v1/state` correctly computes D/D* from live data
4. **Decodability Computation**: D/D* is computed during detection in `PowerTrackDetector`

### ⚠️ Gaps Identified

1. **Decodability Persistence Gap**
   - **Status:** Computed in `PowerTrackDetector.flagCandidate()` but may not be written to manifest
   - **Need:** Verify orchestration's `writeLagManifest()` includes `metrics.decodability`
   - **Impact:** Historical tracks won't have decodability even if computed

2. **Minute Bars Format Mismatch**
   - **Status:** Orchestration stores JSON (`{symbol}_minute_{date}.json`), engine expects CSV (`{SYMBOL}.csv`)
   - **Current State:** Directory exists but empty (no orchestration runs have written minute bars yet)
   - **Impact:** Low - REST fallback works for live data, backfill just needs CSV

3. **Manifest Scanning Performance**
   - **Status:** Works but recursively scans filesystem (multiple paths)
   - **Current Scale:** Acceptable (< 1000 tracks)
   - **Future:** Consider SQLite index if scale increases significantly

## Recommendations

### Immediate (Priority 1)

1. **Verify Decodability Persistence**
   - Check if orchestration captures detector output and writes `metrics.decodability` to manifest
   - If missing, update `writeLagManifest()` to include decodability from detector candidate

2. **Test Live Detection**
   - Run engine on fresh trading window
   - Verify new detections include decodability in manifests
   - Confirm UI displays decodability correctly

### Medium-Term (Priority 2)

3. **Add JSON Minute Bars Support** (Optional)
   - If orchestration writes JSON minute bars, add fallback in `loadMinuteBars()`
   - Enables backfill without CSV conversion

4. **Document Data Lifecycle**
   - When/how decodability is computed
   - When/how it's persisted
   - When/how backfill works

### Long-Term (Priority 3)

5. **Optimize Manifest Scanning**
   - Add SQLite index for track lookups (if scale increases)
   - Or: Generate manifest index during orchestration

6. **Data Archive Strategy**
   - When to archive old tracks
   - Compression/cleanup policies

## Current Architecture Status

**✅ Ready for Live Testing**

The core analytics are working:
- D/D* computation validated ✅
- Regime classification validated ✅
- State endpoint working ✅
- UI components wired ✅

**Remaining:** Verify decodability persists during detection (likely just needs orchestration update)

## Next Steps

1. ✅ Analyze data architecture (done)
2. ⏳ Verify decodability persistence in orchestration
3. ⏳ Test live detection end-to-end
4. ⏳ Confirm UI displays correctly
5. ⏳ Proceed with enhancements (entropy/MI curves, etc.)

