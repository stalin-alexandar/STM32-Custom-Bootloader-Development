"""
CLI interface for the STM32F4 bootloader host tool.

Uses argparse with subcommands for each bootloader operation.
"""

from __future__ import annotations

import argparse
import os
import sys
import struct
from typing import Optional

from .client import BootloaderClient, CommandTrace, list_available_ports, DEFAULT_CHUNK_SIZE
from .exceptions import (
    BootloaderError,
    NackError,
    TimeoutError,
    ValidationError,
)
from .protocol import COMMAND_NAMES


def _create_parser() -> argparse.ArgumentParser:
    """Create the argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="blhost",
        description="STM32F4 Custom Bootloader Host Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  blhost --port COM5 version\n"
            "  blhost --port COM5 chip-id\n"
            "  blhost --port /dev/ttyUSB0 send firmware.bin --erase --go\n"
            "  blhost ports\n"
        ),
    )

    # Global options
    parser.add_argument(
        "--port", "-p",
        help="Serial port (e.g. COM5, /dev/ttyUSB0)",
    )
    parser.add_argument(
        "--baud", "-b",
        type=int,
        default=115200,
        help="Baud rate (default: 115200)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=1.0,
        help="Serial read timeout in seconds (default: 1.0)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose/debug output",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # ports
    subparsers.add_parser("ports", help="List available serial ports")

    # version
    subparsers.add_parser("version", help="Get bootloader version")

    # commands / help
    subparsers.add_parser("commands", help="Get list of supported bootloader commands")

    # chip-id
    subparsers.add_parser("chip-id", help="Get chip identification")

    # rdp-status
    subparsers.add_parser("rdp-status", help="Get read protection status")

    # go
    go_parser = subparsers.add_parser("go", help="Jump to specified address")
    go_parser.add_argument("address", help="Target address (hex or decimal)")

    # erase
    erase_parser = subparsers.add_parser("erase", help="Erase flash sectors")
    erase_parser.add_argument(
        "sector",
        type=_parse_address,
        help="Starting sector number (0-11), or 0xFF for mass erase",
    )
    erase_parser.add_argument(
        "count",
        type=int,
        nargs="?",
        default=1,
        help="Number of sectors to erase (default: 1, ignored for mass erase)",
    )

    # write
    write_parser = subparsers.add_parser("write", help="Write data to memory")
    write_parser.add_argument("address", help="Target address (hex or decimal)")
    write_parser.add_argument(
        "data",
        nargs="?",
        help="Hex data string (e.g. 00112233) or '-' for stdin",
    )
    write_parser.add_argument(
        "--file", "-f",
        help="Read data from binary file instead of inline",
    )

    # read
    read_parser = subparsers.add_parser("read", help="Read memory")
    read_parser.add_argument("address", help="Start address (hex or decimal)")
    read_parser.add_argument("length", type=int, help="Number of bytes to read")
    read_parser.add_argument(
        "--output", "-o",
        help="Save output to file (otherwise prints hex)",
    )
    read_parser.add_argument(
        "--hex",
        action="store_true",
        help="Display output as hex dump",
    )

    # send (high-level firmware update)
    send_parser = subparsers.add_parser("send", help="Send firmware binary to device")
    send_parser.add_argument("file", help="Path to firmware binary file")
    send_parser.add_argument(
        "--address",
        default="0x08008000",
        help="Target flash address (default: 0x08008000)",
    )
    send_parser.add_argument(
        "--chunk-size",
        type=int,
        default=128,
        help="Write chunk size (max 239, default: 128)",
    )
    send_parser.add_argument(
        "--erase",
        action="store_true",
        help="Erase sectors before writing",
    )
    send_parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify written data by reading back",
    )
    send_parser.add_argument(
        "--go",
        action="store_true",
        help="Jump to application after writing",
    )

    # enable-protect
    ep_parser = subparsers.add_parser(
        "enable-protect",
        help="Enable read/write protection on sectors",
    )
    ep_parser.add_argument(
        "sectors",
        type=int,
        nargs="+",
        help="Sector numbers to protect",
    )

    # disable-protect
    dp_parser = subparsers.add_parser(
        "disable-protect",
        help="Disable read/write protection on sectors",
    )
    dp_parser.add_argument(
        "sectors",
        type=int,
        nargs="+",
        help="Sector numbers to unprotect",
    )

    # sector-status
    subparsers.add_parser(
        "sector-status",
        help="Get sector protection status",
    )

    # otp-read
    otp_parser = subparsers.add_parser("otp-read", help="Read OTP memory")
    otp_parser.add_argument("address", help="OTP address (hex or decimal)")
    otp_parser.add_argument("length", type=int, help="Number of bytes to read")

    # raw (for bring-up and debugging)
    raw_parser = subparsers.add_parser(
        "raw",
        help="Send a raw command (for debugging/bring-up)",
    )
    raw_parser.add_argument(
        "--cmd", required=True,
        help="Command code in hex (e.g. 0x51)",
    )
    raw_parser.add_argument(
        "--data",
        default="",
        help="Hex data payload (e.g. 00008008)",
    )

    return parser


def _parse_address(addr_str: str) -> int:
    """Parse a hex or decimal address string."""
    if addr_str.startswith("0x") or addr_str.startswith("0X"):
        return int(addr_str, 16)
    return int(addr_str)


def _print_trace(trace: CommandTrace) -> None:
    """Print a command trace (raw hex frames) for verbose CLI mode."""
    print(f"  SENT  → {trace.request_hex}")
    print(f"  RECV  ← {trace.response_hex}")
    if trace.error:
        print(f"  NOTE  · {trace.error}")


def _format_hex_dump(data: bytes, base_addr: int = 0) -> str:
    """Format bytes as a hex dump with addresses."""
    lines = []
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        # Pad hex part
        hex_part = hex_part.ljust(47)
        ascii_part = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        lines.append(f"{base_addr + i:08X}: {hex_part} {ascii_part}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point. Returns exit code."""
    parser = _create_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 1

    # Handle the ports command specially (no serial connection needed)
    if args.command == "ports":
        ports = list_available_ports()
        if not ports:
            print("No serial ports found.")
            return 0
        print("Available serial ports:")
        for p in ports:
            print(f"  {p['device']:20s} {p['description']}")
        return 0

    # All other commands require --port
    if not args.port:
        parser.error("the following arguments are required: --port/-p")

    # Create client and execute command
    try:
        trace_cb = _print_trace if args.verbose else None
        with BootloaderClient(
            port=args.port,
            baudrate=args.baud,
            timeout=args.timeout,
            trace_callback=trace_cb,
        ) as bl:
            if args.verbose:
                print(f"Connected to {args.port} at {args.baud} baud")
                sys.stdout.flush()

            if args.command == "version":
                ver = bl.get_version()
                print(f"Bootloader version: 0x{ver:02X} ({ver})")

            elif args.command == "commands":
                data = bl.get_help()
                if data:
                    print("Supported commands:")
                    for b in data:
                        name = COMMAND_NAMES.get(b, "UNKNOWN")
                        print(f"  0x{b:02X} {name}")
                else:
                    # If GET_HELP returns empty, show known command table
                    print("Bootloader command codes:")
                    for code, name in sorted(COMMAND_NAMES.items()):
                        print(f"  0x{code:02X}  {name}")

            elif args.command == "chip-id":
                cid = bl.get_chip_id()
                print(f"Chip ID: 0x{cid:04X}")

            elif args.command == "rdp-status":
                status = bl.get_rdp_status()
                level_names = {0: "Level 0 (no protection)", 1: "Level 1 (read protection)", 2: "Level 2 (no debug)"}
                level_name = level_names.get(status, f"Unknown (0x{status:02X})")
                print(f"RDP Status: 0x{status:02X} ({level_name})")

            elif args.command == "go":
                addr = _parse_address(args.address)
                print(f"Jumping to 0x{addr:08X}...")
                try:
                    bl.go_to_address(addr)
                    # If we get a response, print it
                    print("GO_TO_ADDR command acknowledged")
                except NackError:
                    print("Error: Bootloader rejected the jump command")

            elif args.command == "erase":
                sector = args.sector
                count = args.count

                if sector == 0xFF:
                    print("Mass erasing all flash sectors...")
                    confirm = input(
                        "WARNING: This will erase ALL flash including the bootloader! "
                        "Type 'yes' to confirm: "
                    )
                    if confirm.lower() != "yes":
                        print("Aborted.")
                        return 1
                else:
                    if sector < 2:
                        print(
                            "WARNING: Sectors 0-1 are the bootloader! "
                            "Erasing them will brick the device."
                        )
                        confirm = input("Type 'yes' to confirm: ")
                        if confirm.lower() != "yes":
                            print("Aborted.")
                            return 1
                    print(f"Erasing sectors {sector}-{sector + count - 1}...")

                bl.flash_erase(sector, count)
                print("Erase complete")

            elif args.command == "write":
                addr = _parse_address(args.address)
                if args.file:
                    with open(args.file, "rb") as f:
                        data = f.read()
                    print(f"Read {len(data)} bytes from {args.file}")
                elif args.data:
                    if args.data == "-":
                        data = sys.stdin.buffer.read()
                    else:
                        data = bytes.fromhex(args.data)
                else:
                    print("Error: must provide --file, inline data, or '-' for stdin")
                    return 1

                print(f"Writing {len(data)} bytes to 0x{addr:08X}...")
                if len(data) > 239:
                    print(f"Payload exceeds single-write limit; sending in {DEFAULT_CHUNK_SIZE}-byte chunks...")
                for offset in range(0, len(data), DEFAULT_CHUNK_SIZE):
                    chunk = data[offset:offset + DEFAULT_CHUNK_SIZE]
                    bl.mem_write(addr + offset, chunk)
                print("Write complete")

            elif args.command == "read":
                addr = _parse_address(args.address)
                length = args.length

                print(f"Reading {length} bytes from 0x{addr:08X}...")
                data = bl.mem_read(addr, length)
                print(f"Read {len(data)} bytes")

                if args.output:
                    with open(args.output, "wb") as f:
                        f.write(data)
                    print(f"Saved to {args.output}")
                else:
                    if args.hex:
                        print(_format_hex_dump(data, addr))
                    else:
                        # Print hex string
                        print(data.hex(" "))

            elif args.command == "send":
                addr = _parse_address(args.address)

                result = bl.send_file(
                    file_path=args.file,
                    address=addr,
                    chunk_size=args.chunk_size,
                    erase=args.erase,
                    verify=args.verify,
                    go=args.go,
                )

                # Print summary
                print()
                print("Firmware update summary:")
                print(f"  File:     {result['file']}")
                print(f"  Size:     {result['size']} bytes")
                print(f"  Address:  0x{result['address']:08X} - 0x{result['end_address']:08X}")
                print(f"  Chunks:   {result['chunks']}")
                print(f"  Sectors:  {result['sectors']}")
                print(f"  Erased:   {'Yes' if result['erased'] else 'No'}")
                print(f"  Verified: {'Yes' if result['verified'] else 'No'}")
                print(f"  Jumped:   {'Yes' if result['jumped'] else 'No'}")
                print("Done.")

            elif args.command == "enable-protect":
                print(f"Enabling protection on sectors: {args.sectors}")
                bl.enable_rw_protect(args.sectors)
                print("Protection enabled")

            elif args.command == "disable-protect":
                print(f"Disabling protection on sectors: {args.sectors}")
                bl.disable_rw_protect(args.sectors)
                print("Protection disabled")

            elif args.command == "sector-status":
                data = bl.read_sector_status()
                if data:
                    print("Sector protection status:")
                    for i, b in enumerate(data[:12]):
                        status = "Protected" if b else "Unprotected"
                        print(f"  Sector {i:2d}: {status} (0x{b:02X})")
                else:
                    print("No sector status data returned")

            elif args.command == "otp-read":
                addr = _parse_address(args.address)
                data = bl.otp_read(addr, args.length)
                print(f"OTP read {len(data)} bytes from 0x{addr:08X}:")
                print(_format_hex_dump(data, addr))

            elif args.command == "raw":
                cmd_byte = int(args.cmd, 16) if args.cmd.startswith("0x") else int(args.cmd)
                data_bytes = bytes.fromhex(args.data) if args.data else b""

                if args.verbose:
                    print(f"Sending raw: cmd=0x{cmd_byte:02X}, data={data_bytes.hex()}")
                    from .protocol import build_frame
                    frame = build_frame(cmd_byte, data_bytes)
                    print(f"Frame: {frame.hex(' ')}")

                resp = bl.command(cmd_byte, data_bytes)
                print(f"ACK received, follow_len={resp.follow_len}")
                if resp.data:
                    print(f"Response data: {resp.data.hex(' ')}")
                else:
                    print("Response data: (empty)")

            else:
                print(f"Unknown command: {args.command}")
                return 1

    except BootloaderError as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
