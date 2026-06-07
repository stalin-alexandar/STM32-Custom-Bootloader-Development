"""
STM32 HAL-compatible CRC32 implementation.

Matches the bootloader firmware's CRC computation:
  - Polynomial: 0x04C11DB7
  - Init value: 0xFFFFFFFF
  - No final XOR
  - No input/output reflection
  - Each byte is processed as a 32-bit word (0x000000XX)
"""

import struct

POLY = 0x04C11DB7
INIT = 0xFFFFFFFF


def _stm32_crc_word(crc: int, word: int) -> int:
    """Process one 32-bit word through the STM32 CRC engine (bitwise)."""
    crc &= 0xFFFFFFFF
    word &= 0xFFFFFFFF
    for i in range(32):
        bit = (word >> (31 - i)) & 1
        top = (crc >> 31) & 1
        crc = (crc << 1) & 0xFFFFFFFF
        if top ^ bit:
            crc ^= POLY
    return crc & 0xFFFFFFFF


def stm32_bootloader_crc(data: bytes) -> int:
    """
    Compute the CRC as the STM32 bootloader firmware does.

    Each byte in `data` is fed to the CRC engine as a 32-bit word
    with the byte in the low byte and zeros in the upper 24 bits:
        0x000000XX

    Returns a 32-bit integer CRC value.
    """
    crc = INIT
    for b in data:
        crc = _stm32_crc_word(crc, b)
    return crc & 0xFFFFFFFF


def stm32_bootloader_crc_bytes(data: bytes) -> bytes:
    """
    Compute the CRC as the firmware does, returning a 4-byte little-endian value.

    This is suitable for direct appending to a bootloader frame.
    """
    return struct.pack("<I", stm32_bootloader_crc(data))
