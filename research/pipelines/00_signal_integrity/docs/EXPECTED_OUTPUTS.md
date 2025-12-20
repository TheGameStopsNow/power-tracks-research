# Expected Outputs

This document describes the expected outputs from the Power Track reproducibility pipeline for the sample dataset (2024-05-13).

## Sample Dataset: GME 2024-05-13

### Input Data

- **Symbol**: GME
- **Date**: 2024-05-13
- **Source**: Polygon API (premium)
- **Format**: CSV and Parquet

### Expected Frame Counts

- **Total frames detected**: Variable (depends on detection window)
- **Valid frames (CRC pass)**: ≥ 95% of detected frames
- **Frame size**: 7 bytes minimum (header + trailer), plus variable payload

### CRC Pass Rates

- **Target CRC pass rate**: ≥ 98% per hour
- **Minimum acceptable**: ≥ 95%
- **Validation**: All frames must pass CRC-7 validation with polynomial 0x09

### Decoded Varint Counts

- **Typical varints per frame**: 3-20
- **Minimum**: 1 varint per frame
- **Maximum**: 50 varints per frame (rare)

### Price Path Validation Criteria

- **Price range**: $0.01 - $100,000 (reasonable market prices)
- **Temporal monotonicity**: Timestamps must be sequential
- **Price relationships**: OHLC relationships must be valid (High ≥ Low, etc.)
- **Anchor price**: Must be within reasonable range for symbol

### SHA256 Checksums

Expected SHA256 checksums for sample dataset files:

```
# Raw Tick Data
<SHA256>  sample_2024-05-13/raw_ticks/GME_2024-05-13_trades.csv
<SHA256>  sample_2024-05-13/raw_ticks/GME_2024-05-13_trades.parquet

# Decoded Frames
<SHA256>  sample_2024-05-13/decoded_frames/frames.bin
<SHA256>  sample_2024-05-13/decoded_frames/frames.csv

# Price Paths
<SHA256>  sample_2024-05-13/signals/price_paths.csv
```

**Note**: Actual checksums will be generated when sample dataset is curated. Use `sha256sum` or `shasum -a 256` to compute.

### Frame Structure Validation

Each frame must have:

1. **Valid header** (bytes 0-5):
   - Opcode: 0x00-0x3F (6 bits)
   - Version: 0-3 (2 bits)
   - Start time: 0-86,400,000,000 microseconds
   - Duration scale: 0-63
   - Compression ratio: 0-3 (1x, 2x, 4x, 8x)
   - Anchor price: 0-255 cents
   - Volume code: 0-63
   - Parity: 0-3

2. **Valid trailer** (byte 6):
   - CRC-7: 0x00-0x7F (7 bits)
   - Stop bit: 1 (bit 0)

3. **CRC validation**:
   - Computed CRC-7 over header + payload must match CRC in trailer
   - Polynomial: 0x09

### XOR Mask Discovery

- **Search range**: 0x00-0x1F (0-31 decimal)
- **Discovery threshold**: ≥ 25% valid frames
- **Common masks**: 0x00, 0x05, 0x07 (varies by symbol/date)

### Validation Report Format

Expected validation report structure:

```json
{
  "symbol": "GME",
  "date": "2024-05-13",
  "total_frames": 100,
  "valid_frames": 98,
  "crc_pass_rate": 0.98,
  "xor_mask": "0x07",
  "varint_count": 1500,
  "avg_varints_per_frame": 15.0,
  "price_paths": 98,
  "validation_status": "PASS"
}
```

### Performance Targets

- **Frame extraction**: < 100ms per 1000 frames
- **CRC validation**: < 10ms per 1000 frames
- **Varint decoding**: < 50ms per 1000 frames
- **Path unfolding**: < 200ms per 1000 frames

### Troubleshooting

If outputs don't match expectations:

1. **Low CRC pass rate**:
   - Check XOR mask discovery
   - Verify frame alignment
   - Validate input data integrity

2. **Missing frames**:
   - Check detection thresholds
   - Verify bitstream extraction
   - Validate frame boundary detection

3. **Invalid price paths**:
   - Check varint decoding
   - Verify zig-zag decoding
   - Validate temporal scaling

4. **SHA256 mismatches**:
   - Verify input data source
   - Check for data corruption
   - Re-run pipeline from scratch


