// tusb_config.h
#pragma once
#include "tusb_option.h"

#define CFG_TUSB_MCU                OPT_MCU_RP2040
#define CFG_TUSB_OS                 OPT_OS_NONE
#define CFG_TUSB_RHPORT0_MODE      (OPT_MODE_HOST | OPT_MODE_FULL_SPEED)
#define CFG_TUSB_MEM_SECTION
#define CFG_TUSB_MEM_ALIGN         __attribute__ ((aligned(4)))

// Host configuration
#define CFG_TUH_ENUMERATION_BUFSIZE    256
#define CFG_TUH_HUB                     1
#define CFG_TUH_HID                     4
#define CFG_TUH_HID_EPIN_BUFSIZE       64
#define CFG_TUH_HID_EPOUT_BUFSIZE      64
#define CFG_TUH_HID_KEYBOARD           1
#define CFG_TUH_HID_MOUSE              1
#define CFG_TUH_CDC                    0
#define CFG_TUH_MSC                    0
#define CFG_TUH_VENDOR                 0
