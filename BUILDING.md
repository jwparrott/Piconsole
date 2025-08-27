# Building the Pico USB Host Firmware

This variant turns the **Pico** into a real **USB host** for a **USB keyboard** using **TinyUSB**, *and* keeps the LCD + encoders + UART link to the Raspberry Pi 3B for terminal snapshots.

## Prereqs

- Raspberry Pi **Pico SDK (C/C++)** installed and `PICO_SDK_PATH` set
- Submodules initialized (`git submodule update --init --recursive`)
- Toolchain: `cmake`, `ninja` (or `make`), `gcc-arm-none-eabi`

## Steps

```bash
# 1) Get pico-sdk if you don't already have it
git clone https://github.com/raspberrypi/pico-sdk.git --depth=1
cd pico-sdk
git submodule update --init --recursive
cd ..

# 2) Make a project folder and copy files
mkdir pico-host && cd pico-host
cp ../pico_host_main.c .
cp ../tusb_config.h .
cp ../CMakeLists.txt .
cp ../pico-sdk/external/pico_sdk_import.cmake .

# 3) Build
mkdir build && cd build
cmake -DPICO_SDK_PATH=../../pico-sdk -G "Ninja" ..
ninja
```

This creates `pico_host_main.uf2`. Hold **BOOTSEL** while plugging in the Pico, then drag-drop the UF2.

## Wiring (Host Power)

- Feed a clean **5V** to **VBUS (pin 40)** on the Pico (current-limited ~500mA). Share **GND**.
- Use a **Micro‑USB OTG adapter/cable** to connect your keyboard to the Pico’s USB connector.
- **Don’t** simultaneously power the Pico from a PC USB port.

See `wiring_diagram_host.pdf`.
