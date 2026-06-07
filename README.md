# STM32F4 Custom Bootloader Development

A complete STM32F407VGTx bootloader solution with UART bootloader firmware, a Python CLI tool, and a Tkinter GUI for firmware updates, memory operations, and device inspection.

---

## Overview

This repository contains an end-to-end custom bootloader system for the STM32F407VGTx (STM32F4-Discovery board). The embedded firmware implements a UART-based command protocol with CRC verification, flash programming, memory access, protection control, and application jump support. The repository also includes a Python host package with both a command-line tool (`blhost`) and a Tkinter GUI for firmware upload, inspection, and debugging.

---

## Key Features

### Firmware
- **B1 Button Entry** — enter bootloader mode on press, or auto-jump to application
- **UART Command Interface** — USART2 at 115200 baud for host communication
- **Debug Output** — USART3 for bootloader diagnostic messages
- **Hardware CRC Verification** — uses STM32 CRC peripheral for packet integrity
- **ACK/NACK Protocol** — `0xA5` success, `0x7F` failure response framing
- **All 12 Bootloader Commands Implemented** — version, chip ID, memory R/W, flash erase, OTP, protection control, address jump
- **Full System Reset Before Application Jump** — NVIC, SysTick, RCC, HAL, VTOR all cleaned up

### Python Host Tools
- **`blhost` CLI** — subcommands for every bootloader operation
- **Tkinter GUI (`blhost-gui`)** — dark neon-themed desktop app with progress tracking
- **STM32-compatible CRC32** — firmware-accurate CRC generation in Python
- **Chunked Firmware Transfer** — configurable chunk sizes up to 239 bytes
- **High-level `send` Workflow** — erase, write, verify, and jump in one command
- **Serial Port Auto-detection** — lists available COM/USB-serial ports
- **Unit Tests** — protocol and CRC tests in `bootloader_host/tests/`

---

## How It Works

### Boot Sequence

1. MCU resets and the bootloader initializes HAL, GPIO, CRC, USART2, and USART3.
2. It reads the **B1 button** (PA0):
   - **Button PRESSED (HIGH)** → stay in bootloader mode, wait for UART commands on USART2
   - **Button NOT PRESSED (LOW)** → validate the user application at `0x08008000` and jump to it

### Command Protocol

Each command follows this packet structure:

```
Request:  [LEN][CMD][DATA...][CRC32_LE]
Response: [0xA5][FOLLOW_LEN][DATA...]   (success)
          [0x7F]                          (failure)
```

- **LEN** = number of bytes after the LEN byte (`1 + N + 4`)
- **CRC32** is computed over `LEN + CMD + DATA` using the STM32 hardware CRC algorithm
- Firmware rejects packets where LEN is 0 or greater than 249

### Application Jump Sequence

When launching the user application, the bootloader performs a comprehensive cleanup:

1. Validates MSP and reset handler address at `0x08008000`
2. Disables all interrupts globally
3. Stops SysTick timer
4. Clears all NVIC pending and enabled interrupts
5. Deinitializes all HAL peripherals
6. Resets RCC clock configuration back to HSI default
7. Resets flash wait states
8. Updates VTOR to the application vector table
9. Clears the button EXTI interrupt
10. Sets MSP to the application's initial stack pointer
11. Jumps to the application reset handler (never returns)

---

## Complete Command Reference

| Code | Command | Description | Request Data | Response Payload |
|------|---------|-------------|--------------|------------------|
| `0x51` | `BL_GET_VER` | Get bootloader version | none | 1 byte (`0x30`) |
| `0x52` | `BL_GET_HELP` | List supported commands | none | command code bytes |
| `0x53` | `BL_GET_CID` | Get MCU chip ID | none | 2-byte chip ID |
| `0x54` | `BL_GET_RPD_STATUS` | Get read protection level | none | 1-byte RDP level |
| `0x55` | `BL_GO_TO_ADDR` | Jump to address | 4-byte address | 1 byte (valid/invalid) |
| `0x56` | `BL_FLASH_ERASE` | Erase flash sectors | sector + count | 1 byte erase status |
| `0x57` | `BL_MEM_WRITE` | Write to flash/RAM | addr + len + data | 1 byte write status |
| `0x58` | `BL_MEM_READ` | Read memory | addr + len | returned bytes |
| `0x59` | `BL_EN_R_W_PROTECT` | Enable WRP/PCROP protection | sector mask + mode | 1 byte status |
| `0x5A` | `BL_READ_SECTOR_STATUS` | Read sector protection status | none | 2-byte protection mask |
| `0x5B` | `BL_OTP_READ` | Read OTP memory | addr + len | returned bytes |
| `0x5C` | `BL_DIS_R_RW_PROTECT` | Disable protection | sector mask | 1 byte status |

---

## Memory Layout

```
0x08000000 - 0x08007FFF   Bootloader (32 KB, Sectors 0-1)
0x08008000 - 0x080FFFFF   User Application (992 KB, Sectors 2-11)
```

### Flash Sector Map

| Sector | Address Range | Size | Usage |
|--------|---------------|------|-------|
| 0 | 0x08000000 - 0x08003FFF | 16 KB | Bootloader |
| 1 | 0x08004000 - 0x08007FFF | 16 KB | Bootloader |
| 2 | 0x08008000 - 0x0800BFFF | 16 KB | Application |
| 3 | 0x0800C000 - 0x0800FFFF | 16 KB | Application |
| 4 | 0x08010000 - 0x0801FFFF | 64 KB | Application |
| 5 | 0x08020000 - 0x0803FFFF | 128 KB | Application |
| 6 | 0x08040000 - 0x0805FFFF | 128 KB | Application |
| 7 | 0x08060000 - 0x0807FFFF | 128 KB | Application |
| 8 | 0x08080000 - 0x0809FFFF | 128 KB | Application |
| 9 | 0x080A0000 - 0x080BFFFF | 128 KB | Application |
| 10 | 0x080C0000 - 0x080DFFFF | 128 KB | Application |
| 11 | 0x080E0000 - 0x080FFFFF | 128 KB | Application |

---

## Hardware Requirements

- **Board**: STM32F4-Discovery (STM32F407G-DISC1)
- **MCU**: STM32F407VGTx (1024 KB Flash, 128 KB RAM, 64 KB CCMRAM)
- **Programmer**: ST-LINK for flashing the bootloader
- **USB-UART Adapter**: for command interface (e.g., CP2102, CH340, FTDI)
- **Python 3.9+**: for host tools

### Pin Configuration

| Pin | Function | Connection |
|-----|----------|------------|
| PA0 | B1 Button | Internal pulldown, active HIGH for bootloader entry |
| PA2 | USART2 TX | Connect to USB-UART RX |
| PA3 | USART2 RX | Connect to USB-UART TX |
| PD8 | USART3 TX | Connect to USB-UART RX (optional, debug output) |
| PD12-PD15 | LEDs | LD4-LD3-LD5-LD6 status indicators |

---

## Getting Started

### 1. Build and Flash the Bootloader

1. Clone the repository:
```bash
git clone https://github.com/stalin-alexandar/STM32-Custom-Bootloader-Development.git
cd STM32-Custom-Bootloader-Development
```

2. Open in STM32CubeIDE and build the project.

3. Flash to the board via ST-LINK.

### 2. Enter Bootloader Mode

1. **Hold** the B1 button (blue button on Discovery board)
2. **Press and release** the RESET button (black button)
3. **Release** the B1 button
4. Bootloader is now active and waiting for UART commands on USART2

If B1 is **not pressed** during reset, the bootloader automatically jumps to the user application at `0x08008000`.

### 3. Install the Python Host Tool

```bash
cd bootloader_host
pip install -e .
```

This installs two commands:
- **`blhost`** — command-line interface
- **`blhost-gui`** — Tkinter GUI application

### 4. Use the CLI

```bash
# List available serial ports
blhost ports

# Get bootloader version
blhost --port COM5 version

# Get chip ID
blhost --port COM5 chip-id

# List supported commands
blhost --port COM5 commands

# Read memory
blhost --port COM5 read 0x08008000 64 --hex

# Erase flash sectors (never erase sectors 0-1!)
blhost --port COM5 erase 2 4

# Full firmware update: erase, write, verify, and jump
blhost --port COM5 send firmware.bin --erase --verify --go

# Verbose mode with raw frame tracing
blhost --port COM5 --verbose version
```

### 5. Use the GUI

```bash
blhost-gui
```

The GUI provides:
- COM port and baud rate selection
- Command dropdown with descriptions
- Dynamic parameter forms
- Progress bar for firmware transfers
- Scrolling log output with color-coded messages
- Keyboard shortcuts (Enter to execute, F5 to refresh ports, Ctrl+L to clear log)

---

## Firmware Update Workflow

The typical workflow for updating application firmware:

1. **Build your application** linked to `0x08008000`:
```ld
MEMORY
{
  FLASH (rx)  : ORIGIN = 0x08008000, LENGTH = 992K
  RAM (xrw)   : ORIGIN = 0x20000000, LENGTH = 128K
}
```

2. **Relocate the vector table** in your application:
```c
SCB->VTOR = 0x08008000;
```

3. **Generate the binary**:
```bash
arm-none-eabi-objcopy -O binary Application.elf Application.bin
```

4. **Enter bootloader mode** (hold B1, reset, release B1)

5. **Run the update**:
```bash
blhost --port COM5 send Application.bin --erase --verify --go
```

What `send` does:
- Calculates which sectors need erasing
- Optionally erases those sectors (never touches sectors 0-1)
- Writes the binary in chunks (default 128 bytes)
- Optionally reads back flash contents for verification
- Optionally issues a jump to the application address

---

## Project Structure

```
STM32-Custom-Bootloader-Development/
├── Core/
│   ├── Inc/
│   │   ├── main.h              # Command definitions, pin mappings, constants
│   │   ├── stm32f4xx_hal_conf.h
│   │   └── stm32f4xx_it.h
│   └── Src/
│       ├── main.c              # Bootloader logic and all 12 command handlers
│       ├── stm32f4xx_hal_msp.c
│       ├── stm32f4xx_it.c
│       └── system_stm32f4xx.c
├── Drivers/
│   ├── CMSIS/                  # ARM CMSIS core headers
│   └── STM32F4xx_HAL_Driver/  # ST HAL drivers
├── Startup/
│   └── startup_stm32f407vgtx.s
├── bootloader_host/
│   ├── bootloader_host/
│   │   ├── cli.py              # CLI entry point (blhost)
│   │   ├── client.py           # Serial client and send_file workflow
│   │   ├── protocol.py         # Frame builder, parser, command codes
│   │   ├── crc.py              # STM32 HAL-compatible CRC32
│   │   ├── gui.py              # Tkinter GUI application
│   │   ├── exceptions.py       # Typed exception hierarchy
│   │   └── __main__.py
│   ├── tests/
│   │   ├── test_crc.py
│   │   └── test_protocol.py
│   ├── pyproject.toml          # Package config, entry points
│   └── README.md               # Host tool documentation
├── STM32F407VGTX_FLASH.ld      # Linker script (32 KB bootloader limit)
├── STM32F407VGTX_RAM.ld
├── CLAUDE.md                   # Development guidelines
└── README.md                   # This file
```

---

## Safety Notes

- The standard host workflow protects bootloader sectors 0-1 from erasure during normal operations
- **Mass erase (`0xFF` sector code) is destructive** — it erases all flash including the bootloader
- Raw/direct commands can bypass host-side protections — use carefully
- The firmware validates address ranges and CRC, but does not fully hard-lock the bootloader region against every possible command
- Always keep ST-LINK available for recovery
- UART receive in firmware is currently blocking with no timeout

---

## Debug Output

Debug messages are enabled by default via the `PRINTF` define in `main.c`. Connect a USB-UART adapter to USART3 (115200 baud) to view:
- Bootloader entry confirmation
- Command processing details
- Application jump addresses (MSP, reset handler)
- Error conditions

---

## Testing

### Host Tool Tests

```bash
cd bootloader_host
pip install -e .
python -m pytest
```

Tests cover:
- CRC32 computation against known test vectors
- Protocol frame building and parsing
- Response parsing edge cases

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request

See [CLAUDE.md](CLAUDE.md) for development guidelines.

---

## Resources

- [STM32F407xx Reference Manual (RM0090)](https://www.st.com/resource/en/reference_manual/rm0090-stm32f405415-stm32f407417-stm32f427437-and-stm32f429439-advanced-armbased-32bit-mcus-stmicroelectronics.pdf)
- [AN3155: USART Protocol Used in STM32 Bootloader](https://www.st.com/resource/en/application_note/cd00264342-usart-protocol-used-in-the-stm32-bootloader-stmicroelectronics.pdf)
- [AN2606: STM32 Microcontroller System Memory Boot Mode](https://www.st.com/resource/en/application_note/cd00167594-stm32-microcontroller-system-memory-boot-mode-application-note-stmicroelectronics.pdf)
- [STM32F4 HAL Driver Documentation](https://www.st.com/resource/en/user_manual/um1725-stm32cube-embedded-software-package-stm32cubef4-stm32cubeh7-stm32cubecl4-stm32cubeg4-and-stm32cubewl-stmicroelectronics.pdf)

---

## License

This project is open source and available under the MIT License.

---

## Author

**Stalin Alexandar** — [@stalin-alexandar](https://github.com/stalin-alexandar)

---

> **Warning**: Incorrectly modifying bootloader flash sectors can brick the device. Always test on a development board first and keep ST-LINK connected for recovery.
