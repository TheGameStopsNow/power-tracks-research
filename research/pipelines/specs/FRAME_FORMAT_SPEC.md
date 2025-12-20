# Power Track Frame Format Specification

## Overview

Power Tracks use a 56-bit frame structure to encode price movement signals. Frames are XOR-masked for obfuscation and include CRC-7 validation for integrity checking.

## Frame Structure

### Overall Layout

Each frame consists of:
- **Header**: 6 bytes (48 bits) - Fixed structure
- **Payload**: Variable length - Varint-encoded price deltas
- **Trailer**: 1 byte (8 bits) - CRC-7 checksum + stop bit

**Total frame size**: 56 bits minimum (7 bytes header + trailer), plus variable payload

### Byte-by-Byte Layout

```
Byte 0: [opcode:6 bits][version:2 bits]
Byte 1: [start_time_lsb:8 bits]
Byte 2: [start_time_msb:8 bits]
Byte 3: [duration_scale:6 bits][compression_ratio:2 bits]
Byte 4: [anchor_price:8 bits]
Byte 5: [volume_code:6 bits][parity:2 bits]
Byte 6: [CRC-7:7 bits][stop_bit:1 bit]
Bytes 7+: [payload: variable length varints]
```

### Field Definitions

#### Byte 0: Opcode and Version

- **Opcode (bits 7-2)**: 6-bit instruction type defining payload encoding mode
  - `0x1A`: VARINT mode - Compressed integer encoding
  - `0x1F`: VARINT mode - Alternative varint encoding
  - `0x3F`: MIRROR mode - Sign-flipped replication
  - `0x7A`: VARINT mode - Extended varint encoding
  - `0x91`: CONT mode - Path continuation
  - Other values: RAW mode - Direct byte-to-price mapping

- **Version (bits 1-0)**: 2-bit protocol version (0-3)
  - Currently version 1 is most common

#### Byte 1-2: Start Timestamp

- **Start Time (16 bits)**: Microsecond timestamp from session start
  - Byte 1: LSB (least significant byte)
  - Byte 2: MSB (most significant byte)
  - Range: 0 to 86,400,000,000 microseconds (24 hours)
  - Little-endian encoding

#### Byte 3: Duration and Compression

- **Duration Scale (bits 7-2)**: 6-bit temporal scaling factor
  - Range: 0-63
  - Multiplies base time unit

- **Compression Ratio (bits 1-0)**: 2-bit time compression factor
  - `0b00`: 1× (no compression)
  - `0b01`: 2× compression
  - `0b10`: 4× compression
  - `0b11`: 8× compression
  - Formula: `duration = duration_scale × base_time × (2^compression_ratio)`

#### Byte 4: Anchor Price

- **Anchor Price (8 bits)**: Reference price in cents
  - Range: 0-255 cents ($0.00 - $2.55)
  - Used as base for price delta calculations
  - For prices > $2.55, scaling factors apply

#### Byte 5: Volume Code and Parity

- **Volume Code (bits 7-2)**: 6-bit volume scaling cluster
  - Range: 0-63
  - Maps to cluster multipliers: [10, 25, 50, 100] microdollars
  - Formula: `price_factor = cluster_multiplier[volume_code % 4] / π`

- **Parity (bits 1-0)**: 2-bit CRC-7 remainder bits
  - Used for additional error checking

#### Byte 6: CRC-7 and Stop Bit

- **CRC-7 (bits 7-1)**: 7-bit cyclic redundancy check
  - Polynomial: `0x09` (x^7 + x^3 + 1)
  - Computed over bytes 0-5 (header) + payload bytes
  - Algorithm: See CRC-7 Specification section

- **Stop Bit (bit 0)**: Frame terminator
  - Always set to 1 for valid frames
  - Used for frame boundary detection

## XOR Mask Details

### Mask Range

- **Search Range**: `0x00` to `0x1F` (0-31 decimal)
- **Common Masks**: `0x00`, `0x05`, `0x07` (varies by symbol/date)
- **Mask Application**: XOR each byte of the frame with the mask key

### Discovery Algorithm

1. **Test each mask** in range 0x00-0x1F
2. **Apply XOR** to first 30 frames
3. **Score each mask** based on:
   - Varint count (3-20 per frame is typical)
   - Timestamp plausibility (monotonic, within 0-6 hours)
   - Price relationship validation
   - CRC pass rate
4. **Select mask** with highest score above 25% threshold

### Scoring Criteria

```python
score = (
    valid_frame_fraction * 0.4 +
    timestamp_monotonicity * 0.3 +
    price_plausibility * 0.3
)
```

Where:
- `valid_frame_fraction`: Number of frames with valid CRC / total frames
- `timestamp_monotonicity`: Sequential timestamp progression score
- `price_plausibility`: Reasonable OHLC relationships score

## CRC-7 Specification

### Polynomial

- **Polynomial**: `0x09` (binary: `00001001`)
- **Polynomial Form**: x^7 + x^3 + 1
- **Width**: 7 bits
- **Initial Value**: 0x00
- **Final XOR**: None

### Algorithm

```python
def crc7(data: bytes, polynomial: int = 0x09) -> int:
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ polynomial) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc & 0x7F
```

### Validation

- CRC is computed over **header bytes (0-5) + payload bytes**
- Trailer byte (byte 6) contains the CRC value in bits 7-1
- Frame is valid if computed CRC matches expected CRC

### Test Vectors

| Input | Expected CRC-7 |
|-------|----------------|
| `b''` | `0x00` |
| `b'\x00'` | `0x00` |
| `b'\xFF'` | `0x79` |
| `b'123456789'` | `0x75` |
| `b'\x01\x02\x03\x04'` | `0x0E` |

## Varint Encoding Rules

### 7-bit Continuation Encoding

Varints use a 7-bit continuation encoding scheme:

- **Bit 7**: Continuation bit (1 = more bytes follow, 0 = last byte)
- **Bits 6-0**: Data bits
- **Little-endian**: Least significant bits first

### Decoding Algorithm

```python
def decode_varint(buffer: bytes) -> list[int]:
    values = []
    acc = 0
    shift = 0
    
    for byte in buffer:
        acc |= (byte & 0x7F) << shift
        if byte & 0x80:
            shift += 7
            continue
        values.append(acc)
        acc = 0
        shift = 0
    
    if shift != 0:
        values.append(acc)  # Incomplete varint
    
    return values
```

### Zig-Zag Encoding

Signed integers are encoded using zig-zag encoding:

- **Mapping**: `0 → 0, 1 → -1, 2 → 1, 3 → -2, 4 → 2, 5 → -3, ...`
- **Formula**: `zigzag_decode(n) = (n >> 1) ^ (-(n & 1))`
- **Purpose**: Efficient encoding of small signed values

### Example

```
Unsigned varint: 0x82 0x01
Binary: 10000010 00000001
Decode: (0x02 << 0) | (0x01 << 7) = 0x82 = 130
Zig-zag: (130 >> 1) ^ (-(130 & 1)) = 65 ^ (-0) = 65
```

## Payload Encoding Modes

### RAW Mode

- **Direct byte-to-price mapping**
- Formula: `price_delta = byte_value × π microdollars`
- Used for most opcodes

### VARINT Mode

- **Compressed integer encoding**
- Unsigned varints converted to signed via zig-zag
- Used for opcodes: `0x1A`, `0x1F`, `0x7A`

### MIRROR Mode

- **Sign-flipped replication**
- Opcode `0x3F` followed by zig-zag encoded delta
- Formula: `price = -last_complete_price_path + delta`

### CONT Mode

- **Path continuation**
- Opcode `0x91` followed by continuation value
- Appends payload to previous path

## Temporal and Price Scaling

### Temporal Scaling

- **Base time unit**: 1 second
- **Compression factor**: `2^compression_ratio` (1, 2, 4, or 8×)
- **Duration**: `duration_scale × base_time × compression_factor`

### Price Scaling

- **Cluster multipliers**: `[10, 25, 50, 100]` microdollars per volume code bucket
- **Price factor**: `cluster_multiplier[volume_code % 4] / π`
- **Price reconstruction**: `anchor_price + Σ(delta × price_factor)`

## Example Frame

### Raw Frame (Hex)

```
Frame (masked with 0x07):
7A 07 12 34 56 78 9A BC

After XOR unmasking (0x07):
7D 00 15 33 51 7F 9D BB

Decoded:
Byte 0: 0x7D = 0b01111101
  Opcode: 0b011111 = 0x1F (31)
  Version: 0b01 = 1

Byte 1-2: 0x00 0x15 = 0x1500 (little-endian) = 5376 microseconds

Byte 3: 0x33 = 0b00110011
  Duration Scale: 0b001100 = 12
  Compression Ratio: 0b11 = 3 (8× compression)

Byte 4: 0x51 = 81 cents ($0.81 anchor price)

Byte 5: 0x7F = 0b01111111
  Volume Code: 0b011111 = 31
  Parity: 0b11 = 3

Byte 6: 0x9D = 0b10011101
  CRC-7: 0b1001110 = 0x4E (78)
  Stop Bit: 0b1 = 1
```

### Frame Validation

1. Apply XOR mask (0x07) to reveal frame
2. Extract header fields
3. Compute CRC-7 over header + payload
4. Compare computed CRC with CRC in trailer
5. Validate stop bit is set

## Frame Boundary Detection

Frames are detected by:

1. **Sliding window**: Test 56-bit windows across bitstream
2. **CRC validation**: Check if CRC matches for each window
3. **Stop bit check**: Verify stop bit is set
4. **Alignment**: Choose offset with highest CRC pass rate

## References

- CRC-7 polynomial: ISO/IEC 7816-3
- Varint encoding: Protocol Buffers varint format
- Zig-zag encoding: Protocol Buffers signed integer encoding


