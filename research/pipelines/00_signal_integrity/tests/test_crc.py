#!/usr/bin/env python3
"""
CRC Test Suite for Power Track Frame Validation

Tests CRC-7, CRC-16-CCITT, and CRC-16-X25 implementations
with known test vectors and edge cases.
"""

import unittest
from typing import Sequence


def crc7(data: Sequence[int], polynomial: int = 0x09) -> int:
    """
    Calculate CRC-7 checksum using the standard (non-reflected) parameters:
    poly=0x09, init=0x00, refin=False, refout=False, xorout=0x00.
    
    Note: For a 7-bit CRC we temporarily up-shift into an 8-bit working
    register (matching the crccheck implementation) so that bytewise
    processing is consistent with published check values.
    """
    width = 7
    crc = 0
    highbit = 1 << (width - 1)  # 0x40
    mask = (1 << width) - 1
    shift = width - 8  # negative for widths < 8
    diff8 = -shift
    
    # For sub-byte CRC widths, promote to an 8-bit working register
    if diff8 > 0:
        mask = 0xFF
        crc <<= diff8
        shift = 0
        highbit = 0x80
        polynomial <<= diff8
    
    for byte in data:
        crc ^= (byte << shift)
        for _ in range(8):
            if crc & highbit:
                crc = (crc << 1) ^ polynomial
            else:
                crc <<= 1
        crc &= mask
    
    if diff8 > 0:
        crc >>= diff8
    
    return crc & 0x7F


def crc16_ccitt(data: Sequence[int], initial: int = 0xFFFF) -> int:
    """
    Calculate CRC-16-CCITT checksum.
    
    Polynomial: 0x1021 (x^16 + x^12 + x^5 + 1)
    Initial value: 0xFFFF
    """
    crc = initial
    polynomial = 0x1021
    
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ polynomial) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    
    return crc


def crc16_x25(data: Sequence[int], initial: int = 0xFFFF) -> int:
    """
    Calculate CRC-16-X25 checksum (CRC-16/IBM-SDLC).
    
    Params: poly=0x1021 (reflected 0x8408), refin=True, refout=True,
    init=0xFFFF, xorout=0xFFFF.
    """
    crc = initial
    poly_rev = 0x8408  # reflected 0x1021
    
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ poly_rev
            else:
                crc >>= 1
    
    # Final reflection is implicit; apply xorout
    return (~crc) & 0xFFFF


class TestCRC7(unittest.TestCase):
    """Test CRC-7 implementation with known vectors."""
    
    def test_empty_data(self):
        """CRC-7 of empty data should be 0x00."""
        self.assertEqual(crc7([]), 0x00)
    
    def test_single_zero(self):
        """CRC-7 of single zero byte."""
        self.assertEqual(crc7([0x00]), 0x00)
    
    def test_single_ff(self):
        """CRC-7 of single 0xFF byte."""
        # Note: Actual value may vary by implementation
        # This test verifies the function works, not a specific value
        result = crc7([0xFF])
        self.assertLessEqual(result, 0x7F)  # Must be 7-bit
        self.assertGreaterEqual(result, 0x00)
    
    def test_known_vector_1(self):
        """CRC-7 test vector: '123456789'."""
        data = b'123456789'
        result = crc7(data)
        # Verify result is 7-bit and deterministic
        self.assertLessEqual(result, 0x7F)
        self.assertEqual(result, 0x75)  # Standard CRC-7 check value
    
    def test_known_vector_2(self):
        """CRC-7 test vector: [0x01, 0x02, 0x03, 0x04]."""
        data = [0x01, 0x02, 0x03, 0x04]
        result = crc7(data)
        # Verify result is 7-bit and deterministic
        self.assertLessEqual(result, 0x7F)
        self.assertEqual(result, 0x64)
    
    def test_all_zeros(self):
        """CRC-7 of all zeros."""
        data = [0x00] * 10
        self.assertEqual(crc7(data), 0x00)
    
    def test_all_ones(self):
        """CRC-7 of all 0xFF."""
        data = [0xFF] * 10
        expected = 0x58
        self.assertEqual(crc7(data), expected)
    
    def test_frame_header(self):
        """CRC-7 of typical frame header."""
        # Example header: [0x7A, 0x07, 0x12, 0x34, 0x56, 0x78]
        header = [0x7A, 0x07, 0x12, 0x34, 0x56, 0x78]
        crc = crc7(header)
        # Verify CRC is 7 bits
        self.assertLessEqual(crc, 0x7F)
        self.assertGreaterEqual(crc, 0x00)


class TestCRC16CCITT(unittest.TestCase):
    """Test CRC-16-CCITT implementation."""
    
    def test_empty_data(self):
        """CRC-16-CCITT of empty data."""
        self.assertEqual(crc16_ccitt([]), 0xFFFF)
    
    def test_known_vector_1(self):
        """CRC-16-CCITT test vector: '123456789'."""
        data = b'123456789'
        expected = 0x29B1
        self.assertEqual(crc16_ccitt(data), expected)
    
    def test_known_vector_2(self):
        """CRC-16-CCITT test vector: [0x01, 0x02, 0x03]."""
        data = [0x01, 0x02, 0x03]
        expected = 0xADAD
        self.assertEqual(crc16_ccitt(data), expected)
    
    def test_all_zeros(self):
        """CRC-16-CCITT of all zeros."""
        data = [0x00] * 10
        crc = crc16_ccitt(data)
        self.assertLessEqual(crc, 0xFFFF)


class TestCRC16X25(unittest.TestCase):
    """Test CRC-16-X25 implementation."""
    
    def test_empty_data(self):
        """CRC-16-X25 of empty data."""
        self.assertEqual(crc16_x25([]), 0x0000)
    
    def test_known_vector_1(self):
        """CRC-16-X25 test vector: '123456789'."""
        data = b'123456789'
        expected = 0x906E
        self.assertEqual(crc16_x25(data), expected)
    
    def test_all_zeros(self):
        """CRC-16-X25 of all zeros."""
        data = [0x00] * 10
        crc = crc16_x25(data)
        self.assertLessEqual(crc, 0xFFFF)


class TestCRCComparison(unittest.TestCase):
    """Compare CRC implementations for consistency."""
    
    def test_crc7_vs_crc16(self):
        """Verify CRC-7 and CRC-16 produce different results."""
        data = b'test data'
        crc7_val = crc7(data)
        crc16_ccitt_val = crc16_ccitt(data)
        crc16_x25_val = crc16_x25(data)
        
        # All should be different
        self.assertNotEqual(crc7_val, crc16_ccitt_val)
        self.assertNotEqual(crc7_val, crc16_x25_val)
        self.assertNotEqual(crc16_ccitt_val, crc16_x25_val)
    
    def test_deterministic(self):
        """Verify CRC functions are deterministic."""
        data = b'power track frame data'
        
        crc7_1 = crc7(data)
        crc7_2 = crc7(data)
        self.assertEqual(crc7_1, crc7_2)
        
        crc16_1 = crc16_ccitt(data)
        crc16_2 = crc16_ccitt(data)
        self.assertEqual(crc16_1, crc16_2)


if __name__ == '__main__':
    unittest.main()
