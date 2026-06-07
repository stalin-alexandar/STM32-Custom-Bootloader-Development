"""
Typed exception hierarchy for the STM32F4 bootloader host.
"""


class BootloaderError(Exception):
    """Base exception for all bootloader host errors."""


class SerialOpenError(BootloaderError):
    """Could not open the serial port."""


class ConnectionError(BootloaderError):
    """Serial communication error (lost connection, etc.)."""


class TimeoutError(BootloaderError):
    """No response received from the bootloader within the timeout period."""


class NackError(BootloaderError):
    """Bootloader responded with NACK, indicating the command was rejected."""


class ProtocolError(BootloaderError):
    """Unexpected or malformed response from the bootloader."""


class CrcError(BootloaderError):
    """CRC mismatch detected (host-side validation)."""


class ValidationError(BootloaderError):
    """Invalid input parameters (address out of range, bad length, etc.)."""


class PacketTooLargeError(ValidationError):
    """The constructed packet exceeds the bootloader's maximum size."""
