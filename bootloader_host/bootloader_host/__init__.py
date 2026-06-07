"""
STM32F4 Custom Bootloader Host Tool.

A Python-based host tool for communicating with the STM32F4 bootloader
over UART using pyserial.
"""

from .client import BootloaderClient, list_available_ports
from .exceptions import (
    BootloaderError,
    ConnectionError,
    CrcError,
    NackError,
    ProtocolError,
    SerialOpenError,
    TimeoutError,
    ValidationError,
)
from .protocol import (
    ACK,
    NACK,
    BL_VER,
    CommandCode,
    BootloaderResponse,
    build_frame,
    COMMAND_NAMES,
)
from . import gui  # noqa: F401 — import so ``gui`` submodule is accessible

__version__ = "0.1.0"
__all__ = [
    "BootloaderClient",
    "BootloaderResponse",
    "CommandCode",
    "BootloaderError",
    "SerialOpenError",
    "ConnectionError",
    "TimeoutError",
    "NackError",
    "ProtocolError",
    "CrcError",
    "ValidationError",
    "build_frame",
    "list_available_ports",
    "COMMAND_NAMES",
    "gui",
    "ACK",
    "NACK",
    "BL_VER",
]
