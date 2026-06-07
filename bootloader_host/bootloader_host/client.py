"""
Serial client for communicating with the STM32F4 bootloader.

Provides a context manager, generic command send/receive, and
high-level convenience methods for each bootloader command.
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass, field
from typing import Optional, Callable

import serial
from serial.tools import list_ports

from .exceptions import (
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
    CommandCode,
    BootloaderResponse,
    build_frame,
    pack_flash_erase,
    pack_go_to_address,
    pack_mem_read,
    pack_mem_write,
    pack_otp_read,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_BAUDRATE = 115200
DEFAULT_TIMEOUT = 1.0
DEFAULT_ERASE_TIMEOUT = 5.0
DEFAULT_WRITE_TIMEOUT = 3.0
DEFAULT_CHUNK_SIZE = 128

SECTOR2_ADDRESS = 0x08008000
FLASH_SECTOR_SIZES = [
    0x4000,  # Sector 0: 16KB
    0x4000,  # Sector 1: 16KB
    0x4000,  # Sector 2: 16KB
    0x4000,  # Sector 3: 16KB
    0x10000, # Sector 4: 64KB
    0x20000, # Sector 5: 128KB
    0x20000, # Sector 6: 128KB
    0x20000, # Sector 7: 128KB
    0x20000, # Sector 8: 128KB
    0x20000, # Sector 9: 128KB
    0x20000, # Sector 10: 128KB
    0x20000, # Sector 11: 128KB
]

# Sectors 0 and 1 are the bootloader — never erase them
BOOTLOADER_SECTORS = {0, 1}


# ---------------------------------------------------------------------------
# Command trace dataclass
# ---------------------------------------------------------------------------


@dataclass
class CommandTrace:
    """
    Captures the raw request and response bytes for one bootloader command.
    Emitted as a side-effect by BootloaderClient.command() when a
    trace_callback is configured.
    """
    cmd: int
    request: bytes
    response: bytes = b""
    error: str = ""

    @property
    def request_hex(self) -> str:
        return self.request.hex(" ") if self.request else "(empty)"

    @property
    def response_hex(self) -> str:
        return self.response.hex(" ") if self.response else "(no data)"

    @property
    def command_name(self) -> str:
        try:
            return CommandCode(self.cmd).name
        except Exception:
            return f"0x{self.cmd:02X}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def list_available_ports() -> list[dict]:
    """Return a list of available serial ports with description."""
    ports = []
    for p in list_ports.comports():
        ports.append({
            "device": p.device,
            "description": p.description,
            "hwid": p.hwid,
        })
    return ports


def get_sector_for_address(address: int) -> int:
    """Return the flash sector number containing the given address."""
    addr = address & 0x0FFFFFFF  # mask off the flash base
    offset = 0
    for sector, size in enumerate(FLASH_SECTOR_SIZES):
        if offset <= addr < offset + size:
            return sector
        offset += size
    raise ValidationError(f"Address 0x{address:08X} is not in flash range")


def get_sectors_for_range(start: int, end: int) -> list[int]:
    """Return the list of sectors covered by [start, end) address range."""
    sectors: set[int] = set()
    addr = start
    while addr < end:
        sectors.add(get_sector_for_address(addr))
        # Jump to start of next sector
        offset = addr & 0x0FFFFFFF
        cum = 0
        for s, size in enumerate(FLASH_SECTOR_SIZES):
            cum += size
            if offset < cum:
                addr = (addr & 0xFFF00000) | (cum & 0x000FFFFF)
                break
    return sorted(sectors)


# ---------------------------------------------------------------------------
# Client class
# ---------------------------------------------------------------------------

class BootloaderClient:
    """
    Client for communicating with the STM32F4 bootloader over UART.

    Usage:
        with BootloaderClient(port="COM5") as bl:
            ver = bl.get_version()
    """

    def __init__(
        self,
        port: str,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout: float = DEFAULT_TIMEOUT,
        write_timeout: Optional[float] = None,
        trace_callback: Optional[Callable[[CommandTrace], None]] = None,
    ):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.write_timeout = write_timeout
        self.trace_callback = trace_callback
        self.last_trace: Optional[CommandTrace] = None
        self._serial: Optional[serial.Serial] = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> BootloaderClient:
        self.open()
        return self

    def __exit__(self, *args) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Serial port management
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open the serial port."""
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=self.timeout,
                write_timeout=self.write_timeout or self.timeout,
            )
        except serial.SerialException as e:
            raise SerialOpenError(
                f"Failed to open port '{self.port}': {e}"
            ) from e

    def close(self) -> None:
        """Close the serial port."""
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except Exception:
                pass
        self._serial = None

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    # ------------------------------------------------------------------
    # Low-level I/O
    # ------------------------------------------------------------------

    def _read_exact(self, n: int, timeout: Optional[float] = None) -> bytes:
        """Read exactly n bytes from the serial port."""
        if self._serial is None or not self._serial.is_open:
            raise ConnectionError("Serial port is not open")

        old_timeout = None
        if timeout is not None:
            old_timeout = self._serial.timeout
            self._serial.timeout = timeout

        try:
            data = self._serial.read(n)
            if len(data) < n:
                raise TimeoutError(
                    f"Timeout: expected {n} bytes, got {len(data)} after "
                    f"{timeout or self.timeout}s"
                )
            return data
        finally:
            if old_timeout is not None:
                self._serial.timeout = old_timeout

    # ------------------------------------------------------------------
    # Trace emission
    # ------------------------------------------------------------------

    def _emit_trace(
        self,
        cmd: int,
        request: bytes,
        response: bytes = b"",
        error: str = "",
    ) -> None:
        """Build a CommandTrace and pass it to the trace_callback (if set)."""
        trace = CommandTrace(cmd=cmd, request=request,
                              response=response, error=error)
        self.last_trace = trace
        if self.trace_callback:
            try:
                self.trace_callback(trace)
            except Exception:
                pass  # Never let debug tracing break real protocol execution

    # ------------------------------------------------------------------
    # Generic command
    # ------------------------------------------------------------------

    def command(
        self,
        cmd: int,
        data: bytes = b"",
        timeout: Optional[float] = None,
    ) -> BootloaderResponse:
        """
        Send a command to the bootloader and read the response.

        Args:
            cmd: Command code byte.
            data: Optional payload data.
            timeout: Read timeout in seconds (defaults to self.timeout).

        Returns:
            Parsed BootloaderResponse.

        Raises:
            NackError: Bootloader rejected the command.
            TimeoutError: No timely response.
            ProtocolError: Malformed response.
        """
        frame = build_frame(cmd, data)
        raw_response = bytearray()
        error_text = ""

        try:
            # Flush any stale input before sending
            self._serial.reset_input_buffer()
            self._serial.write(frame)
            self._serial.flush()

            # Read status byte
            status_byte = self._read_exact(1, timeout)
            raw_response += status_byte

            if status_byte[0] == NACK:
                raise NackError(
                    f"Bootloader NACKed command 0x{cmd:02X} ({CommandCode(cmd).name})"
                )

            if status_byte[0] != ACK:
                raise ProtocolError(
                    f"Unexpected response byte 0x{status_byte[0]:02X} "
                    f"(expected 0x{ACK:02X} or 0x{NACK:02X})"
                )

            # Read follow_len
            follow_len_bytes = self._read_exact(1, timeout)
            raw_response += follow_len_bytes
            follow_len = follow_len_bytes[0]

            # Read payload
            payload = self._read_exact(follow_len, timeout)
            raw_response += payload

            return BootloaderResponse(
                ack=True,
                follow_len=follow_len,
                data=payload,
            )
        except Exception as e:
            error_text = str(e)
            raise
        finally:
            self._emit_trace(
                cmd=cmd,
                request=frame,
                response=bytes(raw_response),
                error=error_text,
            )

    # ------------------------------------------------------------------
    # High-level command methods
    # ------------------------------------------------------------------

    def get_version(self) -> int:
        """
        Get the bootloader version.

        Returns:
            Version byte (e.g. 0x10).
        """
        resp = self.command(CommandCode.GET_VER)
        if resp.follow_len >= 1:
            return resp.data[0]
        raise ProtocolError("GET_VER response had no data")

    def get_help(self) -> bytes:
        """
        Get the list of supported commands from the bootloader.
        """
        resp = self.command(CommandCode.GET_HELP)
        return resp.data

    def get_chip_id(self) -> int:
        """
        Get the chip identification (DBGMCU_IDCODE).

        Returns:
            Chip ID as integer (e.g. 0x0413 for STM32F407VG).
        """
        resp = self.command(CommandCode.GET_CID)
        if resp.follow_len >= 2:
            return int.from_bytes(resp.data[:2], "little")
        raise ProtocolError("GET_CID response had insufficient data")

    def get_rdp_status(self) -> int:
        """
        Get the read protection status.

        Returns:
            RDP level byte.
        """
        resp = self.command(CommandCode.GET_RPD_STATUS)
        if resp.follow_len >= 1:
            return resp.data[0]
        raise ProtocolError("GET_RPD_STATUS response had no data")

    def go_to_address(self, address: int) -> BootloaderResponse:
        """
        Jump to the specified address.
        """
        return self.command(
            CommandCode.GO_TO_ADDR,
            pack_go_to_address(address),
        )

    def flash_erase(
        self,
        sector: int,
        count: int,
        timeout: Optional[float] = DEFAULT_ERASE_TIMEOUT,
    ) -> BootloaderResponse:
        """
        Erase flash sectors.

        Args:
            sector: Starting sector number (0-11), or 0xFF for mass erase.
            count: Number of sectors to erase (ignored for mass erase).
            timeout: Longer timeout for erase operations.

        Raises:
            ValidationError: If trying to erase bootloader sectors (0-1).
        """
        if sector == 0xFF:
            # Mass erase — skip individual sector checks
            pass
        else:
            # Protect bootloader sectors
            for s in range(sector, sector + count):
                if s in BOOTLOADER_SECTORS:
                    raise ValidationError(
                        f"Cannot erase bootloader sector {s} (sectors {BOOTLOADER_SECTORS} "
                        f"are reserved for the bootloader)"
                    )
        return self.command(
            CommandCode.FLASH_ERASE,
            pack_flash_erase(sector, count),
            timeout=timeout,
        )

    def mem_write(
        self,
        address: int,
        data: bytes,
        timeout: Optional[float] = DEFAULT_WRITE_TIMEOUT,
    ) -> BootloaderResponse:
        """
        Write data to memory (flash or RAM).

        The data is limited to 239 bytes per call.
        For larger writes, use send_file() which handles chunking.
        """
        return self.command(
            CommandCode.MEM_WRITE,
            pack_mem_write(address, data),
            timeout=timeout,
        )

    def mem_read(
        self,
        address: int,
        length: int,
        timeout: Optional[float] = None,
    ) -> bytes:
        """
        Read memory from the specified address.

        Returns:
            Raw bytes read from the device.
        """
        resp = self.command(
            CommandCode.MEM_READ,
            pack_mem_read(address, length),
            timeout=timeout,
        )
        return resp.data

    def _build_sector_mask(self, sectors: list[int]) -> int:
        """Build a sector bitmask from a list of sector numbers (0-11)."""
        mask = 0
        for sector in sectors:
            if not (0 <= sector <= 11):
                raise ValidationError(
                    f"Sector {sector} out of range (must be 0-11)"
                )
            mask |= (1 << sector)
        return mask

    def enable_rw_protect(self, sectors: list[int], mode: int = 1) -> BootloaderResponse:
        """
        Enable read/write protection on specified sectors.

        Args:
            sectors: List of sector numbers (0-11) to protect.
            mode: Protection mode — 1=WRP (write protection), 2=PCROP.
        """
        if not sectors:
            raise ValidationError("At least one sector must be specified")
        if mode not in (1, 2):
            raise ValidationError("Protection mode must be 1 (WRP) or 2 (PCROP)")
        mask = self._build_sector_mask(sectors)
        data = struct.pack("<BB", mask, mode)
        return self.command(CommandCode.EN_R_W_PROTECT, data)

    def read_sector_status(self) -> bytes:
        """
        Get the sector protection status.
        """
        resp = self.command(CommandCode.READ_SECTOR_STATUS)
        return resp.data

    def otp_read(self, address: int, length: int) -> bytes:
        """
        Read OTP memory.
        """
        resp = self.command(
            CommandCode.OTP_READ,
            pack_otp_read(address, length),
        )
        return resp.data

    def disable_rw_protect(self, sectors: list[int]) -> BootloaderResponse:
        """
        Disable read/write protection on specified sectors.

        Args:
            sectors: List of sector numbers (0-11) to unprotect.
        """
        if not sectors:
            raise ValidationError("At least one sector must be specified")
        mask = self._build_sector_mask(sectors)
        data = struct.pack("<B", mask)
        return self.command(CommandCode.DIS_R_RW_PROTECT, data)

    # ------------------------------------------------------------------
    # High-level send firmware
    # ------------------------------------------------------------------

    def send_file(
        self,
        file_path: str,
        address: int = SECTOR2_ADDRESS,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        erase: bool = False,
        verify: bool = False,
        go: bool = False,
        progress_callback: Optional[callable] = None,
    ) -> dict:
        """
        Send a firmware binary to the device.

        This is the high-level convenience for firmware updates.

        Args:
            file_path: Path to the binary file.
            address: Start address to write to.
            chunk_size: Bytes per write chunk (max 239).
            erase: If True, erase the necessary sectors first.
            verify: If True, read back and verify after writing.
            go: If True, jump to the application after writing.
            progress_callback: Optional callable(chunk_index, total_chunks).

        Returns:
            Dict with summary info.
        """
        if not os.path.isfile(file_path):
            raise ValidationError(f"File not found: {file_path}")

        with open(file_path, "rb") as f:
            firmware = f.read()

        file_size = len(firmware)
        end_address = address + file_size

        if chunk_size > 239:
            raise ValidationError(f"Chunk size {chunk_size} exceeds max of 239")

        # Calculate sector info
        sectors_needed = get_sectors_for_range(address, end_address)

        # Erase if requested
        if erase:
            # Verify no bootloader sectors
            for s in sectors_needed:
                if s in BOOTLOADER_SECTORS:
                    raise ValidationError(
                        f"Address range includes bootloader sector {s}. "
                        f"Cannot write to sectors {BOOTLOADER_SECTORS}."
                    )

            first_sector = sectors_needed[0]
            sector_count = len(sectors_needed)
            print(f"Erasing sectors {first_sector}-{first_sector + sector_count - 1}...")
            self.flash_erase(first_sector, sector_count)

        # Write chunks
        total_chunks = (file_size + chunk_size - 1) // chunk_size
        for i in range(0, file_size, chunk_size):
            chunk = firmware[i:i + chunk_size]
            chunk_addr = address + i
            chunk_index = i // chunk_size

            self.mem_write(chunk_addr, chunk)

            if progress_callback:
                progress_callback(chunk_index, total_chunks)
            else:
                pct = (i + len(chunk)) * 100 // file_size
                print(
                    f"\r  Writing... [{pct:3d}%] {i//chunk_size + 1}/{total_chunks} chunks",
                    end="",
                    flush=True,
                )

        print()

        # Verify if requested
        if verify:
            print("Verifying...")
            for i in range(0, file_size, chunk_size):
                chunk_size_actual = min(chunk_size, file_size - i)
                read_back = self.mem_read(address + i, chunk_size_actual)
                expected = firmware[i:i + chunk_size_actual]
                if read_back != expected:
                    raise CrcError(
                        f"Verification failed at offset 0x{i:X}: data mismatch"
                    )
            print("Verification OK")

        # Jump if requested
        if go:
            print(f"Jumping to 0x{address:08X}...")
            try:
                self.go_to_address(address)
            except (TimeoutError, NackError) as e:
                # Timeout is expected — the device jumps away and stops responding
                print(f"  (Expected: {e})")
            print("Jump command sent")

        return {
            "file": file_path,
            "size": file_size,
            "address": address,
            "end_address": end_address,
            "chunks": total_chunks,
            "sectors": sectors_needed,
            "erased": erase,
            "verified": verify,
            "jumped": go,
        }
