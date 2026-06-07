# STM32 Custom Bootloader

A custom bootloader for the STM32F407 Discovery board that lets you update your microcontroller's firmware over UART -- no special programmer needed after the first flash.

---

## What Is a Bootloader?

A bootloader is a small program that runs when your STM32 powers on. It decides:

- **"Should I wait for a firmware update?"** -> If you hold the B1 button during reset
- **"Should I run the user application?"** -> If B1 is not pressed, it jumps to your app

Think of it like a manager that sits at the front door. Most of the time it lets your app run. But if you need to update the app, it steps in and handles the process.

---

## What's Inside This Project?

This repo has **two parts**:

### 1. Bootloader Firmware (runs on the STM32)

The code that lives on the microcontroller. It:
- Waits for commands from your PC over a UART serial connection
- Can erase flash memory, write new firmware, read memory, and more
- Protects itself from being accidentally erased
- Jumps to your application when told to

### 2. Python Host Tool (runs on your PC)

A Python package called `blhost` that talks to the bootloader from your computer. It comes in two flavors:

- **`blhost`** -- a command-line tool you run in a terminal
- **`blhost-gui`** -- a graphical app with buttons and progress bars

---

## How It Works (Step by Step)

```
You press B1 + Reset
        |
Bootloader waits for commands
        |
You run: blhost --port COM5 send firmware.bin --erase --verify --go
        |
PC sends the firmware to STM32 over UART
        |
Bootloader writes it to flash memory
        |
Bootloader jumps to your new application
```

---

## What Can the Bootloader Do?

| What | Command | What It Does |
|------|---------|-------------|
| Get version | `blhost version` | Asks the bootloader what version it is |
| Get chip ID | `blhost chip-id` | Reads the MCU identification number |
| List commands | `blhost commands` | Shows what commands the bootloader supports |
| Read memory | `blhost read 0x08008000 64` | Reads 64 bytes from flash starting at address 0x08008000 |
| Erase flash | `blhost erase 2 4` | Erases 4 flash sectors starting from sector 2 |
| Write firmware | `blhost send firmware.bin --erase --verify --go` | Full update: erase, write, verify, and jump |
| Jump to app | `blhost go 0x08008000` | Tells the bootloader to jump to an address |
| Raw command | `blhost raw --cmd 0x51` | Send a raw command for debugging |

---

## Complete Command Reference

| Code | Command | What It Does | What You Send | What You Get Back |
|------|---------|-------------|--------------|------------------|
| 0x51 | BL_GET_VER | Get bootloader version | nothing | 1 byte (0x30) |
| 0x52 | BL_GET_HELP | List supported commands | nothing | command code bytes |
| 0x53 | BL_GET_CID | Get MCU chip ID | nothing | 2-byte chip ID |
| 0x54 | BL_GET_RPD_STATUS | Get read protection level | nothing | 1-byte RDP level |
| 0x55 | BL_GO_TO_ADDR | Jump to address | 4-byte address | 1 byte (valid/invalid) |
| 0x56 | BL_FLASH_ERASE | Erase flash sectors | sector + count | 1 byte erase status |
| 0x57 | BL_MEM_WRITE | Write to flash/RAM | addr + len + data | 1 byte write status |
| 0x58 | BL_MEM_READ | Read memory | addr + len | returned bytes |
| 0x59 | BL_EN_R_W_PROTECT | Enable protection | sector mask + mode | 1 byte status |
| 0x5A | BL_READ_SECTOR_STATUS | Read sector protection | nothing | 2-byte protection mask |
| 0x5B | BL_OTP_READ | Read OTP memory | addr + len | returned bytes |
| 0x5C | BL_DIS_R_RW_PROTECT | Disable protection | sector mask | 1 byte status |

---

## Communication Protocol

### How Commands Are Sent

Every command follows this packet structure:

```
Request:  [LEN][CMD][DATA...][CRC32_LE]
Response: [0xA5][FOLLOW_LEN][DATA...]   (success)
          [0x7F]                          (failure)
```

**What each part means:**
- **LEN** = number of bytes after the LEN byte (1 + N + 4)
- **CMD** = the command code (like 0x51 for version)
- **DATA** = any extra data the command needs
- **CRC32** = a checksum to verify the data wasn't corrupted
- **0xA5** = ACK (acknowledgement -- command worked)
- **0x7F** = NACK (not acknowledged -- command failed)

### CRC Verification

The bootloader uses the STM32's hardware CRC peripheral to verify every command. The CRC is computed over LEN + CMD + DATA using polynomial 0x04C11DB7. If the CRC doesn't match, the command is rejected with a NACK.

---

## Memory Layout

Your STM32's flash memory is split into two areas:

```
0x08000000 - 0x08007FFF   Bootloader (32 KB, Sectors 0-1)
0x08008000 - 0x080FFFFF   User Application (992 KB, Sectors 2-11)
```

### Flash Sector Map

| Sector | Address Range | Size | What It's For |
|--------|---------------|------|---------------|
| 0 | 0x08000000 - 0x08003FFF | 16 KB | Bootloader (never erase!) |
| 1 | 0x08004000 - 0x08007FFF | 16 KB | Bootloader (never erase!) |
| 2 | 0x08008000 - 0x0800BFFF | 16 KB | Your application |
| 3 | 0x0800C000 - 0x0800FFFF | 16 KB | Your application |
| 4 | 0x08010000 - 0x0801FFFF | 64 KB | Your application |
| 5 | 0x08020000 - 0x0803FFFF | 128 KB | Your application |
| 6 | 0x08040000 - 0x0805FFFF | 128 KB | Your application |
| 7 | 0x08060000 - 0x0807FFFF | 128 KB | Your application |
| 8 | 0x08080000 - 0x0809FFFF | 128 KB | Your application |
| 9 | 0x080A0000 - 0x080BFFFF | 128 KB | Your application |
| 10 | 0x080C0000 - 0x080DFFFF | 128 KB | Your application |
| 11 | 0x080E0000 - 0x080FFFFF | 128 KB | Your application |

---

## Hardware You Need

| Item | Why |
|------|-----|
| **STM32F407G-DISC1** board | The target board |
| **USB-to-UART adapter** (CP2102, CH340, or FTDI) | To send commands from your PC |
| **ST-LINK** (built into Discovery board) | To flash the bootloader the first time |
| **Jumper wires** | To connect the UART adapter |

### Wiring

```
UART Adapter          STM32 Discovery Board
-------------         ----------------------
  TX  ------------->  PA3 (USART2 RX)
  RX  <--------------  PA2 (USART2 TX)
  GND ------------->  GND
```

### Pin Configuration

| Pin | Function | Connection |
|-----|----------|------------|
| PA0 | B1 Button | Internal pulldown, active HIGH for bootloader entry |
| PA2 | USART2 TX | Connect to USB-UART RX |
| PA3 | USART2 RX | Connect to USB-UART TX |
| PD8 | USART3 TX | Debug output (optional) |
| PD12-PD15 | LEDs | Status indicators |

---

## Getting Started

### Step 1: Flash the Bootloader

1. Clone this repo:
```bash
git clone https://github.com/stalin-alexandar/STM32-Custom-Bootloader-Development.git
```

2. Open in STM32CubeIDE and click **Build** (or press Ctrl+B)

3. Click **Run** to flash it to your board via ST-LINK

### Step 2: Enter Bootloader Mode

1. **Hold** the blue B1 button
2. **Press and release** the black RESET button
3. **Release** B1
4. The bootloader is now waiting for commands!

### Step 3: Install the Python Tool

```bash
cd bootloader_host
pip install -e .
```

### Step 4: Test It

```bash
# Check if the bootloader responds
blhost --port COM5 version

# See what it can do
blhost --port COM5 commands
```

### Step 5: Update Your Application

```bash
# Full update: erase old app, write new one, verify, and run it
blhost --port COM5 send your_app.bin --erase --verify --go
```

---

## Making Your Own Applications

If you want your app to work with this bootloader, you need to do two things:

### 1. Tell your linker script to start at 0x08008000

In your .ld file:
```
FLASH (rx) : ORIGIN = 0x08008000, LENGTH = 992K
```

### 2. Set the vector table in your code

At the start of your main():
```c
SCB->VTOR = 0x08008000;
```

That's it! Now your app can be uploaded through the bootloader.

---

## What Happens When You Jump to Your App

The bootloader does a thorough cleanup before handing control to your application:

1. Checks that there's a valid app at 0x08008000
2. Turns off all interrupts
3. Stops the SysTick timer
4. Clears all pending interrupts
5. Resets all peripherals
6. Resets the clock back to default
7. Updates the vector table pointer
8. Sets up the stack poin
