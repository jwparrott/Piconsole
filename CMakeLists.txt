# CMakeLists.txt
cmake_minimum_required(VERSION 3.13)
include(pico_sdk_import.cmake)

project(pico_host_keyboard C CXX ASM)
pico_sdk_init()

add_executable(pico_host_main
  pico_host_main.c
)

target_compile_definitions(pico_host_main PUBLIC
  PICO_TINYUSB_HOST_ENABLED=1
)

target_include_directories(pico_host_main PUBLIC
  ${CMAKE_CURRENT_LIST_DIR}
)

target_link_libraries(pico_host_main
  pico_stdlib
  tinyusb_host
  tinyusb_board
  hardware_uart
  hardware_gpio
)

pico_add_extra_outputs(pico_host_main)

# Disable USB CDC stdio since we're in host mode; use UART for debug if needed
pico_enable_stdio_usb(pico_host_main 0)
pico_enable_stdio_uart(pico_host_main 1)
