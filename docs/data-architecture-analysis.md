# Data Architecture Analysis & Recommendations

## Current State

### Storage Patterns

1. **Orchestration Outputs:**
   - Path: `/app/data/storage/pipeline_outputs/{SYMBOL}/{YYYY}/{MM}/{DD}/{track}/lag_manifest.json`
   - Minute bars: `/app/data/storage/minute_bars/{SYMBOL}/{YYYY}/{MM}/{DD}/{symbol}_minute_{date}.json` (JSON format)
   - Second bars: `/app/data/storage/second_bars/{SYMBOL}/{YYYY}/{MM}/{DD}/{symbol}_second_{date}.json` (JSON format)

2. **Engine Expectations:**
   - Minute bars CSV: `/app/data/data/polygon_min/{SYMBOL}.csv` (CSV format, single file per symbol)
   - Manifests: Scans multiple paths:
     - `/app/data/data/power_tracks/{SYMBOL}/{track}/lag_manifest.json`
     - `/app/data/pipeline_outputs/{SYMBOL}/{YYYY}/{MM}/{DD}/{track}/lag_manifest.json`
     - `/app/data/storage/pipeline_outputs/{SYMBOL}/{YYYY}/{MM}/{DD}/{track}/lag_manifest.json`

### Critical Issues

#### 1. **Minute Bars Format Mismatch** ⚠️
- **Problem:** Orchestration stores JSON (`{symbol}_minute_{date}.json`), engine expects CSV (`{SYMBOL}.csv`)
- **Impact:** Backfill can't find minute bars, `/v1/state` can't load historical data
- **Current Workaround:** Engine falls back to REST API, but this doesn't help backfill

#### 2. **Data Path Fragmentation** ⚠️
- **Problem:** Minute bars stored per-date in nested directories, engine expects single CSV per symbol
- **Impact:** Inefficient lookups, no consolidation
- **Current Workaround:** Engine only uses CSV if it exists, otherwise REST fallback

#### 3. **Manifest Scanning Inefficiency** ⚠️
- **Problem:** `listAllTracks()` recursively scans filesystem for manifests (multiple paths)
- **Impact:** Slow with thousands of tracks, no indexing
- **Current Workaround:** Works but scales poorly

#### 4. **Decodability Persistence Gap** ⚠️
- **Problem:** Decodability computed during detection but not always persisted to manifest
- **Impact:** Historical tracks miss decodability unless backfilled
- **Current Status:** New detections should persist, but need to verify

#### 5. **Missing Data Consolidation** ⚠️
- **Problem:** No process to convert JSON minute bars → CSV format
- **Impact:** Historical backfill requires manual CSV creation
- **Current Workaround:** Accept that historical tracks won't have decodability

## Recommendations

### Immediate Fixes (Priority 1)

1. ✅ **Sync Minute Bars Format**
   - Option B shipped: `FilesystemLoader.loadMinuteBars()` falls back to the JSON directories emitted by the data pipeline (`storage/minute_bars/**`). No CSV consolidation is required as long as the JSON bundles exist (see `docs/data-architecture.md#minute-bars`).
   - A helper script (`power-tracks-data/scripts/consolidate_minute_bars.py`) now converts those JSON shards into `data/polygon_min/{SYMBOL}.csv` files for operators who still need the legacy CSV layout (e.g., `backfillDecodability.ts`).

2. **Ensure Decodability Persistence**
   - Verify `PowerTrackDetector` writes decodability to manifest during detection
   - Add validation to confirm persistence

3. ✅ **Document Data Lifecycle**
   - Added `docs/data-architecture.md` covering storage paths, artifact lifecycles, and the decodability guarantees enforced by `PowerTrackStorage`.

### Medium-Term Improvements (Priority 2)

4. ✅ **Optimize Manifest Scanning**
   - The daemon now keeps the SQLite snapshot store hydrated via `FilesystemLoader.ensureSnapshotsHydrated()`, which calls `TrackSnapshotStore.getSymbolStats()` and only rescans manifests when a symbol’s index is empty or stale. Snapshot refresh timestamps are cached (`SNAPSHOT_REFRESH_TTL_MS`) so `/v1/tracks` no longer performs costly recursive scans on every request.

5. ✅ **Unify Data Paths**
   - `loadEngineConfig()` now autodetects the shared storage root (ENV, config paths, or `../power-tracks-data/storage`) and backfills missing `detector.storage` settings so the engine, data pipeline, and Studio reference the same directories without manual edits. The new behavior is documented in `docs/data-architecture.md#shared-root-discovery`.

### Long-Term Enhancements (Priority 3)

6. ✅ **Data Archive Strategy**
   - Retention/backup cadence documented in `docs/data-architecture.md#data-retention--monitoring` (90-day online ledger, 180-day artifact window, JSON minute-bar compression), plus sample cron helpers for gzipping/cold storage.

7. ✅ **Performance Monitoring**
   - Same section captures disk-usage logging, Prometheus/node-exporter hooks, and snapshot-count alerts so operators can track growth and react before storage exhaustion.

## Proposed Fixes

### Fix 1: Update Engine to Read JSON Minute Bars

Modify `FilesystemLoader.loadMinuteBars()` to:
1. Check for CSV first (existing behavior)
2. Fallback to JSON files: `storage/minute_bars/{SYMBOL}/{YYYY}/{MM}/{DD}/{symbol}_minute_{date}.json`
3. Consolidate multiple date files if needed

### Fix 2: Verify Decodability Persistence

Add test to confirm:
- Detection writes decodability to manifest
- Manifest path matches orchestration output path
- Decodability survives manifest round-trip

### Fix 3: Add Data Path Documentation

Create `docs/data-architecture.md` explaining:
- Storage conventions
- Path structures
- Data formats
- Access patterns

## Validation Steps

1. ✅ Verify orchestration stores minute bars as JSON
2. ⏳ Test engine can read JSON minute bars
3. ⏳ Verify decodability persists during detection
4. ⏳ Test backfill with JSON minute bars
5. ⏳ Measure `listAllTracks` performance with 1000+ tracks
