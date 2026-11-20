#include "rbm_u340e.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>

static RbmU340eOutput step(RbmU340eController *controller, RbmU340eInput *input, uint8_t buttons)
{
    RbmU340eOutput output;
    input->stable_buttons = buttons;
    assert(rbm_u340e_step(controller, input, &output));
    return output;
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
    puts("Tiptronic held shift conflicts and release PASS");
    return 0;
}
