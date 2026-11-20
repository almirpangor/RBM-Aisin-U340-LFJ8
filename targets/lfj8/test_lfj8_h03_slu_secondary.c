#include "lfj8_h03_slu.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>

static uint16_t expected_characteristic(uint16_t selected)
{
    if (selected <= 2560u) {
        return 0u;
    }
    if (selected >= 25600u) {
        return 25600u;
    }
    return (uint16_t)((uint32_t)(selected - 2560u) * 25600u / 23040u);
}

static void expect(const Lfj8H03SluSecondaryInput *input, Lfj8H03SluSecondaryState *state,
                   uint16_t pressure, uint16_t selected, uint8_t timer, bool force)
{
    Lfj8H03SluSecondaryResult result;
    assert(lfj8_h03_slu_secondary(input, state, &result));
    assert(result.pressure_7136 == pressure);
    assert(result.command.selected_7246 == selected);
    assert(result.command.characteristic_7130 == expected_characteristic(selected));
    assert(result.command.force == force);
    assert(state->previous_mode_1637 == input->mode_4505 && state->timer_4735 == timer);
}

int main(void)
{
    Lfj8H03SluSecondaryInput input = {
        .baseline_7026 = 10000, .mode_4505 = 1, .selector_4544 = 0xa5, .qualified = true,
    };
    Lfj8H03SluSecondaryState state = {.timer_4735 = 7};
    expect(&input, &state, 0, 2560, 7, false);
    input.flags_4828 = 0x80;
    expect(&input, &state, 10000, 15600, 7, false);
    input.mode_4505 = 2;
    expect(&input, &state, 23040, 2560, 0, false);
    state.timer_4735 = 1;
    expect(&input, &state, 23040, 2560, 1, false);
    state.timer_4735 = 2;
    expect(&input, &state, 10000, 15600, 2, false);

    state.previous_mode_1637 = 1;
    input.temperature_7184 = 5121;
    expect(&input, &state, 10000, 15600, 0, false);
    input.temperature_7184 = 5120;
    expect(&input, &state, 23040, 2560, 0, false);
    state.timer_4735 = 1;
    expect(&input, &state, 10000, 15600, 1, false);

    input.mode_4505 = 3;
    input.offset_7028 = INT16_MIN;
    input.offset_7030 = INT16_MAX;
    input.flags_1636 = 2;
    expect(&input, &state, 2560, 23040, 1, false);
    input.flags_1636 = 0;
    expect(&input, &state, 20480, 5120, 1, false);

    state.previous_mode_1637 = 1;
    input.mode_4505 = 2;
    input.flags_4829 = 8;
    input.flags_4822 = 0x80;
    input.override_7082 = UINT16_MAX;
    expect(&input, &state, UINT16_MAX, 25601, 0, true);

    input.mode_4505 = 0;
    state.timer_4735 = 47;
    assert(!lfj8_h03_slu_secondary(&input, &state, NULL));
    input.qualified = false;
    Lfj8H03SluSecondaryResult stale = {1, {2, 3, true}};
    assert(!lfj8_h03_slu_secondary(&input, &state, &stale));
    assert(stale.pressure_7136 == 0 && stale.command.selected_7246 == 0 &&
           stale.command.characteristic_7130 == 0 && !stale.command.force);
    assert(state.previous_mode_1637 == 2 && state.timer_4735 == 47);
    puts("M32R SECONDARY SLU: 11 pressure/command cases, 2 refusal cases PASS");
    return 0;
}

void __init(void) {}
void __fini(void) {}
