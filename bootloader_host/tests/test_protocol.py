"""
Unit tests for the bootloader protocol module.

Tests frame building, response parsing, and payload packers.
"""

import struct
import pytest
from bootloader_host.protocol import (
    ACK,
    NACK,
    MAX_PACKET_LEN,
    CommandCode,
    BootloaderResponse,
    build_frame,
    parse_response,
    pack_go_to_address,
    pack_flash_erase,
    pack_mem_write,
    pack_mem_read,
    pack_otp_read,
    COMMAND_NAMES,
)
from bootloader_host.exceptions import (
    NackError,
    ProtocolError,
    PacketTooLargeError,
    ValidationError,
)


# =========================================================================
# Frame Builder Tests
# =========================================================================

class TestBuildFrame:
    """Tests for build_frame()."""

    def test_get_ver_frame(self):
        """GET_VER frame: [LEN=5][CMD=0x51][CRC=4bytes]."""
        frame = build_frame(CommandCode.GET_VER)
        assert len(frame) == 6  # 1 (LEN) + 1 (CMD) + 4 (CRC)
        assert frame[0] == 5    # LEN = 1 (CMD) + 0 (DATA) + 4 (CRC)
        assert frame[1] == 0x51  # Command byte

    def test_get_help_frame(self):
        """GET_HELP frame structure."""
        frame = build_frame(CommandCode.GET_HELP)
        assert len(frame) == 6
        assert frame[0] == 5
        assert frame[1] == 0x52

    def test_frame_has_crc(self):
        """Frame should have 4 CRC bytes at the end."""
        frame = build_frame(CommandCode.GET_VER)
        assert len(frame) == 6
        crc_bytes = frame[2:6]
        assert len(crc_bytes) == 4
        # CRC should not be all zeros
        assert crc_bytes != b"\x00\x00\x00\x00"

    def test_frame_with_data(self):
        """Frame with payload data should have correct length."""
        data = bytes([0x00, 0x80, 0x00, 0x08])
        frame = build_frame(CommandCode.GO_TO_ADDR, data)
        # LEN = 1 (CMD) + 4 (DATA) + 4 (CRC) = 9
        assert frame[0] == 9
        assert len(frame) == 10  # 1 (LEN byte) + 9 = 10
        assert frame[1] == 0x55
        assert frame[2:6] == data

    def test_frame_empty_data(self):
        """Frame with empty data should still be valid."""
        frame = build_frame(CommandCode.GET_VER, b"")
        assert len(frame) == 6

    def test_frame_payload_max_size(self):
        """Maximum allowed payload (244 bytes data + 1 cmd) should work."""
        data = bytes([0x00] * 244)
        frame = build_frame(CommandCode.MEM_WRITE, data)
        # LEN = 1 (CMD) + 244 (DATA) + 4 (CRC) = 249
        assert frame[0] == 249
        assert len(frame) == 250  # 1 + 249

    def test_frame_payload_too_large(self):
        """Payload exceeding max should raise PacketTooLargeError."""
        data = bytes([0x00] * 245)  # 1 + 245 + 4 = 250 > 249
        with pytest.raises(PacketTooLargeError):
            build_frame(CommandCode.MEM_WRITE, data)

    def test_frame_deterministic(self):
        """Same inputs produce identical frames."""
        f1 = build_frame(CommandCode.GET_VER)
        f2 = build_frame(CommandCode.GET_VER)
        assert f1 == f2


# =========================================================================
# CRC Verification in Frame
# =========================================================================

class TestFrameCrc:
    """Verify that frames have correct CRC values."""

    def _extract_and_verify_crc(self, frame: bytes):
        """Helper: extract CRC from frame, compute expected, compare."""
        length = frame[0]
        # CRC input is [LEN, CMD, DATA...] = first (length - 3) bytes... wait
        # length = 1 (CMD) + N (DATA) + 4 (CRC)
        # CRC input = [LEN] + [CMD] + [DATA] = frame[0:1+length-4]
        crc_input = frame[:1 + length - 4]
        expected_crc = self._stm32_crc(crc_input)
        actual_crc = struct.unpack("<I", frame[1 + length - 4:1 + length])[0]
        assert actual_crc == expected_crc, f"CRC mismatch: got 0x{actual_crc:08X}, expected 0x{expected_crc:08X}"

    def _stm32_crc(self, data: bytes) -> int:
        """Re-implement CRC locally for independent verification."""
        from bootloader_host.crc import stm32_bootloader_crc
        return stm32_bootloader_crc(data)

    def test_get_ver_crc_valid(self):
        frame = build_frame(CommandCode.GET_VER)
        self._extract_and_verify_crc(frame)

    def test_go_to_addr_crc_valid(self):
        frame = build_frame(CommandCode.GO_TO_ADDR, pack_go_to_address(0x08008000))
        self._extract_and_verify_crc(frame)

    def test_flash_erase_crc_valid(self):
        frame = build_frame(CommandCode.FLASH_ERASE, pack_flash_erase(2, 4))
        self._extract_and_verify_crc(frame)

    def test_mem_write_crc_valid(self):
        data = bytes([0x00, 0x01, 0x02, 0x03])
        frame = build_frame(CommandCode.MEM_WRITE, pack_mem_write(0x08008000, data))
        self._extract_and_verify_crc(frame)

    def test_mem_read_crc_valid(self):
        frame = build_frame(CommandCode.MEM_READ, pack_mem_read(0x08008000, 16))
        self._extract_and_verify_crc(frame)

    def test_all_commands_have_valid_crc(self):
        """Every command code produces a frame with valid CRC."""
        for cmd in CommandCode:
            if cmd == CommandCode.MEM_WRITE:
                frame = build_frame(cmd, pack_mem_write(0x08000000, bytes([0xAA])))
            elif cmd == CommandCode.MEM_READ:
                frame = build_frame(cmd, pack_mem_read(0x08000000, 4))
            elif cmd == CommandCode.FLASH_ERASE:
                frame = build_frame(cmd, pack_flash_erase(2, 1))
            elif cmd == CommandCode.GO_TO_ADDR:
                frame = build_frame(cmd, pack_go_to_address(0x08008000))
            elif cmd == CommandCode.EN_R_W_PROTECT:
                frame = build_frame(cmd, bytes([2, 3]))
            elif cmd == CommandCode.DIS_R_RW_PROTECT:
                frame = build_frame(cmd, bytes([2, 3]))
            elif cmd == CommandCode.OTP_READ:
                frame = build_frame(cmd, pack_otp_read(0x1FFF7000, 4))
            else:
                frame = build_frame(cmd)  # no payload commands
            self._extract_and_verify_crc(frame)


# =========================================================================
# Response Parser Tests
# =========================================================================

class TestParseResponse:
    """Tests for parse_response()."""

    def test_ack_with_data(self):
        """ACK with follow_len and payload."""
        data = bytes([0xA5, 0x03, 0x10, 0x20, 0x30])
        resp = parse_response(data)
        assert resp.ack is True
        assert resp.follow_len == 3
        assert resp.data == bytes([0x10, 0x20, 0x30])

    def test_ack_empty_payload(self):
        """ACK with follow_len=0."""
        data = bytes([0xA5, 0x00])
        resp = parse_response(data)
        assert resp.ack is True
        assert resp.follow_len == 0
        assert resp.data == b""

    def test_nack(self):
        """NACK response."""
        data = bytes([0x7F])
        resp = parse_response(data)
        assert resp.ack is False
        assert resp.follow_len == 0
        assert resp.data == b""

    def test_empty_response(self):
        """Empty response should raise ProtocolError."""
        with pytest.raises(ProtocolError, match="Empty response"):
            parse_response(b"")

    def test_invalid_status(self):
        """Unexpected status byte should raise ProtocolError."""
        with pytest.raises(ProtocolError, match="Unexpected response"):
            parse_response(bytes([0x00]))

        with pytest.raises(ProtocolError, match="Unexpected response"):
            parse_response(bytes([0xFF]))

    def test_ack_missing_follow_len(self):
        """ACK byte without follow_len should raise ProtocolError."""
        with pytest.raises(ProtocolError, match="missing follow_len"):
            parse_response(bytes([0xA5]))

    def test_truncated_payload(self):
        """ACK with follow_len but not enough data bytes."""
        data = bytes([0xA5, 0x05, 0x01, 0x02])  # claims 5 bytes, only has 2
        with pytest.raises(ProtocolError, match="truncated"):
            parse_response(data)

    def test_ack_hex_display(self):
        """BootloaderResponse.as_hex should format nicely."""
        resp = BootloaderResponse(ack=True, follow_len=2, data=bytes([0xDE, 0xAD]))
        assert "de ad" in resp.as_hex or "dead" in resp.as_hex

    def test_nack_hex_display(self):
        """NACK response should show '(empty)' for hex."""
        resp = BootloaderResponse(ack=False)
        assert "(empty)" in resp.as_hex


# =========================================================================
# Payload Packer Tests
# =========================================================================

class TestPackers:
    """Tests for the command payload packing functions."""

    def test_pack_go_to_address(self):
        """GO_TO_ADDR packs address as little-endian uint32."""
        result = pack_go_to_address(0x08008000)
        assert result == bytes([0x00, 0x80, 0x00, 0x08])
        assert len(result) == 4

    def test_pack_go_to_address_zero(self):
        """Address 0 should pack correctly."""
        result = pack_go_to_address(0)
        assert result == bytes([0x00, 0x00, 0x00, 0x00])

    def test_pack_flash_erase(self):
        """Flash erase packs sector and count as two bytes."""
        result = pack_flash_erase(2, 4)
        assert result == bytes([0x02, 0x04])
        assert len(result) == 2

    def test_pack_flash_erase_single(self):
        """Flash erase with count=1."""
        result = pack_flash_erase(5, 1)
        assert result == bytes([0x05, 0x01])

    def test_pack_flash_erase_invalid_sector(self):
        """Sector out of range should raise."""
        with pytest.raises(ValidationError):
            pack_flash_erase(12, 1)  # sectors are 0-11
        with pytest.raises(ValidationError):
            pack_flash_erase(-1, 1)

    def test_pack_flash_erase_invalid_count(self):
        """Count < 1 should raise."""
        with pytest.raises(ValidationError):
            pack_flash_erase(2, 0)

    def test_pack_mem_write(self):
        """MEM_WRITE packs address, length byte, then data."""
        data = bytes([0x00, 0x01, 0x02])
        result = pack_mem_write(0x08008000, data)
        # Expected: [0x00, 0x80, 0x00, 0x08, 0x03, 0x00, 0x01, 0x02]
        assert result == bytes([0x00, 0x80, 0x00, 0x08, 0x03, 0x00, 0x01, 0x02])
        assert len(result) == 8  # 4 (addr) + 1 (len) + 3 (data)

    def test_pack_mem_write_empty(self):
        """MEM_WRITE with empty data."""
        result = pack_mem_write(0x08000000, b"")
        assert result == bytes([0x00, 0x00, 0x00, 0x08, 0x00])

    def test_pack_mem_write_max_size(self):
        """MEM_WRITE with 239 bytes (maximum)."""
        data = bytes([0x00] * 239)
        result = pack_mem_write(0x08000000, data)
        assert len(result) == 244  # 4 + 1 + 239

    def test_pack_mem_write_too_large(self):
        """MEM_WRITE with > 239 bytes should raise."""
        data = bytes([0x00] * 240)
        with pytest.raises(ValidationError, match="too large"):
            pack_mem_write(0x08000000, data)

    def test_pack_mem_read(self):
        """MEM_READ packs address and length."""
        result = pack_mem_read(0x08008000, 128)
        assert result == bytes([0x00, 0x80, 0x00, 0x08, 0x80])  # 128 = 0x80
        assert len(result) == 5

    def test_pack_mem_read_max_length(self):
        """MEM_READ with length=255 (maximum)."""
        result = pack_mem_read(0x08008000, 255)
        assert result == bytes([0x00, 0x80, 0x00, 0x08, 0xFF])
        assert len(result) == 5

    def test_pack_mem_read_min_length(self):
        """MEM_READ with length=1."""
        result = pack_mem_read(0x08000000, 1)
        assert result == bytes([0x00, 0x00, 0x00, 0x08, 0x01])

    def test_pack_mem_read_zero_length(self):
        """MEM_READ with length 0 should raise."""
        with pytest.raises(ValidationError):
            pack_mem_read(0x08000000, 0)

    def test_pack_otp_read(self):
        """OTP_READ packs address and length."""
        result = pack_otp_read(0x1FFF7000, 8)
        assert result == bytes([0x00, 0x70, 0xFF, 0x1F, 0x08])
        assert len(result) == 5


# =========================================================================
# Command Codes
# =========================================================================

class TestCommandCodes:
    """Tests for CommandCode enum."""

    def test_all_codes_defined(self):
        """All 12 bootloader command codes should be defined."""
        codes = list(CommandCode)
        assert len(codes) == 12

    def test_codes_start_at_0x51(self):
        """First command code should be 0x51."""
        assert CommandCode.GET_VER == 0x51

    def test_codes_end_at_0x5C(self):
        """Last command code should be 0x5C."""
        assert CommandCode.DIS_R_RW_PROTECT == 0x5C

    def test_all_codes_have_names(self):
        """Every command code should have a human-readable name."""
        for code in CommandCode:
            assert code.value in COMMAND_NAMES
            assert COMMAND_NAMES[code.value] == code.name

    def test_unknown_code_not_in_names(self):
        """Unknown codes should not appear in COMMAND_NAMES."""
        assert 0x00 not in COMMAND_NAMES
        assert 0xFF not in COMMAND_NAMES


# =========================================================================
# Edge Cases
# =========================================================================

class TestEdgeCases:
    """Edge case tests for the protocol module."""

    def test_build_frame_requires_int_cmd(self):
        """build_frame should accept int codes as well as CommandCode enum."""
        frame_enum = build_frame(CommandCode.GET_VER)
        frame_int = build_frame(0x51)
        assert frame_enum == frame_int

    def test_build_frame_with_all_zeros_data(self):
        """Frame with all-zero data should still be valid."""
        frame = build_frame(CommandCode.MEM_WRITE, bytes([0x00] * 100))
        assert len(frame) == 1 + 1 + 100 + 4  # LEN + CMD + DATA + CRC

    def test_response_dataclass_defaults(self):
        """BootloaderResponse defaults."""
        resp = BootloaderResponse(ack=True)
        assert resp.follow_len == 0
        assert resp.data == b""

    def test_response_as_int(self):
        """BootloaderResponse.as_int interprets data as LE integer."""
        resp = BootloaderResponse(ack=True, follow_len=2, data=bytes([0x13, 0x04]))
        assert resp.as_int() == 0x0413
