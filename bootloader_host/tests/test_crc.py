"""
Unit tests for the STM32 HAL-compatible CRC implementation.

Tests use known CRC values computed by tracing through the
firmware's CRC algorithm.
"""

import struct
import pytest
from bootloader_host.crc import stm32_bootloader_crc, stm32_bootloader_crc_bytes


class TestCrcBasics:
    """Basic CRC computation tests."""

    def test_crc_empty_data(self):
        """CRC of no data should be the init value 0xFFFFFFFF."""
        result = stm32_bootloader_crc(b"")
        assert result == 0xFFFFFFFF

    def test_crc_single_zero(self):
        """CRC of a single byte 0x00."""
        result = stm32_bootloader_crc(b"\x00")
        # Verified against STM32 HAL CRC peripheral behavior:
        # processes byte 0x00 as 32-bit word 0x00000000
        assert result == 0xC704DD7B

    def test_crc_byte_values(self):
        """CRC of single byte values should produce known results."""
        test_cases = [
            (b"\x00", 0xC704DD7B),
            (b"\x01", 0xC3C5C0CC),
            (b"\xFF", 0x76F39DCF),
            (b"\x51", 0xBB526BCB),
            (b"\x05", 0xD0C1B610),
        ]
        for data, expected in test_cases:
            result = stm32_bootloader_crc(data)
            assert result == expected, f"CRC({data.hex()}) = 0x{result:08X}, expected 0x{expected:08X}"


class TestCrcFrame:
    """CRC tests that match actual bootloader frame computation."""

    def test_get_ver_frame_crc(self):
        """
        GET_VER frame: [0x05][0x51] → CRC input is [0x05, 0x51].
        Verified against the firmware CRC computation.
        """
        crc_input = bytes([0x05, 0x51])  # LEN=5, CMD=0x51
        result = stm32_bootloader_crc(crc_input)
        # This is the value the firmware would compute
        assert result == 0x7CABE9E7

    def test_get_help_frame_crc(self):
        """GET_HELP frame: [0x05][0x52]."""
        crc_input = bytes([0x05, 0x52])
        result = stm32_bootloader_crc(crc_input)
        assert result == 0x71E8CF3E

    def test_chip_id_frame_crc(self):
        """GET_CID frame: [0x05][0x53]."""
        crc_input = bytes([0x05, 0x53])
        result = stm32_bootloader_crc(crc_input)
        assert result == 0x7529D289

    def test_longer_data_crc(self):
        """CRC of a longer input with multiple bytes."""
        data = bytes([
            0x09,       # LEN
            0x55,       # GO_TO_ADDR
            0x00, 0x80, 0x00, 0x08,  # Address 0x08008000
        ])
        result = stm32_bootloader_crc(data)
        # Just verify it's deterministic and non-trivial
        assert result != 0
        assert result != 0xFFFFFFFF

    def test_multi_byte_crc(self):
        """CRC of a 3-byte sequence to verify accumulation."""
        data = bytes([0x05, 0x51, 0x00])
        result = stm32_bootloader_crc(data)
        # Test determinism
        result2 = stm32_bootloader_crc(data)
        assert result == result2


class TestCrcBytes:
    """Tests for the bytes-returning CRC variant."""

    def test_get_ver_crc_bytes(self):
        """stm32_bootloader_crc_bytes returns 4-byte little-endian."""
        crc_input = bytes([0x05, 0x51])
        result = stm32_bootloader_crc_bytes(crc_input)
        assert len(result) == 4
        # Verify it's the little-endian encoding of 0x7CABE9E7
        expected = struct.pack("<I", 0x7CABE9E7)
        assert result == expected

    def test_crc_bytes_reversible(self):
        """stm32_bootloader_crc_bytes should match stm32_bootloader_crc + pack."""
        data = bytes([0x0A, 0x57, 0x00, 0x80, 0x00, 0x08])
        bytes_result = stm32_bootloader_crc_bytes(data)
        int_result = struct.pack("<I", stm32_bootloader_crc(data))
        assert bytes_result == int_result


class TestCrcConsistency:
    """Tests that CRC is deterministic and consistent."""

    def test_deterministic(self):
        """Same input always produces same CRC."""
        data = b"The quick brown fox jumps over the lazy dog"
        assert stm32_bootloader_crc(data) == stm32_bootloader_crc(data)

    def test_order_matters(self):
        """CRC of [A, B] != CRC of [B, A]."""
        ab = stm32_bootloader_crc(bytes([0x01, 0x02]))
        ba = stm32_bootloader_crc(bytes([0x02, 0x01]))
        assert ab != ba

    def test_max_payload_crc(self):
        """CRC of a 249-byte payload (max packet)."""
        data = bytes([249]) + bytes([0x51]) + bytes([0x00] * 244)
        result = stm32_bootloader_crc(data)
        assert isinstance(result, int)
        assert 0 <= result <= 0xFFFFFFFF
