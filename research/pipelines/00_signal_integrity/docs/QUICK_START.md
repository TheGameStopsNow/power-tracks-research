# Quick Start Guide - Using Your Polygon API Key

## Overview

The reproducibility bundle works with your Polygon API key to fetch sample data. **You don't need to share raw Polygon data** - only the decoded Power Tracks data can be shared.

## Step 1: Set Your API Key

Simply copy and paste your Polygon API key:

```bash
export POLYGON_API_KEY='your_polygon_API_KEY='your_polygon_api_key_here'
```

Or use it inline:

```bash
POLYGON_API_KEY='your_key' python scripts/fetch_sample_data.py
```

## Step 2: Fetch Sample Data

```bash
python scripts/fetch_sample_data.py \
    --symbol GME \
    --date 2024-05-13
```

This will:
- Fetch data from Polygon API
- Save to `sample_2024-05-13/raw_ticks/`
- Generate SHA256 checksums
- Update the manifest

## Step 3: Run Decoding Pipeline

```bash
./scripts/pipeline_verify.sh \
    --input sample_2024-05-13/raw_ticks \
    --output output
```

This creates:
- `output/frames.bin` - Decoded frames (CAN BE SHARED)
- `output/price_paths.csv` - Price paths (CAN BE SHARED)

## Step 4: Share Decoded Data

**✅ You CAN share:**
- `output/frames.bin` (decoded frames)
- `output/price_paths.csv` (price paths)
- All scripts, tools, documentation
- Validation reports

**❌ You CANNOT share:**
- `sample_2024-05-13/raw_ticks/` (raw Polygon data)

## Why This Works

- **Raw Polygon data** = Proprietary/licensed (cannot share)
- **Decoded Power Tracks** = Derived/transformed data (can share)

The decoded data is created by your decoding pipeline and contains completely different numbers than the raw Polygon data.

## Verification

Others can verify your decoded data without needing Polygon API access:

```bash
python scripts/verify_reproducibility.py \
    --sample-dir output \
    --no-checksums  # Skip raw data checksums
```

## Example Workflow

```bash
# 1. Set API key (you)
export POLYGON_API_KEY='your_key'

# 2. Fetch data
python scripts/fetch_sample_data.py

# 3. Decode frames
./scripts/pipeline_verify.sh --input sample_2024-05-13/raw_ticks --output decoded

# 4. Share decoded data only
tar -czf shared-bundle.tar.gz \
    decoded/ \
    scripts/ \
    tools/ \
    tests/ \
    *.md

# 5. Others verify without API key
tar -xzf shared-bundle.tar.gz
python scripts/verify_reproducibility.py --sample-dir decoded --no-checksums
```

## Questions?

See [DATA_SHARING.md](DATA_SHARING.md) for detailed guidelines.


