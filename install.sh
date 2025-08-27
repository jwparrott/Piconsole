#!/usr/bin/env bash
set -euo pipefail

# install.sh
# Installs dependencies on Raspberry Pi OS and sets up serial.
# Usage: sudo ./install.sh
#
# What this does:
#  - apt-get packages for Python 3 and pip
#  - pip installs pyserial and pyte
#  - enables UART on Pi (adds enable_uart=1), keeps SSH console off serial
#  - prints next steps

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root: sudo ./install.sh"
  exit 1
fi

apt-get update
apt-get install -y python3 python3-pip

python3 -m pip install --upgrade pip
python3 -m pip install pyserial pyte

# Enable UART in /boot/config.txt if not already
CONFIG=/boot/config.txt
if ! grep -q "^enable_uart=1" "$CONFIG"; then
  echo "enable_uart=1" >> "$CONFIG"
  echo "Added enable_uart=1 to $CONFIG"
fi

# Ensure serial console not using UART (manual step reminder)
echo
echo "----------------------------------------------------------------"
echo "Serial setup:"
echo " - Make sure the serial login console is disabled."
echo "   Run: sudo raspi-config -> Interface Options -> Serial Port ->"
echo "     Login shell over serial?  No"
echo "     Enable serial hardware?   Yes"
echo " - Or, manually remove 'console=serial0,115200' from /boot/cmdline.txt"
echo "   and reboot."
echo "----------------------------------------------------------------"
echo
echo "Next steps:"
echo " 1) Reboot the Pi."
echo " 2) Connect Pico UART0: GP0->Pi GPIO15 (RXD0), GP1<-Pi GPIO14 (TXD0), and GND."
echo " 3) Flash MicroPython on the Pico and copy pico_main.py to it (as main.py)."
echo " 4) Run: python3 /path/to/pi_bridge.py --port /dev/serial0 --baud 115200 --rows 24 --cols 80 --mirror"
echo
echo "Done."
