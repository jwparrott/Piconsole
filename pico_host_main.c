// pico_host_main.c
// RP2040 (Pico) firmware using TinyUSB (HOST) to read a USB HID keyboard,
// while also driving a 16x2 HD44780 LCD and two rotary encoders, and exchanging
// terminal frames with a Raspberry Pi over UART.
//
//  - USB Host: TinyUSB (HID keyboard). Sends ASCII and special keys to Pi over UART.
//  - UART protocol to Pi (same as previous Python design for frames):
//      Pi -> Pico: [0x02 'S' ROWS COLS <ROWS*COLS bytes> 0x03]
//    where bytes are printable ASCII (space for others).
//  - Pico -> Pi: lines of ASCII ending with '\n':
//      "KEY:ENTER\n", "KEY:BACKSPACE\n", or "TXT:<text>\n"
//
// Build with pico-sdk + tinyusb (host enabled).
//
// Pins (change as needed):
//   UART0: TX=GP0 (to Pi RXD0/GPIO15), RX=GP1 (from Pi TXD0/GPIO14)
//   LCD (4-bit): RS=GP6, E=GP7, D4=GP10, D5=GP11, D6=GP12, D7=GP13, RW->GND
//   Enc V: A=GP14, B=GP15, BTN=GP16 (Enter)
//   Enc H: A=GP17, B=GP18, BTN=GP19 (Backspace)
//
// USB Host wiring on Pico board:
//   - Use a Micro-USB OTG adapter/cable to plug a USB keyboard into the Pico's USB connector
//     AND inject 5V onto the Pico's VBUS pin (pin 40) from a clean, current-limited 5V supply.
//   - Do NOT power the Pico from the same USB PC port at the same time. See README_HOST.md.
//


#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/uart.h"
#include "hardware/gpio.h"
#include "pico/binary_info.h"

// TinyUSB Host
#include "bsp/board.h"
#include "tusb.h"

// -------------------- Config --------------------
#define UART_ID uart0
#define UART_TX_PIN 0
#define UART_RX_PIN 1
#define UART_BAUD   115200

#define LCD_RS 6
#define LCD_E  7
#define LCD_D4 10
#define LCD_D5 11
#define LCD_D6 12
#define LCD_D7 13

#define ENC_V_A 14
#define ENC_V_B 15
#define BTN_V   16  // Enter

#define ENC_H_A 17
#define ENC_H_B 18
#define BTN_H   19  // Backspace

#define LCD_COLS 16
#define LCD_ROWS 2

#define TERM_ROWS 24
#define TERM_COLS 80

// -------------------- LCD --------------------
static inline void lcd_pulse() {
  gpio_put(LCD_E, 1); sleep_us(1);
  gpio_put(LCD_E, 0); sleep_us(100);
}

static void lcd_write4(uint8_t val) {
  gpio_put(LCD_D4, val & 1);
  gpio_put(LCD_D5, (val >> 1) & 1);
  gpio_put(LCD_D6, (val >> 2) & 1);
  gpio_put(LCD_D7, (val >> 3) & 1);
  lcd_pulse();
}

static void lcd_cmd(uint8_t cmd) {
  gpio_put(LCD_RS, 0);
  lcd_write4(cmd >> 4);
  lcd_write4(cmd & 0x0F);
}

static void lcd_data(uint8_t data) {
  gpio_put(LCD_RS, 1);
  lcd_write4(data >> 4);
  lcd_write4(data & 0x0F);
}

static void lcd_init() {
  gpio_init(LCD_RS); gpio_set_dir(LCD_RS, GPIO_OUT); gpio_put(LCD_RS, 0);
  gpio_init(LCD_E);  gpio_set_dir(LCD_E,  GPIO_OUT); gpio_put(LCD_E,  0);
  gpio_init(LCD_D4); gpio_set_dir(LCD_D4, GPIO_OUT);
  gpio_init(LCD_D5); gpio_set_dir(LCD_D5, GPIO_OUT);
  gpio_init(LCD_D6); gpio_set_dir(LCD_D6, GPIO_OUT);
  gpio_init(LCD_D7); gpio_set_dir(LCD_D7, GPIO_OUT);
  sleep_ms(50);
  lcd_write4(0x03); sleep_ms(5);
  lcd_write4(0x03); sleep_us(150);
  lcd_write4(0x03);
  lcd_write4(0x02);
  lcd_cmd(0x28); // 4-bit, 2-line
  lcd_cmd(0x08); // display off
  lcd_cmd(0x01); sleep_ms(2);
  lcd_cmd(0x06); // entry mode
  lcd_cmd(0x0C); // display on
}

static void lcd_clear() { lcd_cmd(0x01); sleep_ms(2); }

static void lcd_set_cursor(int col, int row) {
  if (row < 0) row = 0; if (row > 1) row = 1;
  if (col < 0) col = 0; if (col > 15) col = 15;
  uint8_t addr = col + (row ? 0x40 : 0x00);
  lcd_cmd(0x80 | addr);
}

static void lcd_printn(const char* s, int n) {
  for (int i=0; i<n; ++i) lcd_data((uint8_t)s[i]);
}

// -------------------- Terminal Buffer --------------------
static char term_buf[TERM_ROWS][TERM_COLS];
static int v_off = 0, h_off = 0;

static void term_reset() {
  for (int r=0; r<TERM_ROWS; ++r) for (int c=0; c<TERM_COLS; ++c) term_buf[r][c] = ' ';
  v_off = h_off = 0;
}

static void term_apply_snapshot(uint8_t rows, uint8_t cols, const uint8_t* data) {
  int R = rows, C = cols;
  if (R > TERM_ROWS) R = TERM_ROWS;
  if (C > TERM_COLS) C = TERM_COLS;
  const uint8_t* p = data;
  for (int r=0; r<R; ++r) {
    for (int c=0; c<C; ++c) {
      uint8_t b = *p++;
      term_buf[r][c] = (b >= 32 && b <= 126) ? (char)b : ' ';
    }
    p += (cols - C);
  }
  if (v_off > R-1) v_off = R-1;
  if (h_off > C-1) h_off = C-1;
}

static void render() {
  char line[17];
  for (int row=0; row<2; ++row) {
    int rr = v_off + row; if (rr >= TERM_ROWS) rr = TERM_ROWS-1;
    for (int c=0; c<16; ++c) {
      int cc = h_off + c; if (cc >= TERM_COLS) cc = TERM_COLS-1;
      line[c] = term_buf[rr][cc];
    }
    line[16]='\0';
    lcd_set_cursor(0,row); lcd_printn(line,16);
  }
}

// -------------------- Encoders & Buttons --------------------
typedef struct {
  uint8_t a, b;
  uint8_t last;
  void (*on_step)(int dir);
} encoder_t;

static void enc_step_v(int dir){ v_off -= dir; if (v_off < 0) v_off = 0; if (v_off > TERM_ROWS-1) v_off = TERM_ROWS-1; render(); }
static void enc_step_h(int dir){ h_off += dir; if (h_off < 0) h_off = 0; if (h_off > TERM_COLS-1) h_off = TERM_COLS-1; render(); }

static encoder_t enc_v = {ENC_V_A, ENC_V_B, 0, enc_step_v};
static encoder_t enc_h = {ENC_H_A, ENC_H_B, 0, enc_step_h};

static void enc_init(encoder_t* e) {
  gpio_init(e->a); gpio_set_dir(e->a, GPIO_IN); gpio_pull_up(e->a);
  gpio_init(e->b); gpio_set_dir(e->b, GPIO_IN); gpio_pull_up(e->b);
  e->last = (gpio_get(e->a)<<1) | gpio_get(e->b);
}

static void enc_poll(encoder_t* e) {
  uint8_t a = gpio_get(e->a);
  uint8_t b = gpio_get(e->b);
  uint8_t state = (a<<1) | b;
  if (state != e->last) {
    int dir = -1;
    if ((e->last==0b00 && state==0b01) || (e->last==0b01 && state==0b11) ||
        (e->last==0b11 && state==0b10) || (e->last==0b10 && state==0b00)) dir = +1;
    e->last = state;
    e->on_step(dir);
  }
}

static absolute_time_t btn_v_last, btn_h_last;

static void send_line(const char* s) {
  uart_puts(UART_ID, s);
  uart_putc_raw(UART_ID, '\n');
}

static void btn_init(uint pin) {
  gpio_init(pin); gpio_set_dir(pin, GPIO_IN); gpio_pull_up(pin);
}

static void btn_poll(uint pin, absolute_time_t* last, const char* line) {
  if (!gpio_get(pin)) {
    if (absolute_time_diff_us(*last, get_absolute_time()) > 200*1000) {
      *last = get_absolute_time();
      send_line(line);
    }
  }
}

// -------------------- UART Frame Receiver --------------------
static bool read_exact(uint8_t* dst, size_t n) {
  size_t got = 0; uint64_t start = time_us_64();
  while (got < n) {
    if (uart_is_readable(UART_ID)) {
      dst[got++] = uart_getc(UART_ID);
    } else {
      tight_loop_contents();
      if (time_us_64() - start > 200000) return false; // 200ms timeout
    }
  }
  return true;
}

static bool try_read_frame() {
  if (!uart_is_readable(UART_ID)) return false;
  uint8_t b = uart_getc(UART_ID);
  if (b != 0x02) return false;
  if (!uart_is_readable(UART_ID)) return false;
  if (uart_getc(UART_ID) != 'S') return false;
  uint8_t hdr[2];
  if (!read_exact(hdr,2)) return false;
  uint8_t rows = hdr[0], cols = hdr[1];
  size_t total = (size_t)rows * (size_t)cols;
  static uint8_t buf[TERM_ROWS*TERM_COLS];
  if (total > sizeof(buf)) total = sizeof(buf);
  if (!read_exact(buf, total)) return false;
  uint8_t etx;
  if (!read_exact(&etx,1)) return false;
  if (etx != 0x03) return false;
  term_apply_snapshot(rows, cols, buf);
  render();
  return true;
}

// -------------------- TinyUSB HID Host --------------------

// Helpers for shift detection
#define KEYBOARD_MODIFIER_LEFTSHIFT   0x02
#define KEYBOARD_MODIFIER_RIGHTSHIFT  0x20

void tuh_hid_mount_cb (uint8_t dev_addr, uint8_t instance, uint8_t const* desc_report, uint16_t desc_len) {
  (void)desc_report; (void)desc_len;
  tuh_hid_receive_report(dev_addr, instance);
}

void tuh_hid_umount_cb(uint8_t dev_addr, uint8_t instance) {
  (void)dev_addr; (void)instance;
}

void tuh_hid_report_received_cb(uint8_t dev_addr, uint8_t instance, uint8_t const* report, uint16_t len) {
  (void)dev_addr; (void)instance;
  if (len >= 8) {
    uint8_t mods = report[0];
    for (int i=2; i<8; ++i) {
      uint8_t kc = report[i];
      if (!kc) continue;
      if (kc == 0x28) { send_line("KEY:ENTER"); }
      else if (kc == 0x2a) { send_line("KEY:BACKSPACE"); }
      else {
        char out[32]; int oi=0;
        if (kc >= 0x04 && kc <= 0x1d) {
          char base = (mods & (KEYBOARD_MODIFIER_LEFTSHIFT | KEYBOARD_MODIFIER_RIGHTSHIFT)) ? 'A' : 'a';
          out[oi++] = base + (kc - 0x04);
        } else if (kc >= 0x1e && kc <= 0x27) {
          const char* noshift = "1234567890";
          const char* shift   = "!@#$%^&*()";
          int idx = kc - 0x1e;
          if (idx>=0 && idx<10) out[oi++] = (mods ? shift[idx] : noshift[idx]);
        } else if (kc == 0x2c) out[oi++] = ' ';
        else if (kc == 0x2d) out[oi++] = (mods ? '_' : '-');
        else if (kc == 0x2e) out[oi++] = (mods ? '+' : '=');
        else if (kc == 0x2f) out[oi++] = (mods ? '{' : '[');
        else if (kc == 0x30) out[oi++] = (mods ? '}' : ']');
        else if (kc == 0x31) out[oi++] = (mods ? '|' : '\\');
        else if (kc == 0x33) out[oi++] = (mods ? ':' : ';');
        else if (kc == 0x34) out[oi++] = (mods ? '\"' : '\'');
        else if (kc == 0x36) out[oi++] = (mods ? '>' : '.');
        else if (kc == 0x37) out[oi++] = (mods ? '?' : '/');
        else if (kc == 0x35) out[oi++] = (mods ? '~' : '`');

        if (oi) {
          char line[64];
          memcpy(line, "TXT:", 4);
          memcpy(line+4, out, oi);
          line[4+oi] = '\0';
          send_line(line);
        }
      }
    }
  }
  tuh_hid_receive_report(dev_addr, instance);
}

int main() {
  stdio_init_all();

  // UART
  uart_init(UART_ID, UART_BAUD);
  gpio_set_function(UART_TX_PIN, GPIO_FUNC_UART);
  gpio_set_function(UART_RX_PIN, GPIO_FUNC_UART);

  // LCD / encoders / buttons
  lcd_init(); lcd_clear();
  lcd_set_cursor(0,0); const char* a="Pico Host Ready"; lcd_printn(a,16);
  lcd_set_cursor(0,1); const char* b="Plug keyboard   "; lcd_printn(b,16);

  // Encoders
  encoder_t *e1=&enc_v, *e2=&enc_h;
  enc_init(e1); enc_init(e2);
  btn_init(BTN_V); btn_init(BTN_H);
  term_reset();

  // TinyUSB Host
  board_init();
  tusb_init();

  absolute_time_t last_render = get_absolute_time();
  while (true) {
    tuh_task();
    (void)try_read_frame();
    enc_poll(e1); enc_poll(e2);
    btn_poll(BTN_V, &btn_v_last, "KEY:ENTER");
    btn_poll(BTN_H, &btn_h_last, "KEY:BACKSPACE");
    if (absolute_time_diff_us(last_render, get_absolute_time()) > 200*1000) {
      render(); last_render = get_absolute_time();
    }
    tight_loop_contents();
  }
  return 0;
}
