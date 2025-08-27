# pi_bridge.py (updated)
# - Spawns a shell under a PTY
# - Uses pyte to maintain an 80x24 terminal screen and sends snapshots to the Pico
# - Accepts input from Pico:
#       "KEY:ENTER" -> newline
#       "KEY:BACKSPACE" -> 0x7f
#       "TXT:<text>" -> literal ASCII bytes of <text>
#
# See install.sh for dependencies (pyserial, pyte).

import sys, os, time, argparse, select, serial, pty, tty, termios
import pyte

def open_serial(port, baud):
    return serial.Serial(port, baudrate=baud, timeout=0)

def spawn_shell():
    pid, fd = pty.fork()
    if pid == 0:
        os.execvp("bash", ["bash", "-i"])
    return pid, fd

def setup_pyte(rows, cols):
    screen = pyte.Screen(cols, rows)
    stream = pyte.Stream(screen)
    return screen, stream

def frame_bytes(screen):
    rows = screen.lines
    cols = screen.columns
    payload = bytearray()
    for r in range(rows):
        line = screen.display[r] if r < len(screen.display) else ""
        line = "".join(ch if 32 <= ord(ch) <= 126 else " " for ch in line)
        if len(line) < cols: line = line + (" " * (cols - len(line)))
        else: line = line[:cols]
        payload.extend(line.encode("ascii", "replace"))
    frm = bytearray()
    frm.append(0x02); frm.extend(b"S"); frm.append(rows & 0xFF); frm.append(cols & 0xFF)
    frm.extend(payload); frm.append(0x03)
    return bytes(frm)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/serial0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--rows", type=int, default=24)
    ap.add_argument("--cols", type=int, default=80)
    ap.add_argument("--mirror", action="store_true")
    args = ap.parse_args()

    ser = open_serial(args.port, args.baud)
    pid, pty_fd = spawn_shell()
    screen, stream = setup_pyte(args.rows, args.cols)

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
                        try:
                            stream.feed(data.decode("utf-8", "ignore"))
                        except Exception:
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
                        text = line.decode("ascii", "ignore").strip()
                        if text == "KEY:ENTER":
                            os.write(pty_fd, b"\n")
                        elif text == "KEY:BACKSPACE":
                            os.write(pty_fd, b"\x7f")
                        elif text.startswith("TXT:"):
                            payload = text[4:]
                            os.write(pty_fd, payload.encode("ascii", "ignore"))
                except Exception:
                    pass

            now = time.time()
            if now - last_send >= 0.05:
                try:
                    ser.write(frame_bytes(screen))
                except Exception:
                    pass
                last_send = now
    finally:
        termios.tcsetattr(stdin_fd, termios.TCSADRAIN, old_settings)

if __name__ == "__main__":
    main()
