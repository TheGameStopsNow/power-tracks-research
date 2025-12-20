# Verification Checklist - Ensuring Accuracy

## Critical Requirements (From Pipeline Code)

### ✅ Data Type
- [x] **TICK DATA** (individual trades) - NOT minute bars
- [x] Required columns: `timestamp`, `price`
- [x] Optional columns: `volume`, `venue`, `symbol`

### ✅ Time Coverage
- [x] **Full trading day**: 4:00 AM - 8:00 PM ET
- [x] Includes premarket (4 AM - 9:30 AM ET)
- [x] Includes regular hours (9:30 AM - 4:00 PM ET)
- [x] Includes aftermarket (4 PM - 8 PM ET)

### ✅ Venue Coverage
- [x] **EDGX** (exchange code 4) - REQUIRED
- [x] **OTC** (exchange code 8) - REQUIRED (include_otc=true)
- [x] **CBOE** (exchange codes 3, 5, 6, 7) - Optional but included

### ✅ API Parameters
- [x] `include_otc=true` - REQUIRED for off-exchange trades
- [x] Polygon v3 trades endpoint (not aggregates)
- [x] Nanosecond timestamps properly converted

## Verification Steps

### 1. Check Data Format
```bash
head -5 sample_2024-05-13/raw_ticks/GME_2024-05-13_trades.csv
```
Should show: `timestamp,price,volume,venue,symbol`

### 2. Check Venue Coverage
```python
import pandas as pd
df = pd.read_csv('sample_2024-05-13/raw_ticks/GME_2024-05-13_trades.csv')
print(df['venue'].value_counts())
```
Must include: EDGX, OTC

### 3. Check Time Coverage
```python
df['ts'] = pd.to_datetime(df['timestamp'])
print(f"Start: {df['ts'].min()}")
print(f"End: {df['ts'].max()}")
```
Should span: 4:00 AM - 8:00 PM ET

### 4. Verify Against Pipeline
The data should match what `tick_loader.js` expects:
- `timestamp` column (required)
- `price` column (required)
- `venue` or `exchange` column (mapped correctly)

## Known Issues Fixed

1. ✅ **Was fetching minute bars** → Now fetches tick data
2. ✅ **Was only fetching regular hours** → Now includes premarket + aftermarket
3. ✅ **Wasn't verifying EDGX/OTC** → Now explicitly checks and maps venues
4. ✅ **Wasn't setting include_otc=true** → Now explicitly sets it

## Testing

Run with your API key:
```bash
export POLYGON_API_KEY='your_key'
python scripts/fetch_sample_data.py --symbol GME --date 2024-05-13
```

Then verify:
1. Data format matches requirements
2. EDGX and OTC trades are present
3. Time range covers full trading day
4. Can be loaded by `tick_loader.js`


