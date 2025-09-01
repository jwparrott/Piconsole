# pico_main.py
# MicroPython firmware for Raspberry Pi Pico (RP2040)
# Role: drive a 16x2 HD44780 LCD, read two rotary encoders + push buttons,
# maintain a scrollable viewport of a full terminal buffer sent by a Raspberry Pi over UART,
# and send key events (ENTER/BACKSPACE) to the Pi.
#
# Notes:
# - RP2040 (Pico) USB is *device-only*. USB host keyboards require extra host hardware,
#   so this design moves USB-host duties to the Raspberry Pi 3B.
# - UART protocol (Pi <-> Pico):
#   * Pi -> Pico full-screen snapshot frames:
#       [0x02 'S' ROWS COLS <ROWS*COLS bytes> 0x03]
#     characters are printable ASCII or spaces; ROWS/COLS up to 255 (we use up to 24x80).
#   * Pico -> Pi key events, ASCII lines:
#       b"KEY:ENTER\n" or b"KEY:BACKSPACE\n"
# - The LCD is driven in standard 4-bit mode: RS, E, D4..D7. RW is tied to GND.
# - Rotary encoders: one for vertical scroll, one for horizontal scroll; push buttons generate Enter/Backspace.
#
# Wiring (Pico side, change pins below if needed):
#   UART0:  TX=GP0 -> Pi GPIO15 (RXD0) ,  RX=GP1 <- Pi GPIO14 (TXD0),  GND common
#   LCD: RS=GP6, E=GP7, D4=GP10, D5=GP11, D6=GP12, D7=GP13, RW to GND
#        VSS->GND, VDD->5V, VO->middle of 10k pot (ends to 5V/GND), LED A->5V via ~100Ω, LED K->GND
#   Enc A (vertical): A=GP14, B=GP15, BUTTON=GP16 (to GND, pull-up enabled)
#   Enc B (horizontal): A=GP17, B=GP18, BUTTON=GP19 (to GND, pull-up enabled)
#


from machine import Pin, UART
import utime

# --------------------------- Configuration ---------------------------
# UART
UART_ID = 0
UART_BAUD = 115200
UART_TX_PIN = 0  # GP0
UART_RX_PIN = 1  # GP1

# LCD pins (4-bit mode)
LCD_RS = 6
LCD_E  = 7
LCD_D4 = 10
LCD_D5 = 11
LCD_D6 = 12
LCD_D7 = 13

# Rotary encoders & buttons
ENC_V_A = 14
ENC_V_B = 15
BTN_V   = 16  # Enter

ENC_H_A = 17
ENC_H_B = 18
BTN_H   = 19  # Backspace

LCD_COLS = 16
LCD_ROWS = 2

# Default terminal buffer size (incoming from Pi)
TERM_ROWS = 24
TERM_COLS = 80

# Debounce timings
BTN_DEBOUNCE_MS = 200

# --------------------------- LCD Driver ---------------------------
class LCD:
    def __init__(self, rs, e, d4, d5, d6, d7, cols=16, rows=2):
        self.cols = cols
        self.rows = rows
        self.rs = Pin(rs, Pin.OUT, value=0)
        self.e  = Pin(e,  Pin.OUT, value=0)
        self.d4 = Pin(d4, Pin.OUT, value=0)
        self.d5 = Pin(d5, Pin.OUT, value=0)
        self.d6 = Pin(d6, Pin.OUT, value=0)
        self.d7 = Pin(d7, Pin.OUT, value=0)
        utime.sleep_ms(50)
        self._write4(0x03); utime.sleep_ms(5)
        self._write4(0x03); utime.sleep_us(150)
        self._write4(0x03)
        self._write4(0x02)  # 4-bit
        self.command(0x28)  # 4-bit, 2-line, 5x8 font
        self.command(0x08)  # display off
        self.clear()
        self.command(0x06)  # entry mode
        self.command(0x0C)  # display on, cursor off, blink off

    def _pulse(self):
        self.e.value(1)
        utime.sleep_us(1)
        self.e.value(0)
        utime.sleep_us(100)

    def _write4(self, val):
        self.d4.value((val >> 0) & 1)
        self.d5.value((val >> 1) & 1)
        self.d6.value((val >> 2) & 1)
        self.d7.value((val >> 3) & 1)
        self._pulse()

    def command(self, cmd):
        self.rs.value(0)
        self._write4(cmd >> 4)
        self._write4(cmd & 0x0F)

    def write_char(self, ch):
        self.rs.value(1)
        b = ord(ch)
        self._write4(b >> 4)
        self._write4(b & 0x0F)

    def clear(self):
        self.command(0x01)
        utime.sleep_ms(2)

    def set_cursor(self, col, row):
        row = max(0, min(self.rows-1, row))
        col = max(0, min(self.cols-1, col))
        addr = col + (0x40 * row)
        self.command(0x80 | addr)

    def write_str(self, s):
        for ch in s[:self.cols]:
            self.write_char(ch)

# --------------------------- Rotary Encoder ---------------------------
class Encoder:
    def __init__(self, pin_a, pin_b, on_step):
        self.pin_a = Pin(pin_a, Pin.IN, Pin.PULL_UP)
        self.pin_b = Pin(pin_b, Pin.IN, Pin.PULL_UP)
        self.on_step = on_step
        self.last = (self.pin_a.value() << 1) | self.pin_b.value()
        self.pin_a.irq(self._handler, Pin.IRQ_FALLING | Pin.IRQ_RISING)
        self.pin_b.irq(self._handler, Pin.IRQ_FALLING | Pin.IRQ_RISING)

    def _handler(self, pin):
        a = self.pin_a.value()
        b = self.pin_b.value()
        state = (a << 1) | b
        if state == self.last:
            return
        # Gray code decoding (very simple, may count twice per detent)
        if (self.last == 0b00 and state == 0b01) or \
           (self.last == 0b01 and state == 0b11) or \
           (self.last == 0b11 and state == 0b10) or \
           (self.last == 0b10 and state == 0b00):
            direction = +1
        else:
            direction = -1
        self.last = state
        try:
            self.on_step(direction)
        except Exception as e:
            pass

# --------------------------- Buttons ---------------------------
class Button:
    def __init__(self, pin, on_click):
        self.pin = Pin(pin, Pin.IN, Pin.PULL_UP)
        self.on_click = on_click
        self.last_time = 0
        self.pin.irq(self._handler, Pin.IRQ_FALLING)

    def _handler(self, pin):
        now = utime.ticks_ms()
        if utime.ticks_diff(now, self.last_time) < BTN_DEBOUNCE_MS:
            return
        self.last_time = now
        utime.sleep_ms(10)
        if self.pin.value() == 0:
            try:
                self.on_click()
            except Exception as e:
                pass

# --------------------------- Terminal Buffer + Viewport ---------------------------
class TerminalView:
    def __init__(self, rows, cols):
        self.rows = rows
        self.cols = cols
        self.buffer = [[' ']*cols for _ in range(rows)]
        self.v_off = 0
        self.h_off = 0

    def apply_snapshot(self, rows, cols, data_bytes):
        # Resize if needed
        if rows != self.rows or cols != self.cols:
            self.rows = rows
            self.cols = cols
            self.buffer = [[' ']*cols for _ in range(rows)]
            self.v_off = 0
            self.h_off = 0
        # Fill
        idx = 0
        for r in range(rows):
            for c in range(cols):
                ch = chr(data_bytes[idx]) if 32 <= data_bytes[idx] <= 126 else ' '
                self.buffer[r][c] = ch
                idx += 1

    def scroll_v(self, delta):
        self.v_off = max(0, min(self.rows-1, self.v_off + delta))
    def scroll_h(self, delta):
        self.h_off = max(0, min(self.cols-1, self.h_off + delta))

    def window_lines(self, width=16, height=2):
        # Return two lines of width chars at (v_off, h_off)
        lines = []
        for r in range(height):
            rr = min(self.rows-1, self.v_off + r)
            start = self.h_off
            end = min(self.cols, start + width)
            row = self.buffer[rr][start:end]
            s = ''.join(row)
            # Pad to width
            if len(s) < width:
                s = s + ' '*(width - len(s))
            lines.append(s)
        return lines

# --------------------------- Main ---------------------------
uart = UART(UART_ID, UART_BAUD, tx=Pin(UART_TX_PIN), rx=Pin(UART_RX_PIN))

lcd = LCD(LCD_RS, LCD_E, LCD_D4, LCD_D5, LCD_D6, LCD_D7, LCD_COLS, LCD_ROWS)
term = TerminalView(TERM_ROWS, TERM_COLS)

def render():
    lines = term.window_lines(LCD_COLS, LCD_ROWS)
    lcd.set_cursor(0,0); lcd.write_str(lines[0])
    lcd.set_cursor(0,1); lcd.write_str(lines[1])

def on_v_step(direction):
    term.scroll_v(-direction)  # invert if needed
    render()

def on_h_step(direction):
    term.scroll_h(+direction)
    render()

def on_btn_v():
    # Send Enter
    uart.write(b"KEY:ENTER\n")

def on_btn_h():
    # Send Backspace
    uart.write(b"KEY:BACKSPACE\n")

enc_v = Encoder(ENC_V_A, ENC_V_B, on_v_step)
enc_h = Encoder(ENC_H_A, ENC_H_B, on_h_step)
btn_v = Button(BTN_V, on_btn_v)
btn_h = Button(BTN_H, on_btn_h)

# Initial splash
lcd.clear()
lcd.set_cursor(0,0); lcd.write_str("Pico Term Viewer")
lcd.set_cursor(0,1); lcd.write_str("Waiting for Pi...")

# Frame receiver
def read_frame():
    # Look for STX
    if uart.any() == 0:
        return False
    b = uart.read(1)
    if not b or b[0] != 0x02:
        return False
    # Next byte must be 'S'
    cmd = uart.read(1)
    if not cmd or cmd != b'S':
        return False
    hdr = uart.read(2)
    if not hdr or len(hdr) < 2:
        return False
    rows = hdr[0]
    cols = hdr[1]
    total = rows * cols
    data = bytearray()
    while len(data) < total:
        chunk = uart.read(total - len(data))
        if chunk:
            data.extend(chunk)
    etx = uart.read(1)
    if not etx or etx[0] != 0x03:
        return False
    # Apply
    term.apply_snapshot(rows, cols, data)
    return True

last_render = utime.ticks_ms()
while True:
    if read_frame():
        render()
        last_render = utime.ticks_ms()
    # minimal idle
    utime.sleep_ms(2)
