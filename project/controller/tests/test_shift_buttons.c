#include "rbm_u340e.h"

#undef NDEBUG
#include <assert.h>
#include <stddef.h>
#include <stdio.h>

static RbmU340eOutput step(RbmU340eController *controller, RbmU340eInput *input, uint8_t buttons)
{
    RbmU340eOutput output;
    input->stable_buttons = buttons;
    assert(rbm_u340e_step(controller, input, &output));
    return output;
}

static void check_rejected_snapshot(const RbmU340ePolicy *policy)
{
    const uint8_t buttons[] = {RBM_U340E_BUTTON_MODE, RBM_U340E_BUTTON_UP,
                              RBM_U340E_BUTTON_DOWN, RBM_U340E_BUTTON_OVERDRIVE};
    const uint8_t gears[] = {0, 3, 1, 0};

    for (size_t i = 0; i < sizeof buttons / sizeof buttons[0]; ++i) {
        const uint8_t button = buttons[i];
        const RbmU340eInput malformed = {
            .selector = UINT8_MAX, .stable_buttons = button, .buttons_valid = 1,
            .actual_gear = 2, .allowed_gears = 0x0f,
        };
        const RbmU340eInput *const rejected[] = {&malformed, NULL};
        for (size_t j = 0; j < sizeof rejected / sizeof rejected[0]; ++j) {
            RbmU340eController controller;
            RbmU340eInput input = {
                .selector = RBM_U340E_SELECTOR_D, .buttons_valid = 1,
                .actual_gear = 2, .allowed_gears = 0x0f,
            };
            assert(rbm_u340e_init(&controller, policy));
            assert(step(&controller, &input, 0).requested_gear == 0);

            RbmU340eOutput failed = {.overdrive_pressed = 1, .requested_gear = 4};
            assert(!rbm_u340e_step(&controller, rejected[j], &failed));
            assert(!failed.requested_gear && !failed.overdrive_pressed);

            for (unsigned hold = 0; hold < 2; ++hold) {
                const RbmU340eOutput blocked = step(&controller, &input, button);
                assert(blocked.mode == RBM_U340E_TIPTRONIC && blocked.overdrive_enabled);
                assert(!blocked.overdrive_pressed && !blocked.requested_gear);
            }
            step(&controller, &input, 0);
            const RbmU340eOutput pressed = step(&controller, &input, button);
            assert(pressed.mode == (button == RBM_U340E_BUTTON_MODE ?
                                   RBM_U340E_AUTO : RBM_U340E_TIPTRONIC));
            assert(pressed.overdrive_enabled == (button != RBM_U340E_BUTTON_OVERDRIVE));
            assert(pressed.overdrive_pressed == (button == RBM_U340E_BUTTON_OVERDRIVE));
            assert(pressed.requested_gear == gears[i]);
        }
    }
}

int main(void)
{
    const RbmU340ePolicy policy = {
        .manual_selectors = 1u << RBM_U340E_SELECTOR_D,
        .initial_mode = RBM_U340E_TIPTRONIC,
        .initial_overdrive_enabled = 1,
    };
    const uint8_t directions[] = {RBM_U340E_BUTTON_UP, RBM_U340E_BUTTON_DOWN};
    const uint8_t gears[] = {3, 1};
    const uint8_t both = RBM_U340E_BUTTON_UP | RBM_U340E_BUTTON_DOWN;

    for (unsigned i = 0; i < 2; ++i) {
        const unsigned opposite = 1u - i;
        RbmU340eController controller;
        RbmU340eInput input = {
            .selector = RBM_U340E_SELECTOR_D, .buttons_valid = 1, .actual_gear = 2, .allowed_gears = 0x0f,
        };
        assert(rbm_u340e_init(&controller, &policy));
        assert(step(&controller, &input, 0).requested_gear == 0);
        assert(step(&controller, &input, directions[i]).requested_gear == gears[i]);

        RbmU340eOutput conflict = step(&controller, &input, both);
        assert(conflict.conflicting_buttons && conflict.requested_gear == 0);
        conflict = step(&controller, &input, both);
        assert(conflict.conflicting_buttons && conflict.requested_gear == 0);

        const RbmU340eOutput released = step(&controller, &input, directions[opposite]);
        assert(!released.conflicting_buttons && released.requested_gear == 0);
        step(&controller, &input, 0);
        assert(step(&controller, &input, directions[opposite]).requested_gear == gears[opposite]);

        input.buttons_valid = 0;
        const RbmU340eOutput invalid = step(&controller, &input, both);
        assert(!invalid.conflicting_buttons && invalid.requested_gear == 0);
        input.buttons_valid = 1;
        assert(step(&controller, &input, directions[i]).requested_gear == 0);
    }
    check_rejected_snapshot(&policy);
    puts("Tiptronic held shift conflicts and release PASS");
    puts("Button baseline after rejected or missing input PASS");
    return 0;
}
