# pico_main.py
# (MicroPython) LCD + Encoders + UART snapshot viewer; buttons send Enter/Backspace.
# Designed to work with pi_bridge.py on the Raspberry Pi 3B.
from machine import Pin, UART
import utime

UART_ID=0; UART_BAUD=115200; UART_TX_PIN=0; UART_RX_PIN=1
LCD_RS=6; LCD_E=7; LCD_D4=10; LCD_D5=11; LCD_D6=12; LCD_D7=13
ENC_V_A=14; ENC_V_B=15; BTN_V=16
ENC_H_A=17; ENC_H_B=18; BTN_H=19
LCD_COLS=16; LCD_ROWS=2; TERM_ROWS=24; TERM_COLS=80
BTN_DEBOUNCE_MS=200

class LCD:
    def __init__(self, rs,e,d4,d5,d6,d7,cols=16,rows=2):
        self.cols=cols; self.rows=rows
        self.rs=Pin(rs,Pin.OUT,value=0); self.e=Pin(e,Pin.OUT,value=0)
        self.d4=Pin(d4,Pin.OUT,value=0); self.d5=Pin(d5,Pin.OUT,value=0)
        self.d6=Pin(d6,Pin.OUT,value=0); self.d7=Pin(d7,Pin.OUT,value=0)
        utime.sleep_ms(50)
        self._w4(0x03); utime.sleep_ms(5); self._w4(0x03); utime.sleep_us(150)
        self._w4(0x03); self._w4(0x02)
        self.cmd(0x28); self.cmd(0x08); self.clr(); self.cmd(0x06); self.cmd(0x0C)
    def _pulse(self): self.e.value(1); utime.sleep_us(1); self.e.value(0); utime.sleep_us(100)
    def _w4(self,val):
        self.d4.value(val&1); self.d5.value((val>>1)&1); self.d6.value((val>>2)&1); self.d7.value((val>>3)&1); self._pulse()
    def cmd(self,c): self.rs.value(0); self._w4(c>>4); self._w4(c&0x0F)
    def put(self,ch): self.rs.value(1); b=ord(ch); self._w4(b>>4); self._w4(b&0x0F)
    def clr(self): self.cmd(0x01); utime.sleep_ms(2)
    def cursor(self,c,r):
        if r<0:r=0
        if r>self.rows-1:r=self.rows-1
        if c<0:c=0
        if c>self.cols-1:c=self.cols-1
        self.cmd(0x80 | (c + (0x40 if r else 0)))
    def write(self,s):
        for ch in s[:self.cols]: self.put(ch)

class Encoder:
    def __init__(self, a,b,cb):
        self.a=Pin(a,Pin.IN,Pin.PULL_UP); self.b=Pin(b,Pin.IN,Pin.PULL_UP)
        self.cb=cb; self.last=(self.a.value()<<1)|self.b.value()
        self.a.irq(self._h,Pin.IRQ_FALLING|Pin.IRQ_RISING)
        self.b.irq(self._h,Pin.IRQ_FALLING|Pin.IRQ_RISING)
    def _h(self,p):
        a=self.a.value(); b=self.b.value(); s=(a<<1)|b
        if s==self.last: return
        if (self.last, s) in [(0,1),(1,3),(3,2),(2,0)]: d=+1
        else: d=-1
        self.last=s
        try: self.cb(d)
        except: pass

class Button:
    def __init__(self,pin,cb):
        self.p=Pin(pin,Pin.IN,Pin.PULL_UP); self.cb=cb; self.last=0
        self.p.irq(self._h,Pin.IRQ_FALLING)
    def _h(self,p):
        now=utime.ticks_ms()
        if utime.ticks_diff(now,self.last)<BTN_DEBOUNCE_MS: return
        self.last=now; utime.sleep_ms(10)
        if self.p.value()==0:
            try: self.cb()
            except: pass

class Term:
    def __init__(self,R,C):
        self.R=R; self.C=C; self.buf=[[' ']*C for _ in range(R)]
        self.v=0; self.h=0
    def snapshot(self,R,C,data):
        if R!=self.R or C!=self.C:
            self.R=R; self.C=C; self.buf=[[' ']*C for _ in range(R)]; self.v=0; self.h=0
        i=0
        for r in range(R):
            for c in range(C):
                b=data[i]; self.buf[r][c]=chr(b) if 32<=b<=126 else ' '; i+=1
    def sv(self,d): self.v=max(0,min(self.R-1,self.v+d))
    def sh(self,d): self.h=max(0,min(self.C-1,self.h+d))
    def window(self,w=16,h=2):
        out=[]
        for rr in range(h):
            r=min(self.R-1,self.v+rr)
            s=''.join(self.buf[r][self.h:self.h+w])
            if len(s)<w: s+=' '*(w-len(s))
            out.append(s)
        return out

uart=UART(UART_ID, UART_BAUD, tx=Pin(UART_TX_PIN), rx=Pin(UART_RX_PIN))
lcd=LCD(LCD_RS,LCD_E,LCD_D4,LCD_D5,LCD_D6,LCD_D7,LCD_COLS,LCD_ROWS)
term=Term(24,80)

def render():
    L=term.window(16,2)
    lcd.cursor(0,0); lcd.write(L[0])
    lcd.cursor(0,1); lcd.write(L[1])

def on_vs(d): term.sv(-d); render()
def on_hs(d): term.sh(+d); render()
def on_be(): uart.write(b"KEY:ENTER\n")
def on_bb(): uart.write(b"KEY:BACKSPACE\n")

Encoder(ENC_V_A,ENC_V_B,on_vs)
Encoder(ENC_H_A,ENC_H_B,on_hs)
Button(BTN_V,on_be)
Button(BTN_H,on_bb)

lcd.clr(); lcd.cursor(0,0); lcd.write("Pico Term Viewer")
lcd.cursor(0,1); lcd.write("Waiting for Pi...")

def read_frame():
    if uart.any()==0: return False
    b=uart.read(1)
    if not b or b[0]!=0x02: return False
    c=uart.read(1)
    if not c or c!=b'S': return False
    hdr=uart.read(2)
    if not hdr or len(hdr)<2: return False
    R=hdr[0]; C=hdr[1]
    total=R*C; data=bytearray()
    while len(data)<total:
        ch=uart.read(total-len(data))
        if ch: data.extend(ch)
    e=uart.read(1)
    if not e or e[0]!=0x03: return False
    term.snapshot(R,C,data); return True

while True:
    if read_frame(): render()
    utime.sleep_ms(2)
