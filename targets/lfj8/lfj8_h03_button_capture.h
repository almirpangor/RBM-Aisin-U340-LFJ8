#ifndef RBM_LFJ8_H03_BUTTON_CAPTURE_H
#define RBM_LFJ8_H03_BUTTON_CAPTURE_H

#include "lfj8_range_control.h"

enum {
    LFJ8_H03_BUTTON_P1 = 0,
    LFJ8_H03_BUTTON_AUX = 1,
    LFJ8_H03_BUTTON_BANKS = 2,
};

typedef struct {
    uint8_t bank;
    uint8_t mask;
    uint8_t active_low;
} Lfj8H03ButtonPin;

typedef struct {
    /* Mode, up, down, overdrive. Only overdrive may be unmapped (mask zero). */
    Lfj8H03ButtonPin pins[4];
} Lfj8H03ButtonMap;

typedef struct {
    uint32_t captured_us;
    uint32_t generation;
    uint8_t auxiliary;
    uint8_t available_banks; /* One bit per bank qualified by the caller. */
} Lfj8H03ButtonSample;

/* The caller serializes this capture, supplies the clock and generation, and
 * guarantees that any auxiliary byte and the P1DATA read belong to one
 * coherent observation. This function reads P1DATA once when it is mapped.
 * Pin masks must be single bits with no reuse within a bank.
 *
 * On failure the result is cleared. Report a failed current acquisition to
 * the button owner for immediate disarm; do not treat it as a released reading.
 * The existing button filter checks age and order using captured_us. */
int lfj8_h03_button_capture_locked(const Lfj8RegisterIo *io, const Lfj8H03ButtonMap *map,
    const Lfj8H03ButtonSample *sample, uint32_t generation, Lfj8ButtonReading *out);

#endif
