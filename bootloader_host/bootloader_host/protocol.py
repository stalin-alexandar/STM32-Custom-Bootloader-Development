"""
Bootloader protocol definitions.

Packet structure:
  [LEN:1][CMD:1][DATA:N][CRC32:4]

  LEN = number of bytes after the LEN byte itself
       = 1 (CMD) + N (DATA) + 4 (CRC)

  Max LEN = 249  (firmware rejects 0 or > 249)

Response (on success):
  [0xA5][FOLLOW_LEN][DATA...]

Response (on failure):
  [0x7F]
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

from .crc import stm32_bootloader_crc
from .exceptions import ProtocolError, ValidationError, PacketTooLargeError


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACK = 0xA5
NACK = 0x7F
MAX_PACKET_LEN = 249  # firmware rejects LEN > 249
BL_VER = 0x10  # current bootloader version


class CommandCode(IntEnum):
    """Bootloader command codes as defined in main.h."""

    GET_VER = 0x51
    GET_HELP = 0x52
    GET_CID = 0x53
    GET_RPD_STATUS = 0x54
    GO_TO_ADDR = 0x55
    FLASH_ERASE = 0x56
    MEM_WRITE = 0x57
    MEM_READ = 0x58
    EN_R_W_PROTECT = 0x59
    READ_SECTOR_STATUS = 0x5A
    OTP_READ = 0x5B
    DIS_R_RW_PROTECT = 0x5C


# Human-readable names for display
COMMAND_NAMES: dict[int, str] = {
    0x51: "GET_VER",
    0x52: "GET_HELP",
    0x53: "GET_CID",
    0x54: "GET_RPD_STATUS",
    0x55: "GO_TO_ADDR",
    0x56: "FLASH_ERASE",
    0x57: "MEM_WRITE",
    0x58: "MEM_READ",
    0x59: "EN_R_W_PROTECT",
    0x5A: "READ_SECTOR_STATUS",
    0x5B: "OTP_READ",
    0x5C: "DIS_R_RW_PROTECT",
}


# ---------------------------------------------------------------------------
# Response dataclass
# ---------------------------------------------------------------------------

@dataclass
class BootloaderResponse:
    """Parsed response from the bootloader."""

    ack: bool
    follow_len: int = 0
    data: bytes = field(default_factory=bytes)

    @property
    def as_hex(self) -> str:
        """Return response data as a hex string."""
        return self.data.hex(" ") if self.data else "(empty)"

    def as_int(self) -> int:
        """Interpret response data as a little-endian integer."""
        if len(self.data) == 0:
            return 0
        return int.from_bytes(self.data, "little")


# ---------------------------------------------------------------------------
# Frame builder
# ---------------------------------------------------------------------------

def build_frame(cmd: int, data: bytes = b"") -> bytes:
    """
    Build a complete bootloader request frame.

    Args:
        cmd: Command code byte.
        data: Optional payload data.

    Returns:
        The complete frame bytes ready to send over UART.

    Raises:
        ValidationError: If the packet would exceed size limits.
    """
    body = bytes([cmd]) + data
    length = len(body) + 4  # LEN includes CMD + DATA + CRC

    if not (1 <= length <= MAX_PACKET_LEN):
        raise PacketTooLargeError(
            f"Packet length {length} exceeds valid range [1, {MAX_PACKET_LEN}]. "
            f"Command: 0x{cmd:02X}, data: {len(data)} bytes."
        )

    crc_input = bytes([length]) + body
    crc = stm32_bootloader_crc(crc_input)
    return crc_input + struct.pack("<I", crc)


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------

def parse_response(data: bytes) -> BootloaderResponse:
    """
    Parse a raw response from the bootloader.

    Args:
        data: Raw response bytes including status, follow_len, and payload.

    Returns:
        A BootloaderResponse.

    Raises:
        ProtocolError: If the response is malformed.
    """
    if len(data) < 1:
        raise ProtocolError("Empty response from bootloader")

    status = data[0]

    if status == NACK:
        return BootloaderResponse(ack=False)

    if status != ACK:
        raise ProtocolError(
            f"Unexpected response byte: 0x{status:02X} "
            f"(expected 0x{ACK:02X} or 0x{NACK:02X})"
        )

    if len(data) < 2:
        raise ProtocolError(
            f"ACK response missing follow_len byte: {data.hex()}"
        )

    follow_len = data[1]

    if len(data) < 2 + follow_len:
        raise ProtocolError(
            f"ACK response truncated: expected {2 + follow_len} bytes, "
            f"got {len(data)} bytes"
        )

    payload = data[2:2 + follow_len]
    return BootloaderResponse(ack=True, follow_len=follow_len, data=payload)


# ---------------------------------------------------------------------------
# Convenience: known command payload builders
# ---------------------------------------------------------------------------

def pack_go_to_address(address: int) -> bytes:
    """Pack the payload for GO_TO_ADDR: <I address>."""
    return struct.pack("<I", address)


def pack_flash_erase(sector: int, count: int) -> bytes:
    """Pack the payload for FLASH_ERASE: <B sector><B count>.

    Special values:
        sector=0xFF: mass erase (count is ignored by firmware).
        sector=0-11: erase a specific sector or range.
    """
    if not ((0 <= sector <= 11) or sector == 0xFF):
        raise ValidationError(
            f"Sector {sector} out of range: must be 0-11 or 0xFF (mass erase)"
        )
    if count < 1:
        raise ValidationError(f"Erase count {count} must be >= 1")
    return struct.pack("<BB", sector, count)


def pack_mem_write(address: int, data: bytes) -> bytes:
    """
    Pack the payload for MEM_WRITE: <I address><B length><data...>.

    The length byte is the number of data bytes, not the total payload size.
    """
    payload_len = len(data)
    if payload_len > 239:
        # Max data = 249 - 1(cmd) - 4(addr) - 1(len_byte) - 4(crc) = 239
        raise ValidationError(
            f"Write payload too large: {payload_len} bytes (max 239)"
        )
    return struct.pack("<IB", address, payload_len) + data


def pack_mem_read(address: int, length: int) -> bytes:
    """Pack the payload for MEM_READ: <I address><B length>."""
    if not (1 <= length <= 255):
        raise ValidationError(f"Read length {length} must be in [1, 255]")
    return struct.pack("<IB", address, length)


def pack_otp_read(address: int, length: int) -> bytes:
    """Pack the payload for OTP_READ: <I address><B length>."""
    if not (1 <= length <= 255):
        raise ValidationError(f"OTP read length {length} must be in [1, 255]")
    return struct.pack("<IB", address, length)
