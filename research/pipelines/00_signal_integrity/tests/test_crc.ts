/**
 * CRC Test Suite for Power Track Frame Validation (TypeScript)
 * 
 * Tests CRC-7, CRC-16-CCITT, and CRC-16-X25 implementations
 * with known test vectors and edge cases.
 */

export function crc7(data: Uint8Array, polynomial: number = 0x09): number {
  let crc = 0;
  for (const byte of data) {
    crc ^= byte;
    for (let i = 0; i < 8; i += 1) {
      if (crc & 0x80) {
        crc = ((crc << 1) ^ polynomial) & 0xff;
      } else {
        crc = (crc << 1) & 0xff;
      }
    }
  }
  return crc & 0x7f;
}

export function crc16Ccitt(data: Uint8Array, initial: number = 0xffff): number {
  let crc = initial;
  const polynomial = 0x1021;
  
  for (const byte of data) {
    crc ^= (byte << 8);
    for (let i = 0; i < 8; i += 1) {
      if (crc & 0x8000) {
        crc = ((crc << 1) ^ polynomial) & 0xffff;
      } else {
        crc = (crc << 1) & 0xffff;
      }
    }
  }
  
  return crc;
}

export function crc16X25(data: Uint8Array, initial: number = 0xffff): number {
  let crc = initial;
  const polynomial = 0x1021;
  
  for (const byte of data) {
    crc ^= byte;
    for (let i = 0; i < 8; i += 1) {
      if (crc & 0x0001) {
        crc = ((crc >> 1) ^ polynomial) & 0xffff;
      } else {
        crc = (crc >> 1) & 0xffff;
      }
    }
  }
  
  return crc ^ 0xffff;
}

// Test cases (for use with Jest or similar)
describe('CRC-7', () => {
  it('should return 0x00 for empty data', () => {
    expect(crc7(new Uint8Array([]))).toBe(0x00);
  });

  it('should return 0x00 for single zero byte', () => {
    expect(crc7(new Uint8Array([0x00]))).toBe(0x00);
  });

  it('should return 0x79 for single 0xFF byte', () => {
    expect(crc7(new Uint8Array([0xFF]))).toBe(0x79);
  });

  it('should match known vector for "123456789"', () => {
    const data = new Uint8Array([0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39]);
    expect(crc7(data)).toBe(0x75);
  });

  it('should match known vector [0x01, 0x02, 0x03, 0x04]', () => {
    const data = new Uint8Array([0x01, 0x02, 0x03, 0x04]);
    expect(crc7(data)).toBe(0x0E);
  });

  it('should return 0x00 for all zeros', () => {
    const data = new Uint8Array(10).fill(0);
    expect(crc7(data)).toBe(0x00);
  });

  it('should return 7-bit value', () => {
    const data = new Uint8Array([0xFF, 0xFF, 0xFF]);
    const crc = crc7(data);
    expect(crc).toBeLessThanOrEqual(0x7F);
    expect(crc).toBeGreaterThanOrEqual(0x00);
  });
});

describe('CRC-16-CCITT', () => {
  it('should return 0xFFFF for empty data', () => {
    expect(crc16Ccitt(new Uint8Array([]))).toBe(0xFFFF);
  });

  it('should match known vector for "123456789"', () => {
    const data = new Uint8Array([0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39]);
    expect(crc16Ccitt(data)).toBe(0x29B1);
  });

  it('should return 16-bit value', () => {
    const data = new Uint8Array([0x01, 0x02, 0x03]);
    const crc = crc16Ccitt(data);
    expect(crc).toBeLessThanOrEqual(0xFFFF);
  });
});

describe('CRC-16-X25', () => {
  it('should return 0x0000 for empty data', () => {
    expect(crc16X25(new Uint8Array([]))).toBe(0x0000);
  });

  it('should match known vector for "123456789"', () => {
    const data = new Uint8Array([0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39]);
    expect(crc16X25(data)).toBe(0x906E);
  });

  it('should return 16-bit value', () => {
    const data = new Uint8Array([0x01, 0x02, 0x03]);
    const crc = crc16X25(data);
    expect(crc).toBeLessThanOrEqual(0xFFFF);
  });
});

describe('CRC Comparison', () => {
  it('should produce different results for different CRC types', () => {
    const data = new Uint8Array([0x74, 0x65, 0x73, 0x74]); // "test"
    const crc7Val = crc7(data);
    const crc16CcittVal = crc16Ccitt(data);
    const crc16X25Val = crc16X25(data);
    
    expect(crc7Val).not.toBe(crc16CcittVal);
    expect(crc7Val).not.toBe(crc16X25Val);
    expect(crc16CcittVal).not.toBe(crc16X25Val);
  });

  it('should be deterministic', () => {
    const data = new Uint8Array([0x70, 0x6F, 0x77, 0x65, 0x72]); // "power"
    
    const crc7_1 = crc7(data);
    const crc7_2 = crc7(data);
    expect(crc7_1).toBe(crc7_2);
    
    const crc16_1 = crc16Ccitt(data);
    const crc16_2 = crc16Ccitt(data);
    expect(crc16_1).toBe(crc16_2);
  });
});


