#include "lfj8_h03_button_capture.h"

int lfj8_h03_button_capture_locked(const Lfj8RegisterIo *io, const Lfj8H03ButtonMap *map,
    const Lfj8H03ButtonSample *sample, uint32_t generation, Lfj8ButtonReading *out)
{
    if (!out) {
        return 0;
    }
    *out = (Lfj8ButtonReading){0};
    if (!map || !sample || sample->generation != generation) {
        return 0;
    }

    static const uint8_t buttons[] = {
        RBM_U340E_BUTTON_MODE, RBM_U340E_BUTTON_UP, RBM_U340E_BUTTON_DOWN,
        RBM_U340E_BUTTON_OVERDRIVE,
    };
    uint8_t used[LFJ8_H03_BUTTON_BANKS] = {0};
    for (unsigned i = 0; i < sizeof buttons; ++i) {
        const Lfj8H03ButtonPin *pin = &map->pins[i];
        if (!pin->mask && buttons[i] == RBM_U340E_BUTTON_OVERDRIVE) {
            continue;
        }
        if (pin->bank >= LFJ8_H03_BUTTON_BANKS || !pin->mask ||
            (pin->mask & (pin->mask - 1u)) || pin->active_low > 1u ||
            !(sample->available_banks & (1u << pin->bank)) ||
            (used[pin->bank] & pin->mask)) {
            return 0;
        }
        used[pin->bank] |= pin->mask;
    }
    if (used[LFJ8_H03_BUTTON_P1] && (!io || !io->read8)) {
        return 0;
    }

    const uint8_t data[LFJ8_H03_BUTTON_BANKS] = {
        [LFJ8_H03_BUTTON_P1] = used[LFJ8_H03_BUTTON_P1] ? io->read8(io->context, 0x800701u) : 0,
        [LFJ8_H03_BUTTON_AUX] = sample->auxiliary,
    };
    uint8_t pressed = 0;
    for (unsigned i = 0; i < sizeof buttons; ++i) {
        const Lfj8H03ButtonPin *pin = &map->pins[i];
        if (!pin->mask) {
            continue;
        }
        const uint8_t high = (data[pin->bank] & pin->mask) != 0u;
        if (high != pin->active_low) {
            pressed |= buttons[i];
        }
    }
    *out = (Lfj8ButtonReading){.captured_us = sample->captured_us, .pressed = pressed, .valid = 1};
    return 1;
}
