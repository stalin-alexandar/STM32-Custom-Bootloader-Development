# STM32F4 Custom Bootloader Project

## Project Overview

This is a custom bootloader implementation for the STM32F407VGTx microcontroller (STM32F4-Discovery board). The bootloader provides UART-based firmware update capabilities and application management.

## Hardware Configuration

- **MCU**: STM32F407VGTx
- **Board**: STM32F4-Discovery (STM32F407G-DISC1)
- **Flash**: 1024KB total (bootloader uses first 32KB, application starts at 0x08008000)
- **RAM**: 128KB
- **CCMRAM**: 64KB
- **Clock**: HSI-based PLL configuration, 25MHz system clock

## Memory Layout

```
Flash Memory Map:
├── 0x08000000 - 0x08007FFF (32KB)  : Bootloader (Sector 0-1)
└── 0x08008000 - 0x080FFFFF (992KB) : User Application (Sector 2+)
```

**Critical**: The bootloader occupies the first 32KB of flash. User applications must be linked to start at `0x08008000` (SECTOR2_FLASH_STORAGE).

## Peripheral Configuration

### UARTs
- **USART2 (C_UART)**: Command interface for bootloader protocol (115200 baud, 8N1)
- **USART3 (D_UART)**: Debug output for bootloader messages (115200 baud, 8N1)

### Other Peripherals
- **CRC**: Hardware CRC for data integrity verification
- **GPIO**: 
  - B1 button (PA0): Bootloader entry trigger (active HIGH with pulldown)
  - LEDs on GPIOD (LD3-LD6): Status indicators

## Bootloader Operation

### Entry Conditions
The bootloader checks the B1 button state at startup:
- **Button PRESSED (HIGH)**: Enter bootloader mode, wait for UART commands
- **Button NOT PRESSED (LOW)**: Jump to user application at 0x08008000

### Bootloader Commands

The bootloader implements a command protocol over USART2. All commands follow this packet structure:
```
[Length][Command][Data...][CRC]
```

#### Supported Commands (defined in main.h)

| Command Code | Name | Description | Status |
|--------------|------|-------------|--------|
| 0x51 | BL_GET_VER | Get bootloader version | Stub |
| 0x52 | BL_GET_HELP | Get list of supported commands | Stub |
| 0x53 | BL_GET_CID | Get chip identification | Stub |
| 0x54 | BL_GET_RPD_STATUS | Get read protection status | Stub |
| 0x55 | BL_GO_TO_ADDR | Jump to specified address | Stub |
| 0x56 | BL_FLASH_ERASE | Erase flash sectors | Stub |
| 0x57 | BL_MEM_WRITE | Write to memory | Stub |
| 0x58 | BL_MEM_READ | Read from memory | Stub |
| 0x59 | BL_EN_R_W_PROJECT | Enable read/write protection | Stub |
| 0x5A | BL_READ_SECTOR_STATUS | Get sector protection status | Stub |
| 0x5B | BL_OTP_READ | Read OTP memory | Stub |
| 0x5C | BL_DIS_R_RW_PROJECT | Disable read/write protection | Stub |

**Note**: All command handlers are currently empty stubs and need implementation.

### Application Jump Sequence

The `bootloader_jump_to_user_app()` function performs a comprehensive system reset before jumping to the user application:

1. **Validation**: Checks MSP and reset handler validity
2. **Interrupt Disable**: Disables all interrupts globally
3. **SysTick Stop**: Stops SysTick timer completely
4. **NVIC Clear**: Clears all pending interrupts and disables all interrupt sources
5. **HAL Deinit**: Deinitializes all HAL peripherals
6. **Clock Reset**: Manually resets RCC to HSI default state (16MHz)
7. **Flash Latency**: Resets flash wait states to 0
8. **VTOR Update**: Sets vector table offset to application address
9. **EXTI Clear**: Disables and clears button interrupt
10. **Stack Pointer**: Sets MSP to application's initial stack pointer
11. **Jump**: Transfers control to application reset handler

**Why this is important**: The comprehensive reset ensures the application starts in a clean state, preventing issues from bootloader peripheral configurations interfering with the application.

## Code Structure

### Main Files
- `Core/Src/main.c`: Bootloader main logic and command handlers
- `Core/Inc/main.h`: Command definitions and pin mappings
- `STM32F407VGTX_FLASH.ld`: Linker script (bootloader limited to 32KB)

### Key Functions
- `bootloader_uart_read_data()`: Command reception loop
- `bootloader_jump_to_user_app()`: Application transition with full system reset
- `printmsg()`: Debug output via USART3 (conditional on PRINTF define)
- `bl_*()`: Command handler stubs (12 functions, all empty)

## Development Guidelines

### When Implementing Command Handlers

1. **Always validate inputs**: Check packet length, CRC, address ranges
2. **Use CRC peripheral**: Hardware CRC is initialized and available
3. **Send responses via C_UART**: Command responses go to USART2
4. **Log via D_UART**: Debug messages go to USART3 using `printmsg()`
5. **Flash operations**: Use HAL flash functions, unlock before write/erase, lock after
6. **Sector boundaries**: Respect the bootloader/application boundary at 0x08008000
7. **Error handling**: Return appropriate error codes for invalid operations

### Flash Sector Map (STM32F407VG)
```
Sector 0:  0x08000000 - 0x08003FFF (16KB)  [Bootloader]
Sector 1:  0x08004000 - 0x08007FFF (16KB)  [Bootloader]
Sector 2:  0x08008000 - 0x0800BFFF (16KB)  [Application Start]
Sector 3:  0x0800C000 - 0x0800FFFF (16KB)
Sector 4:  0x08010000 - 0x0801FFFF (64KB)
Sector 5:  0x08020000 - 0x0803FFFF (128KB)
Sector 6:  0x08040000 - 0x0805FFFF (128KB)
Sector 7:  0x08060000 - 0x0807FFFF (128KB)
Sector 8:  0x08080000 - 0x0809FFFF (128KB)
Sector 9:  0x080A0000 - 0x080BFFFF (128KB)
Sector 10: 0x080C0000 - 0x080DFFFF (128KB)
Sector 11: 0x080E0000 - 0x080FFFFF (128KB)
```

**Never erase or write to Sectors 0-1** as this would brick the bootloader.

### Testing User Applications

User applications must:
1. Be linked to start at `0x08008000`
2. Have a valid vector table at that address
3. Set the vector table offset: `SCB->VTOR = 0x08008000;` in startup code
4. Not rely on bootloader peripheral configurations (everything is reset)

### Common Pitfalls

- **Don't assume peripheral state**: The bootloader resets everything before jumping
- **Validate before jumping**: The bootloader checks for valid MSP and reset handler
- **UART conflicts**: Application can reconfigure UARTs freely after jump
- **Stack pointer**: Application's initial SP must be valid RAM address
- **Interrupt vectors**: Application must have its own complete vector table

## Build Configuration

- **IDE**: STM32CubeIDE 1.18.0
- **Toolchain**: ARM GCC
- **HAL Version**: STM32F4 HAL Driver
- **CMSIS**: ARM CMSIS v5.x
- **Linker Script**: Modified to limit bootloader to 32KB flash

## Current Implementation Status

### ✅ Implemented
- Basic bootloader framework
- UART initialization (command + debug)
- Button-based bootloader entry
- Command reception and dispatch
- Comprehensive application jump with full system reset
- Application validation before jump

### ⚠️ Partially Implemented
- Command handlers (all are empty stubs)
- CRC verification (peripheral initialized but not used)

### ❌ Not Implemented
- All 12 command handler implementations
- Flash erase/write operations
- Memory read/write operations
- Protection status queries
- OTP operations
- Error response protocol
- Timeout handling in UART reception

## Next Steps for Implementation

1. **Implement BL_GET_VER and BL_GET_HELP**: Start with simple read-only commands
2. **Add CRC verification**: Validate incoming command packets
3. **Implement BL_MEM_READ**: Safe read-only operation for testing
4. **Implement BL_FLASH_ERASE**: Critical for firmware updates (protect sectors 0-1)
5. **Implement BL_MEM_WRITE**: Flash programming capability
6. **Add response protocol**: Define ACK/NACK format
7. **Implement remaining commands**: Protection status, OTP, etc.
8. **Add timeout handling**: Prevent infinite blocking in UART receive
9. **Create host-side tool**: Python/C tool to send commands and upload firmware

## Safety Considerations

- **Bootloader Protection**: Never allow erasing/writing sectors 0-1
- **Validation**: Always validate addresses before flash operations
- **CRC Checks**: Verify all incoming data integrity
- **Timeout**: Add timeouts to prevent hanging in bootloader mode
- **Fallback**: Consider watchdog timer for recovery from failed updates
- **Read Protection**: Be careful with RDP level changes (can lock the chip)

## Debug Output

Enable debug messages by keeping the `PRINTF` define. Messages appear on USART3:
- Bootloader entry confirmation
- Application jump status
- MSP and reset handler addresses
- Error conditions

## References

- STM32F407xx Reference Manual (RM0090)
- STM32F4 HAL Driver Documentation
- AN3155: USART protocol used in STM32 bootloader
- AN2606: STM32 microcontroller system memory boot mode
