# Power Track Frame Format - Kaitai Struct Schema
# Frame Structure: 56-bit frames with XOR mask and CRC-7 validation

meta:
  id: power_track_frame
  file-extension: ptf
  endian: le
  encoding: UTF-8
  title: Power Track Frame Format
  license: MIT
  ks-version: 0.9

doc: |
  Power Track frame format specification.
  Each frame consists of a 6-byte header, variable-length payload,
  and 1-byte trailer with CRC-7 checksum.

doc-ref: https://github.com/TheGameStopsNow/power-tracks-engine

seq:
  - id: header
    type: frame_header
    
  - id: payload
    type: varint_array
    size: eos
    
  - id: trailer
    type: frame_trailer

types:
  frame_header:
    doc: |
      6-byte fixed header containing opcode, version, timestamps,
      scaling factors, anchor price, and volume code.
    seq:
      - id: byte0
        type: u1
        doc: Opcode (6 bits) and Version (2 bits)
        
      - id: start_time_lsb
        type: u1
        doc: Start timestamp LSB (microseconds from session start)
        
      - id: start_time_msb
        type: u1
        doc: Start timestamp MSB
        
      - id: byte3
        type: u1
        doc: Duration scale (6 bits) and Compression ratio (2 bits)
        
      - id: anchor_price
        type: u1
        doc: Anchor price in cents (0-255)
        
      - id: byte5
        type: u1
        doc: Volume code (6 bits) and Parity (2 bits)
        
    instances:
      opcode:
        value: (byte0 >> 2) & 0x3F
        doc: 6-bit opcode defining payload encoding mode
      
      version:
        value: byte0 & 0x03
        doc: 2-bit protocol version (0-3)
      
      start_time_us:
        value: start_time_lsb | (start_time_msb << 8)
        doc: 16-bit microsecond timestamp (little-endian)
      
      duration_scale:
        value: (byte3 >> 2) & 0x3F
        doc: 6-bit temporal scaling factor (0-63)
      
      compression_ratio:
        value: byte3 & 0x03
        doc: 2-bit compression factor (0=1x, 1=2x, 2=4x, 3=8x)
      
      volume_code:
        value: (byte5 >> 2) & 0x3F
        doc: 6-bit volume scaling cluster (0-63)
      
      parity:
        value: byte5 & 0x03
        doc: 2-bit CRC-7 remainder bits

  frame_trailer:
    doc: |
      1-byte trailer containing CRC-7 checksum and stop bit.
    seq:
      - id: trailer_byte
        type: u1
        
    instances:
      crc7:
        value: (trailer_byte >> 1) & 0x7F
        doc: 7-bit CRC-7 checksum (polynomial 0x09)
      
      stop_bit:
        value: trailer_byte & 0x01
        doc: Frame terminator bit (should be 1)

  varint_array:
    doc: |
      Array of varint-encoded integers using 7-bit continuation encoding.
      Each varint may be zig-zag encoded for signed values.
    seq:
      - id: values
        type: varint
        repeat: eos

  varint:
    doc: |
      Variable-length integer using 7-bit continuation encoding.
      Bit 7 indicates continuation (1 = more bytes, 0 = last byte).
      Bits 6-0 contain data bits.
    seq:
      - id: bytes
        type: u1
        repeat: until
        repeat-until: _io.pos >= _io.size || (bytes & 0x80) == 0
        
    instances:
      value:
        value: >
          var acc = 0;
          var shift = 0;
          for (var i = 0; i < bytes.length; i++) {
            acc |= (bytes[i] & 0x7F) << shift;
            shift += 7;
          }
          acc
        doc: Decoded unsigned integer value
      
      zigzag_decoded:
        value: (value >> 1) ^ (-(value & 1))
        doc: Zig-zag decoded signed integer

enums:
  opcode_type:
    0x1a: opcode_varint_1
    0x1f: opcode_varint_2
    0x3f: opcode_mirror
    0x7a: opcode_varint_3
    0x91: opcode_continuation


