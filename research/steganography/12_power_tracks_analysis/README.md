# Phase 12: Power Tracks Binary Protocol Steganalysis

## Overview

Analyzes the Power Tracks binary frame format for steganographic capacity and hidden patterns.

## Key Finding

**~500 bits of hiding capacity per frame** due to varint encoding inefficiency.

## Structure

```
12_power_tracks_analysis/
├── README.md              # This file
├── scripts/
│   ├── power_tracks_steganalysis.py   # Main analysis
│   ├── varint_extractor.py            # Extract slack bits
│   └── frame_decoder.py               # Decode real frames
├── data/
│   └── extracted_frames/              # Decoded frames from engine
├── results/
│   ├── power_tracks_report.md         # Main findings
│   └── *.json                         # Raw analysis data
└── docs/
    └── findings_summary.md            # Interpretation
```

## Scripts

### 1. power_tracks_steganalysis.py
Analyzes frame structure for hiding capacity.

### 2. varint_extractor.py  
Extracts potential hidden bits from varint slack.

### 3. frame_decoder.py
Decodes actual frames from the engine and compares to theoretical.

## Results

| Metric | Value |
|--------|-------|
| Mean frame size | 150 bytes |
| Mean hiding capacity | 499 bits |
| Entropy ratio | 0.33-0.53 |
