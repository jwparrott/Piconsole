#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run as root: sudo ./install.sh"
  exit 1
fi

apt-get update
apt-get install -y python3 python3-pip
python3 -m pip install --upgrade pip
python3 -m pip install pyserial pyte

CONFIG=/boot/config.txt
if ! grep -q "^enable_uart=1" "$CONFIG"; then
  echo "enable_uart=1" >> "$CONFIG"
fi

echo
echo "Disable serial login, enable serial hardware via raspi-config."
echo "Reboot when done. Then run:"
echo "  python3 pi_bridge.py --port /dev/serial0 --baud 115200 --rows 24 --cols 80 --mirror"
