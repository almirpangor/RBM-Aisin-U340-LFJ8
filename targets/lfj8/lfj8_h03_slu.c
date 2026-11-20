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
                                   Lfj8H03SluSecondaryState *state, uint16_t baseline)
{
    const bool enabled = (input->flags_4828 & 0x80u) != 0u;
    uint16_t pressure = 0u;
    if (enabled || (input->flags_4827 & 0x01u)) {
        pressure = baseline;
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

static bool clear_secondary(Lfj8H03SluSecondaryResult *result)
{
    if (result) {
        result->pressure_7136 = 0u;
        lfj8_h03_slu_command(NULL, &result->command);
    }
    return false;
}

static bool secondary_result(const Lfj8H03SluSecondaryInput *input,
                             Lfj8H03SluSecondaryState *state, uint16_t baseline,
                             Lfj8H03SluSecondaryResult *result)
{
    result->pressure_7136 = secondary_pressure(input, state, baseline);
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

bool lfj8_h03_slu_secondary(const Lfj8H03SluSecondaryInput *input,
                           Lfj8H03SluSecondaryState *state, Lfj8H03SluSecondaryResult *result)
{
    if (!input || !state || !result || !input->qualified) {
        return clear_secondary(result);
    }
    return secondary_result(input, state, input->baseline_7026, result);
}

static int16_t baseline_adjustment(const Lfj8H03SluBaselineInput *input, bool use_nt)
{
    static const uint8_t speed_axis[] = {7, 21, 31, 41, 51, 61, 71, 81};
    static const uint8_t nt_axis[] = {5, 128, 241, 243, 245, 247};
    const uint8_t *axis = use_nt ? nt_axis : speed_axis;
    const uint8_t *points = input->learning_4616 + (use_nt ? 7u : 0u);
    const uint16_t speed = use_nt ? input->speed_7204 : input->speed_7200;
    uint8_t table[15];
    const unsigned count = axis[0];

    for (unsigned i = 0; i <= count; ++i) {
        table[i] = axis[i];
    }
    for (unsigned i = 0; i < count; ++i) {
        table[count + 1u + i] = points[i];
    }
    /* Double in the donor's wide domain. Both maps have ended by UINT16_MAX. */
    const uint16_t doubled = speed > UINT16_MAX / 2u ? UINT16_MAX : (uint16_t)(speed * 2u);
    return (int16_t)((int32_t)(factory_interp1(doubled, table) >> 3) - 4096);
}

static uint16_t baseline_pressure(const Lfj8H03SluSecondaryInput *input,
                                  const Lfj8H03SluBaselineInput *baseline,
                                  Lfj8H03SluBaselineState *state)
{
    const bool use_nt = (input->flags_4827 & 0x01u) != 0u;
    if (baseline->gear == 0u || (!use_nt && !(input->flags_4828 & 0x80u))) {
        return 0u;
    }
    if (input->mode_4505 == 1u) {
        return 2560u;
    }
    if (input->flags_4825 & 0x08u) {
        return state->baseline_7026;
    }
    /* When both branches run, the NT curve supplies the final GP-7032. */
    state->adjustment_7032 = baseline_adjustment(baseline, use_nt);
    int32_t pressure = (int32_t)baseline->base_7054 + baseline->trim_7066 + state->adjustment_7032;
    if (pressure < 2560) {
        pressure = 2560;
    } else if (pressure > 20480) {
        pressure = 20480;
    }
    return (uint16_t)pressure;
}

bool lfj8_h03_slu_secondary_from_baseline(const Lfj8H03SluSecondaryInput *input,
                                         const Lfj8H03SluBaselineInput *baseline_input,
                                         Lfj8H03SluBaselineState *baseline_state,
                                         Lfj8H03SluSecondaryState *state,
                                         Lfj8H03SluSecondaryResult *result)
{
    if (!input || !baseline_input || !baseline_state || !state || !result || !input->qualified) {
        return clear_secondary(result);
    }
    baseline_state->baseline_7026 = baseline_pressure(input, baseline_input, baseline_state);
    return secondary_result(input, state, baseline_state->baseline_7026, result);
}
