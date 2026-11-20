#include "lfj8_h03_slu.h"

#include <stddef.h>

#include "factory_core.h"

bool lfj8_h03_slu_command(const Lfj8H03SluInput *input, Lfj8H03SluCommand *command)
{
    if (!command) {
        return false;
    }
    if (!input || !input->qualified) {
        command->selected_7246 = 0u;
        command->characteristic_7130 = 0u;
        command->force = false;
        return false;
    }

    uint16_t selected = (input->flags_4834 & 0x40u) ? 25600u : 2560u;
    if ((input->selector_4544 == 0xa5u || (input->flags_4834 & 0x08u)) &&
        ((input->flags_4828 & 0x80u) || (input->flags_4827 & 0x01u) || (input->flags_4829 & 0x18u))) {
        /* The original stores the subtraction as an unsigned 16-bit word. */
        selected = (input->flags_4825 & 0x08u) ? 2560u : (uint16_t)(25600u - input->pressure_7136);
    }
    command->selected_7246 = selected;
    command->characteristic_7130 = factory_slu_characteristic(selected);
    command->force = (input->flags_4822 & 0x80u) != 0u;
    return true;
}

static uint16_t secondary_pressure(const Lfj8H03SluSecondaryInput *input,
                                   Lfj8H03SluSecondaryState *state)
{
    const bool enabled = (input->flags_4828 & 0x80u) != 0u;
    uint16_t pressure = 0u;
    if (enabled || (input->flags_4827 & 0x01u)) {
        pressure = input->baseline_7026;
        if (input->mode_4505 > 1u) {
            const int16_t offset = (input->flags_1636 & 0x02u) ? input->offset_7028 : input->offset_7030;
            int32_t corrected = (int32_t)pressure + offset;
            if (corrected < 2560) {
                corrected = 2560;
            } else if (corrected > 20480) {
                corrected = 20480;
            }
            pressure = (uint16_t)corrected;
        }
    }

    if (enabled && input->mode_4505 == 2u) {
        if (state->previous_mode_1637 == 1u) {
            state->timer_4735 = 0u;
        }
        const unsigned delay = input->temperature_7184 <= 5120u
            ? 1u + (input->temperature_7184 <= 2560u) : 0u;
        if (state->timer_4735 < delay) {
            pressure = 23040u;
        }
    }

    state->previous_mode_1637 = input->mode_4505;
    return (input->flags_4829 & 0x18u) ? input->override_7082 : pressure;
}

bool lfj8_h03_slu_secondary(const Lfj8H03SluSecondaryInput *input,
                           Lfj8H03SluSecondaryState *state, Lfj8H03SluSecondaryResult *result)
{
    if (!result) {
        return false;
    }
    if (!input || !state || !input->qualified) {
        result->pressure_7136 = 0u;
        return lfj8_h03_slu_command(NULL, &result->command);
    }

    result->pressure_7136 = secondary_pressure(input, state);
    const Lfj8H03SluInput command = {
        .pressure_7136 = result->pressure_7136,
        .selector_4544 = input->selector_4544,
        .flags_4834 = input->flags_4834,
        .flags_4828 = input->flags_4828,
        .flags_4827 = input->flags_4827,
        .flags_4829 = input->flags_4829,
        .flags_4825 = input->flags_4825,
        .flags_4822 = input->flags_4822,
        .qualified = true,
    };
    return lfj8_h03_slu_command(&command, &result->command);
}
