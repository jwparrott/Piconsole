# Pico + Pi Mini Terminal Viewer (Rotary Encoders + 16x2 LCD)

This project turns a Raspberry Pi Pico into a **scrollable window** onto a full terminal running on a Raspberry Pi 3B.  
You get:

- **Pico firmware (`pico_main.py`)**: drives a **16×2 HD44780** LCD, reads two **rotary encoders** (with push buttons), stores a full **80×24** screen buffer sent from the Pi, and lets you scroll **up/down** and **left/right** through the buffer. Button clicks send **Enter** and **Backspace** to the Pi’s shell.
- **Pi bridge (`pi_bridge.py`)**: runs a real shell under a **PTY**, uses **pyte** (VT100 emulator) to keep a full screen buffer in sync, and continuously streams snapshots to the Pico over UART. It also accepts key events back from the Pico.

---

## Hardware Overview

- **Raspberry Pi 3B** (headless OK). Keyboard plugs into the Pi’s USB.
- **Raspberry Pi Pico** (or Pico W) running **MicroPython**.
- **HD44780-compatible 16×2 LCD** (parallel interface).
- **Two rotary encoders** with push buttons.
- Wires, 10k potentiometer for LCD contrast, resistor (~100Ω) for LCD backlight.

### Serial Link

- **Voltage**: Both Pi and Pico use **3.3V UART**, so direct connection is fine.
- **Pins**:
  - Pico **GP0 (TX)** → Pi **GPIO15 (RXD0)**
  - Pico **GP1 (RX)** ← Pi **GPIO14 (TXD0)**
  - **GND ↔ GND**

### LCD Wiring (4-bit mode)

The 16-pin header on the LCD includes power and backlight pins; not all 16 go to GPIO.

| LCD Pin | Function | Connect to |
|---|---|---|
| 1 (VSS) | GND | Pico GND |
| 2 (VDD) | +5V | Pico VSYS/5V (or external 5V) |
| 3 (VO) | Contrast | Wiper of 10k pot (ends to 5V & GND) |
| 4 (RS) | Register Select | Pico **GP6** |
| 5 (RW) | Read/Write | **GND** |
| 6 (E)  | Enable | Pico **GP7** |
| 11 (D4) | Data 4 | Pico **GP10** |
| 12 (D5) | Data 5 | Pico **GP11** |
| 13 (D6) | Data 6 | Pico **GP12** |
| 14 (D7) | Data 7 | Pico **GP13** |
| 15 (A) | Backlight + | +5V via ~100Ω |
| 16 (K) | Backlight − | GND |

> Most HD44780 modules accept **3.3V logic** on RS/E/D4..D7 when powered at 5V. If yours doesn’t, add a level shifter.

### Encoders

- **Vertical scroll**: A=GP14, B=GP15, **button=GP16** (Enter)
- **Horizontal scroll**: A=GP17, B=GP18, **button=GP19** (Backspace)

Internal pull-ups are enabled in the firmware; wire buttons to **GND**.

---

## Software Setup (Pi 3B)

1. Copy `install.sh` to the Pi and run:

   ```bash
   sudo ./install.sh
   ```

   This installs **python3/pip**, **pyserial**, **pyte**, and enables the **UART**.

2. Disable the serial login shell and enable the serial hardware using **raspi-config** (the script prints the steps).
3. Reboot the Pi.
4. Connect the Pico UART pins as shown above.
5. Run the bridge:

   ```bash
   python3 pi_bridge.py --port /dev/serial0 --baud 115200 --rows 24 --cols 80 --mirror
   ```

   - `--mirror` echoes shell output to your current terminal (useful for debugging).

> You can type normally on the **Pi’s keyboard**. The Pico’s **left button** sends **Enter**, and the **right button** sends **Backspace**. The two encoders **scroll the view** on the Pico’s 16×2 LCD (they do not send arrow keys to the shell).

---

## Software Setup (Pico)

1. Flash **MicroPython** UF2 to the Pico (from Raspberry Pi’s official MicroPython for RP2040).
2. Copy `pico_main.py` to the board and rename it **`main.py`** (so it runs on boot).
3. Power the Pico (it shares ground with the Pi via UART).

---

## How It Works

- The Pi launches a real shell under a **PTY** and feeds its output into **pyte**, which tracks a canonical **80×24** screen.
- About **20 times per second**, the Pi serializes that screen into a compact frame and sends it to the Pico:
  ```
  0x02 'S' ROWS COLS [ROWS*COLS bytes] 0x03
  ```
- The Pico stores the full buffer and shows a **16×2 viewport**.  
  - **Left encoder**: scroll **up/down**  
  - **Right encoder**: scroll **left/right**  
  - **Left button**: send **Enter**  
  - **Right button**: send **Backspace**

---

## Customization

- Change terminal size with `--rows/--cols` on the Pi.
- Adjust UART pins/baud in `pico_main.py`.
- If your LCD wiring is different, edit the pin numbers at the top of `pico_main.py`.

---

## Limitations & Alternatives


- **ANSI/VT Compatibility**: `pyte` handles common escape sequences well, but some very exotic apps may render imperfectly.

---

## Files

- `pico_main.py` — MicroPython firmware for the Pico
- `pi_bridge.py` — Pi-side bridge
- `install.sh` — Dependency/setup helper
- `wiring_diagram.pdf` — High-level wiring diagram
- `README.md` — This document

Enjoy!
