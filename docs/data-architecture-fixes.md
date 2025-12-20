# Data Architecture Fixes

## Issue Summary

After analyzing the data flow, here are the key findings:

### 1. Minute Bars Storage Gap ✅ UNDERSTOOD
- **Status:** Orchestration stores JSON (`storage/minute_bars/{SYMBOL}/{YYYY}/{MM}/{DD}/{symbol}_minute_{date}.json`)
- **Engine Expects:** CSV (`data/polygon_min/{SYMBOL}.csv`)
- **Current State:** Directory exists but empty (no orchestration runs have written minute bars yet)
- **Impact:** Low (REST fallback works for live data, backfill just needs CSV)

### 2. Decodability Persistence ⚠️ NEEDS VERIFICATION
- **Status:** Computed during detection in `PowerTrackDetector.flagCandidate()`
- **Question:** Does orchestration write it to manifest?
- **Need to verify:** Check if `writeLagManifest()` in orchestration includes decodability

### 3. Manifest Scanning ✅ WORKING BUT CAN OPTIMIZE
- **Status:** Scans multiple paths, works correctly
- **Performance:** Acceptable for now (< 1000 tracks)
- **Future:** Consider SQLite index if scale increases

## Immediate Actions

### Action 1: Verify Decodability Persistence
Check if orchestration's `writeLagManifest()` includes decodability from detector output.

### Action 2: Add JSON Minute Bars Support (Optional)
If orchestration writes JSON minute bars, add fallback in `loadMinuteBars()` to read them.

### Action 3: Document Current State
Create clear documentation of what works and what's expected.

## Proposed Changes

### Change 1: Enhance `loadMinuteBars()` to support JSON
```typescript
// Add fallback to read JSON minute bars from orchestration paths
private async loadMinuteBarsFromJson(symbol: string, date: string): Promise<MinuteBar[]> {
  const [year, month, day] = date.split('-');
  const jsonPath = path.join(
    this.basePath,
    'storage',
    'minute_bars',
    symbol,
    year,
    month,
    day,
    `${symbol.toLowerCase()}_minute_${date}.json`
  );
  if (!existsSync(jsonPath)) return [];
  
  const content = await fs.readFile(jsonPath, 'utf-8');
  const parsed = JSON.parse(content);
  if (!Array.isArray(parsed?.bars)) return [];
  
  return parsed.bars.map((bar: any) => ({
    ts: Number(bar.timestamp),
    open: Number(bar.open),
    high: Number(bar.high),
    low: Number(bar.low),
    close: Number(bar.close),
    volume: Number(bar.volume ?? 0)
  }));
}
```

### Change 2: Verify Orchestration Writes Decodability
Check `writeLagManifest()` in orchestration to ensure it includes `metrics.decodability`.

## Recommendation

**For now:**
1. ✅ Current setup works for live data (REST fallback)
2. ✅ New detections compute D/D* (need to verify persistence)
3. ⏸️ Historical backfill can wait until minute bars CSV exists

**Priority:** Verify decodability persistence during detection, then proceed with live testing.

