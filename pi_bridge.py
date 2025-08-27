# pi_bridge.py
# Python 3 script for Raspberry Pi 3B
# Responsibilities:
#  - Spawn a real shell under a pty (bash -i).
#  - Emulate a terminal using pyte (VT100) to maintain a full screen buffer (e.g., 80x24).
#  - Mirror the shell's stdout to this console (optional) AND send periodic full-screen snapshots
#    to the Pico over UART using the simple framing protocol:
#       [0x02 'S' ROWS COLS <ROWS*COLS bytes> 0x03]
#  - Accept "KEY:ENTER" / "KEY:BACKSPACE" messages from the Pico and write them to the shell pty.
#  - Also pass through any keyboard input from stdin to the shell pty (so you can type on the Pi).
#
# Dependencies: pyserial, pyte
#
# Serial wiring:
#   Pico GP0 (TX) -> Pi GPIO15 (RXD0)
#   Pico GP1 (RX) <- Pi GPIO14 (TXD0)
#   GND common
#
# Run:
#   python3 pi_bridge.py --port /dev/serial0 --baud 115200 --rows 24 --cols 80
#
# Author: ChatGPT

import sys, os, time, argparse, select, serial, pty, tty, termios
import pyte

def open_serial(port, baud):
    ser = serial.Serial(port, baudrate=baud, timeout=0)
    return ser

def spawn_shell():
    pid, fd = pty.fork()
    if pid == 0:
        # Child: new shell
        os.execvp("bash", ["bash", "-i"])
    # Parent: configure raw-ish stdin
    return pid, fd

def setup_pyte(rows, cols):
    screen = pyte.Screen(cols, rows)
    stream = pyte.Stream(screen)
    return screen, stream

def frame_bytes(screen):
    # Flatten the screen into rows*cols bytes, ascii 32..126 or space
    rows = screen.lines
    R = screen.lines  # undocumented but pyte exposes screen.display for text
    text_lines = screen.display  # list[str] of length rows
    # Make sure each line is exactly screen.columns
    rows = screen.lines
    cols = screen.columns
    payload = bytearray()
    for r in range(rows):
        line = text_lines[r] if r < len(text_lines) else ""
        # Replace nonprintable
        line = "".join(ch if 32 <= ord(ch) <= 126 else " " for ch in line)
        # Right-pad
        if len(line) < cols:
            line = line + (" " * (cols - len(line)))
        else:
            line = line[:cols]
        payload.extend(line.encode("ascii", "replace"))
    # Build frame
    frm = bytearray()
    frm.append(0x02)
    frm.extend(b"S")
    frm.append(rows & 0xFF)
    frm.append(cols & 0xFF)
    frm.extend(payload)
    frm.append(0x03)
    return bytes(frm)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/serial0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--rows", type=int, default=24)
    ap.add_argument("--cols", type=int, default=80)
    ap.add_argument("--mirror", action="store_true", help="Also print shell output locally")
    args = ap.parse_args()

    ser = open_serial(args.port, args.baud)
    pid, pty_fd = spawn_shell()
    screen, stream = setup_pyte(args.rows, args.cols)

    # Non-blocking stdin
    stdin_fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(stdin_fd)
    tty.setcbreak(stdin_fd)

    last_send = 0
    try:
        while True:
            rlist, _, _ = select.select([pty_fd, stdin_fd, ser], [], [], 0.02)

            if pty_fd in rlist:
                try:
                    data = os.read(pty_fd, 1024)
                    if data:
                        # Update emulator
                        try:
                            stream.feed(data.decode("utf-8", "ignore"))
                        except Exception:
                            # Fallback: best effort
                            stream.feed(data.decode("latin-1", "ignore"))
                        if args.mirror:
                            os.write(sys.stdout.fileno(), data)
                except OSError:
                    break

            if stdin_fd in rlist:
                data = os.read(stdin_fd, 1024)
                if data:
                    os.write(pty_fd, data)

            if ser in rlist:
                try:
                    line = ser.readline()
                    if line:
                        line = line.decode("ascii", "ignore").strip()
                        if line == "KEY:ENTER":
                            os.write(pty_fd, b"\n")
                        elif line == "KEY:BACKSPACE":
                            os.write(pty_fd, b"\x7f")
                except Exception:
                    pass

            now = time.time()
            if now - last_send >= 0.05:  # throttle ~20 FPS max
                frm = frame_bytes(screen)
                try:
                    ser.write(frm)
                except Exception:
                    pass
                last_send = now
    finally:
        termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_settings)

if __name__ == "__main__":
    main()
