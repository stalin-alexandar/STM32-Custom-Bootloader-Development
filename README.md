# 🔓 STM32 Custom Bootloader Development

> A feature-rich custom bootloader for STM32F407VGTx with UART firmware updates, Python host tools, and a Tkinter GUI

[![Platform](https://img.shields.io/badge/Platform-STM32F407-blue.svg)](https://www.st.com/)
[![Protocol](https://img.shields.io/badge/Protocol-UART-orange.svg)](https://www.st.com/resource/en/application_note/cd00264342-usart-protocol-used-in-the-stm32-bootloader-stmicroelectronics.pdf)
[![Language](https://img.shields.io/badge/Language-Python-green.svg)](https://www.python.org/)
[![IDE](https://img.shields.io/badge/IDE-STM32CubeIDE-red.svg)](https://www.st.com/stm32cubeide)

---

## 📋 Overview

A complete custom bootloader system for the STM32F407VGTx (STM32F4-Discovery board). The embedded firmware implements a UART-based command protocol with CRC verification, flash programming, memory access, protection control, and application jump support. Includes a Python host package with both a CLI tool (`blhost`) and a Tkinter GUI for firmware upload, inspection, and debugging.

**Built as a portfolio project to demonstrate embedded bootloader development, protocol design, and full-stack tooling skills.**

### Key Features
- 🔧 **12 Command Handlers** - All bootloader commands fully implemented
- 🛡️ **CRC32 Verification** - Hardware CRC for packet integrity
- 📡 **UART Protocol** - ACK/NACK response framing (0xA5/0x7F)
- 💾 **Flash Programming** - Erase, write, verify with sector protection
- 🖥️ **Python Host Tool** - CLI (`blhost`) and GUI (`blhost-gui`)
- 🔄 **Safe Application Jump** - Full system reset before handoff
- 🛡️ **Bootloader Protection** - Sectors 0-1 protected from erasure

---

## 🔧 Hardware Requirements

### Your Components
- **STM32F407G-DISC1** - Target board (1024KB Flash, 128KB RAM)
- **USB-to-UART Adapter** - CP2102, CH340, or FTDI
- **Jumper Wires** - For UART connections
- **ST-LINK** - Built into Discovery board

### Pin Configuration

| Pin | Function | Connection |
|-----|----------|------------|
| PA0 | B1 Button | Bootloader entry (active HIGH) |
| PA2 | USART2 TX | To USB-UART RX |
| PA3 | USART2 RX | To USB-UART TX |
| PD8 | USART3 TX | Debug output (optional) |
| PD12-PD15 | LEDs | Status indicators |

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────┐
│         PC HOST (Python)                │
│  ┌──────────────────────────┐           │
│  │   blhost CLI / GUI       │           │
│  │   (Firmware Upload)      │           │
│  └────────────┬─────────────┘           │
└───────────────┼──────────────────────────┘
                │ UART (115200 8N1)
                │
┌───────────────┼──────────────────────────┐
│  STM32F407G   │                          │
│         ┌─────▼─────┐                    │
│         │ Bootloader│                    │
│         │  (32KB)   │                    │
│         └─────┬─────┘                    │
│               │ Jump                     │
│         ┌─────▼──────┐                   │
│         │   User     │                   │
│         │Application │                   │
│         │ (992KB)    │                   │
│         └────────────┘                   │
└──────────────────────────────────────────┘
```

---

## 📊 Complete Command Reference

| Code | Command | Description | Request Data | Response |
|------|---------|-------------|--------------|----------|
| `0x51` | `BL_GET_VER` | Get bootloader version | none | 1 byte (`0x30`) |
| `0x52` | `BL_GET_HELP` | List supported commands | none | command bytes |
| `0x53` | `BL_GET_CID` | Get MCU chip ID | none | 2-byte ID |
| `0x54` | `BL_GET_RPD_STATUS` | Get read protection level | none | 1-byte RDP level |
| `0x55` | `BL_GO_TO_ADDR` | Jump to address | 4-byte address | 1 byte status |
| `0x56` | `BL_FLASH_ERASE` | Erase flash sectors | sector + count | 1 byte status |
| `0x57` | `BL_MEM_WRITE` | Write to flash/RAM | addr + len + data | 1 byte status |
| `0x58` | `BL_MEM_READ` | Read memory | addr + len | returned bytes |
| `0x59` | `BL_EN_R_W_PROTECT` | Enable protection | sector mask + mode | 1 byte status |
| `0x5A` | `BL_READ_SECTOR_STATUS` | Read sector protection | none | 2-byte mask |
| `0x5B` | `BL_OTP_READ` | Read OTP memory | addr + len | returned bytes |
| `0x5C` | `BL_DIS_R_RW_PROTECT` | Disable protection | sector mask | 1 byte status |

---

## 📡 Communication Protocol

### Packet Format

```
Request:  [LEN][CMD][DATA...][CRC32_LE]
Response: [0xA5][FOLLOW_LEN][DATA...]   (success)
          [0x7F]                          (failure)
```

- **LEN** = bytes after LEN byte (1 + N + 4)
- **CRC32** = STM32 hardware CRC polynomial 0x04C11DB7
- **ACK** = 0xA5 (command succeeded)
- **NACK** = 0x7F (command rejected)

---

## 💾 Memory Layout

```
0x08000000 - 0x08007FFF   Bootloader (32 KB, Sectors 0-1)
0x08008000 - 0x080FFFFF   User Application (992 KB, Sectors 2-11)
```

### Flash Sector Map

| Sector | Address Range | Size | Usage |
|--------|---------------|------|-------|
| 0 | 0x08000000 - 0x08003FFF | 16 KB | Bootloader (never erase!) |
| 1 | 0x08004000 - 0x08007FFF | 16 KB | Bootloader (never erase!) |
| 2 | 0x08008000 - 0x0800BFFF | 16 KB | Application |
| 3-11 | 0x0800C000 - 0x080FFFFF | varies | Application |

---

## 🚀 Getting Started

### Prerequisites
- STM32CubeIDE (v1.18.0+)
- Python 3.9+
- USB-to-UART adapter
- ST-LINK programmer

### Quick Start
1. **Clone repository**
   ```bash
   git clone https://github.com/stalin-alexandar/STM32-Custom-Bootloader-Development.git
   ```

2. **Build and flash bootloader**
   - Open STM32CubeIDE
   - Import project → Build → Flash via ST-LINK

3. **Enter bootloader mode**
   - Hold B1 button
   - Press and release RESET
   - Release B1

4. **Install Python host tool**
   ```bash
   cd bootloader_host
   pip install -e .
   ```

5. **Test the connection**
   ```bash
   blhost --port COM5 version
   blhost --port COM5 commands
   ```

6. **Update firmware**
   ```bash
   blhost --port COM5 send firmware.bin --erase --verify --go
   ```

---

## 📁 Project Structure

```
Custom Bootloader/
├── Core/
│   ├── Inc/
│   │   └── main.h              # Command definitions
│   └── Src/
│       └── main.c              # Bootloader + 12 command handlers
├── Drivers/                    # STM32 HAL library
├── bootloader_host/
│   ├── bootloader_host/
│   │   ├── cli.py              # CLI entry point
│   │   ├── client.py           # Serial client
│   │   ├── protocol.py         # Frame builder/parser
│   │   ├── crc.py              # STM32 CRC32
│   │   └── gui.py              # Tkinter GUI
│   └── tests/                  # Unit tests
├── STM32F407VGTX_FLASH.ld     # Linker script (32KB limit)
└── README.md
```

---

## 🎓 Skills Demonstrated

### Embedded Systems
- ✅ STM32F407 programming (Cortex-M4)
- ✅ UART communication protocol design
- ✅ Flash memory programming/erasure
- ✅ Hardware CRC verification
- ✅ Interrupt handling and vector tables
- ✅ Application jump with full system reset

### Software Development
- ✅ Python CLI tool development
- ✅ Tkinter GUI application
- ✅ Serial communication (pyserial)
- ✅ Protocol frame building/parsing
- ✅ Unit testing (pytest)
- ✅ Package management (pip/pyproject.toml)

### Protocol Design
- ✅ Custom packet format (LEN+CMD+DATA+CRC)
- ✅ ACK/NACK response handling
- ✅ Error detection and recovery
- ✅ STM32 HAL-compatible CRC algorithm

---

## 🛡️ Safety Notes

- ⚠️ Never erase sectors 0-1 (bootloader region)
- ⚠️ Mass erase is destructive - erases everything
- ⚠️ Keep ST-LINK connected for recovery
- ✅ Host tool protects against accidental erasure
- ✅ Firmware validates addresses and CRC

---

## 💼 For Employers

This project demonstrates:
- **Bootloader Development**: Custom firmware update mechanism
- **Protocol Design**: UART-based command protocol with CRC
- **Full-Stack Tooling**: Python CLI/GUI for embedded device management
- **Safety-Critical Design**: Flash protection, address validation
- **Professional Documentation**: Architecture diagrams, API reference

**Interview Pitch**: "I built a custom bootloader for STM32F407 with 12 command handlers, CRC32 
