#include "lfj8_h03_button_capture.h"

#include <stddef.h>

static int decode_buttons(const Lfj8RegisterIo *io, const Lfj8H03ButtonMap *map,
    const Lfj8H03ButtonSample *sample, const uint8_t *captured_p1, Lfj8ButtonReading *out)
{
    if (!out) {
        return 0;
    }
    *out = (Lfj8ButtonReading){0};
    if (!map || !sample) {
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
    uint8_t p1data = 0;
    if (used[LFJ8_H03_BUTTON_P1]) {
        if (captured_p1) {
            p1data = *captured_p1;
        } else if (io && io->read8) {
            p1data = io->read8(io->context, LFJ8_H03_P1DATA_ADDRESS);
        } else {
            return 0;
        }
    }
    const uint8_t data[LFJ8_H03_BUTTON_BANKS] = {
        [LFJ8_H03_BUTTON_P1] = p1data,
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

int lfj8_h03_button_capture_locked(const Lfj8RegisterIo *io, const Lfj8H03ButtonMap *map,
    const Lfj8H03ButtonSample *sample, uint32_t generation, Lfj8ButtonReading *out)
{
    return decode_buttons(io, map, sample && sample->generation == generation ? sample : NULL,
                          NULL, out);
}

int lfj8_h03_button_decode_p1(const Lfj8H03ButtonMap *map, const Lfj8SelectorAdcReading *reading,
    Lfj8ButtonReading *out)
{
    if (!reading || reading->event != LFJ8_SELECTOR_ADC_VALUE || reading->p1_valid != 1u) {
        if (out) {
            *out = (Lfj8ButtonReading){0};
        }
        return 0;
    }
    const Lfj8H03ButtonSample sample = {
        .captured_us = reading->captured_us,
        .available_banks = 1u << LFJ8_H03_BUTTON_P1,
    };
    return decode_buttons(NULL, map, &sample, &reading->p1data, out);
}
