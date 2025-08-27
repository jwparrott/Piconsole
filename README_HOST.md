# Pico as USB Host (TinyUSB) + 16x2 LCD + Encoders

This firmware makes the **Raspberry Pi Pico** a **USB HID keyboard host**. The Pico reads keys from a USB keyboard (via OTG adapter), forwards them over **UART** to a **Raspberry Pi 3B** shell, receives **80×24** screen snapshots back from the Pi, and shows a scrollable **16×2** viewport on an HD44780 LCD. Knobs scroll and buttons send **Enter**/**Backspace**.

- **Host stack**: TinyUSB (HID)
- **Transport**: UART0 (115200) to Pi
- **Display**: 16×2 LCD in 4‑bit mode
- **Controls**: Two rotary encoders + push buttons

Build instructions: see `BUILDING.md`.
