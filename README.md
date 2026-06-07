# STM32F4 Custom Bootloader

A feature-rich custom bootloader for STM32F407VGTx microcontroller with UART-based firmware update capabilities.

## 🎯 Overview

This bootloader provides a robust solution for field firmware updates on STM32F4-Discovery boards. It implements a command-based protocol over UART, allowing you to:

- Update application firmware remotely
- Read/write memory and flash
- Query chip information and protection status
- Manage flash sector protection
- Access OTP memory

## 📋 Features

- **UART Protocol**: Command interface at 115200 baud
- **Button Entry**: Physical button to enter bootloader mode
- **Safe Application Jump**: Comprehensive system reset before transferring control
- **Hardware CRC**: Data integrity verification
- **Debug Output**: Separate UART channel for diagnostics
- **Memory Protection**: Bootloader self-protection mechanism
- **Extensible**: 12 command handlers ready for implementation

## 🔧 Hardware Requirements

- **Board**: STM32F4-Discovery (STM32F407G-DISC1)
- **MCU**: STM32F407VGTx
- **Flash**: 1024KB
- **RAM**: 128KB + 64KB CCMRAM
- **UART**: USB-to-UART adapter for command interface
- **Button**: B1 (PA0) for bootloader entry

## 📦 Memory Layout

```
┌─────────────────────────────────────────┐
│ 0x08000000 - 0x08007FFF (32KB)          │
│ Bootloader (Sectors 0-1)                │
│ - Protected from erasure                │
│ - Contains bootloader code              │
├─────────────────────────────────────────┤
│ 0x08008000 - 0x080FFFFF (992KB)         │
│ User Application (Sectors 2-11)         │
│ - Your firmware goes here               │
│ - Updated via bootloader                │
└─────────────────────────────────────────┘
```

## 🚀 Getting Started

### Prerequisites

- STM32CubeIDE 1.18.0 or later
- ARM GCC toolchain
- STM32F4 HAL drivers
- ST-Link programmer

### Building the Bootloader

1. Clone this repository:
```bash
git clone https://github.com/stalin-alexandar/STM32-Custom-Bootloader-Development.git
cd STM32-Custom-Bootloader-Development
```

2. Open the project in STM32CubeIDE

3. Build the project:
   - Right-click project → Build Project
   - Or use keyboard shortcut: `Ctrl+B`

4. Flash to the board:
   - Right-click project → Run As → STM32 C/C++ Application

### Entering Bootloader Mode

1. Press and hold the **B1 button** (blue button on Discovery board)
2. Press and release the **RESET button** (black button)
3. Release the B1 button
4. Bootloader is now active and waiting for commands on USART2

If B1 is not pressed during reset, the bootloader automatically jumps to your application at `0x08008000`.

## 🔌 Hardware Connections

### USART2 (Command Interface)
- **TX**: PA2 → Connect to UART adapter RX
- **RX**: PA3 → Connect to UART adapter TX
- **Baud**: 115200, 8N1
- **Purpose**: Send bootloader commands

### USART3 (Debug Output)
- **TX**: PD8 → Connect to UART adapter RX (optional)
- **Baud**: 115200, 8N1
- **Purpose**: View bootloader debug messages

### GPIO
- **PA0**: B1 button (internal pulldown, active HIGH)
- **PD12-PD15**: Status LEDs

## 📡 Bootloader Protocol

### Packet Format

```
┌──────┬─────────┬──────────┬─────┐
│ Len  │ Command │ Data ... │ CRC │
├──────┼─────────┼──────────┼─────┤
│ 1B   │ 1B      │ 0-255B   │ 4B  │
└──────┴─────────┴──────────┴─────┘
```

### Supported Commands

| Code | Command | Description | Status |
|------|---------|-------------|--------|
| `0x51` | BL_GET_VER | Get bootloader version | Stub |
| `0x52` | BL_GET_HELP | List supported commands | Stub |
| `0x53` | BL_GET_CID | Get chip ID | Stub |
| `0x54` | BL_GET_RPD_STATUS | Read protection status | Stub |
| `0x55` | BL_GO_TO_ADDR | Jump to address | Stub |
| `0x56` | BL_FLASH_ERASE | Erase flash sectors | Stub |
| `0x57` | BL_MEM_WRITE | Write to memory | Stub |
| `0x58` | BL_MEM_READ | Read from memory | Stub |
| `0x59` | BL_EN_R_W_PROJECT | Enable protection | Stub |
| `0x5A` | BL_READ_SECTOR_STATUS | Sector protection status | Stub |
| `0x5B` | BL_OTP_READ | Read OTP memory | Stub |
| `0x5C` | BL_DIS_R_RW_PROJECT | Disable protection | Stub |

**Note**: Command handlers are currently stubs and require implementation.

### Example Command Sequence

```python
# Example: Get bootloader version (Python pseudocode)
cmd_packet = [
    0x02,        # Length (command + CRC)
    0x51,        # BL_GET_VER command
    0xAA, 0xBB, 0xCC, 0xDD  # CRC32 (calculated over length + command)
]
serial.write(cmd_packet)
response = serial.read()
```

## 🛠️ Creating User Applications

Your application must be configured to work with the bootloader:

### 1. Linker Script Modification

Edit your application's linker script to start at `0x08008000`:

```ld
MEMORY
{
  FLASH (rx)  : ORIGIN = 0x08008000, LENGTH = 992K
  RAM (xrw)   : ORIGIN = 0x20000000, LENGTH = 128K
}
```

### 2. Vector Table Relocation

Add this to your application's `main()` or `SystemInit()`:

```c
// Relocate vector table to application base
SCB->VTOR = 0x08008000;
```

### 3. Generate Binary for Upload

After building your application:

```bash
arm-none-eabi-objcopy -O binary Application.elf Application.bin
```

This `.bin` file can be uploaded via the bootloader's `BL_MEM_WRITE` command.

## 🏗️ Project Structure

```
Custom Bootloader/
├── Core/
│   ├── Src/
│   │   ├── main.c              # Bootloader main logic
│   │   ├── stm32f4xx_it.c      # Interrupt handlers
│   │   └── stm32f4xx_hal_msp.c # HAL MSP initialization
│   └── Inc/
│       ├── main.h              # Command definitions
│       ├── stm32f4xx_it.h
│       └── stm32f4xx_hal_conf.h
├── Drivers/
│   ├── STM32F4xx_HAL_Driver/   # HAL drivers
│   └── CMSIS/                  # CMSIS core
├── STM32F407VGTX_FLASH.ld      # Linker script (32KB limit)
├── CLAUDE.md                   # Development guidelines
└── README.md                   # This file
```

## 🔍 Implementation Status

### ✅ Completed
- [x] Bootloader framework and entry logic
- [x] UART initialization (command + debug)
- [x] Button-based mode selection
- [x] Command reception and dispatch
- [x] Safe application jump with full system reset
- [x] CRC peripheral initialization

### ⚠️ In Progress
- [ ] Command handler implementations (all 12 functions)
- [ ] CRC verification logic
- [ ] Flash erase/write operations
- [ ] Response packet protocol

### 📝 Planned
- [ ] Host-side Python upload tool
- [ ] Timeout handling in UART receive
- [ ] Watchdog timer integration
- [ ] Firmware encryption support

## 🚨 Safety Features

### Bootloader Protection
- Sectors 0-1 are protected from erasure
- Address validation prevents bootloader corruption
- CRC checks ensure data integrity

### Application Jump Validation
Before jumping to the user application, the bootloader verifies:
1. **Valid Stack Pointer**: MSP points to valid RAM
2. **Valid Reset Handler**: Reset vector points to flash
3. **Complete System Reset**: All peripherals deinitialized
4. **Vector Table Relocation**: VTOR set to application base

## 📊 Flash Sector Map

| Sector | Address Range | Size | Usage |
|--------|---------------|------|-------|
| 0 | 0x08000000 - 0x08003FFF | 16KB | Bootloader |
| 1 | 0x08004000 - 0x08007FFF | 16KB | Bootloader |
| 2 | 0x08008000 - 0x0800BFFF | 16KB | Application |
| 3 | 0x0800C000 - 0x0800FFFF | 16KB | Application |
| 4 | 0x08010000 - 0x0801FFFF | 64KB | Application |
| 5-11 | 0x08020000 - 0x080FFFFF | 128KB each | Application |

## 🐛 Debugging

### Enable Debug Output

Debug messages are enabled by default via the `PRINTF` define in `main.c`. Messages appear on USART3 at 115200 baud.

### Common Issues

**Application doesn't start:**
- Verify application is linked to `0x08008000`
- Check `SCB->VTOR` is set in application code
- Ensure B1 button is not pressed during reset

**Bootloader hangs:**
- Check UART connections (TX/RX swapped?)
- Verify baud rate is 115200
- Monitor debug output on USART3

**Flash operations fail:**
- Confirm sectors 0-1 are not targeted
- Verify flash unlock/lock sequence
- Check address alignment (word-aligned)

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/command-implementation`)
3. Commit your changes (`git commit -m 'Implement BL_GET_VER command'`)
4. Push to the branch (`git push origin feature/command-implementation`)
5. Open a Pull Request

### Development Guidelines

See [CLAUDE.md](CLAUDE.md) for detailed development guidelines, including:
- Command handler implementation patterns
- Flash operation safety rules
- Testing procedures
- Common pitfalls

## 📚 Resources

- [STM32F407xx Reference Manual (RM0090)](https://www.st.com/resource/en/reference_manual/rm0090-stm32f405415-stm32f407417-stm32f427437-and-stm32f429439-advanced-armbased-32bit-mcus-stmicroelectronics.pdf)
- [AN3155: USART Protocol](https://www.st.com/resource/en/application_note/cd00264342-usart-protocol-used-in-the-stm32-bootloader-stmicroelectronics.pdf)
- [AN2606: STM32 System Memory Boot Mode](https://www.st.com/resource/en/application_note/cd00167594-stm32-microcontroller-system-memory-boot-mode-application-note-stmicroelectronics.pdf)

## 📄 License

This project is open source and available under the MIT License.

## 👤 Author

**Stalin Alexandar**
- GitHub: [@stalin-alexandar](https://github.com/stalin-alexandar)

## 🙏 Acknowledgments

- STMicroelectronics for the HAL drivers and documentation
- STM32 community for bootloader design patterns
- CMSIS team for ARM Cortex-M support

---

**⚠️ Warning**: Incorrectly modifying bootloader code or flash sectors can brick your device. Always test on a development board first. Keep a backup programmer (ST-Link) handy for recovery.
