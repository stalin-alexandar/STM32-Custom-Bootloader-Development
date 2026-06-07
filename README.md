# STM32 Custom Bootloader

A custom bootloader for the STM32F407 Discovery board that lets you update your microcontroller's firmware over UART — no special programmer needed after the first flash.

---

## What Is a Bootloader?

A bootloader is a small program that runs when your STM32 powers on. It decides:

- **"Should I wait for a firmware update?"** → If you hold the B1 button during reset
- **"Should I run the user application?"** → If B1 is not pressed, it jumps to your app

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

- **`blhost`** — a command-line tool you run in a terminal
- **`blhost-gui`** — a graphical app with buttons and progress bars

---

## How It Works (Step by Step)

```
You press B1 + Reset
        ↓
Bootloader waits for commands
        ↓
You run: blhost --port COM5 send firmware.bin --erase --verify --go
        ↓
PC sends the firmware to STM32 over UART
        ↓
Bootloader writes it to flash memory
        ↓
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

---

## Memory Layout

Your STM32's flash memory is split into two areas:

```
┌─────────────────────────────────┐
│  Bootloader (32 KB)             │ ← This project
│  Address: 0x08000000            │
├─────────────────────────────────┤
│  Your Application (992 KB)      │ ← Your code goes here
│  Address: 0x08008000            │
└─────────────────────────────────┘
```

The bootloader takes the first 32 KB. Your application starts right after at `0x08008000`.

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
─────────────         ─────────────────────
  TX  ──────────────→  PA3 (USART2 RX)
  RX  ←──────────────  PA2 (USART2 TX)
  GND ──────────────→  GND
```

---

## Getting Started

### Step 1: Flash the Bootloader

1. Clone this repo:
```bash
git clone https://github.com/stalin-alexandar/STM32-Custom-Bootloader-Development.git
```

2. Open in STM32CubeIDE and click **Build** (or press `Ctrl+B`)

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

In your `.ld` file:
```
FLASH (rx) : ORIGIN = 0x08008000, LENGTH = 992K
```

### 2. Set the vector table in your code

At the start of your `main()`:
```c
SCB->VTOR = 0x08008000;
```

That's it! Now your app can be uploaded through the bootloader.

---

## Safety Rules

- **Never erase sectors 0-1** — that's the bootloader itself! Erasing it will brick your board
- **Keep ST-LINK connected** — if something goes wrong, you can always re-flash
- **The Python tool protects you** — it won't let you accidentally erase the bootloader during normal operations

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `blhost` can't find any ports | Check that the UART adapter is plugged in and drivers are installed |
| Bootloader doesn't respond | Make sure you entered bootloader mode (hold B1, press Reset, release B1) |
| "NACK" error | The command was rejected — check your parameters |
| App doesn't start after update | Make sure your app is linked to `0x08008000` and sets `SCB->VTOR` |

---

## Author

**Stalin Alexandar** — [@stalin-alexandar](https://github.com/stalin-alexandar)
