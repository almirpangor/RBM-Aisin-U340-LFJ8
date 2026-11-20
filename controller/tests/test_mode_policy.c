#include "rbm_u340e.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>

static const uint8_t range_limit[] = {
    [RBM_U340E_SELECTOR_D] = 4,
    [RBM_U340E_SELECTOR_2] = 2,
    [RBM_U340E_SELECTOR_L] = 1,
};

static RbmU340eOutput sample(RbmU340eController *controller, RbmU340eInput *input, uint8_t buttons)
{
    RbmU340eOutput output;
    input->stable_buttons = buttons;
    assert(rbm_u340e_step(controller, input, &output));
    return output;
}

static void check_restart(const RbmU340ePolicy *policy)
{
    RbmU340eController controller;
    RbmU340eInput input = {.selector = RBM_U340E_SELECTOR_D, .buttons_valid = 1};
    const uint8_t held = RBM_U340E_BUTTON_MODE | RBM_U340E_BUTTON_OVERDRIVE;
    assert(rbm_u340e_init(&controller, policy));
    RbmU340eOutput output = sample(&controller, &input, held);
    assert(output.mode == policy->initial_mode);
    assert(output.overdrive_enabled == policy->initial_overdrive_enabled);
    assert(!output.overdrive_pressed);

    sample(&controller, &input, 0);
    output = sample(&controller, &input, RBM_U340E_BUTTON_MODE);
    assert(output.mode != policy->initial_mode);
    sample(&controller, &input, 0);
    output = sample(&controller, &input, RBM_U340E_BUTTON_OVERDRIVE);
    assert(output.overdrive_pressed && output.overdrive_enabled != policy->initial_overdrive_enabled);

    assert(rbm_u340e_init(&controller, policy));
    output = sample(&controller, &input, held);
    assert(output.mode == policy->initial_mode);
    assert(output.overdrive_enabled == policy->initial_overdrive_enabled);
    assert(!output.overdrive_pressed);
}

static uint8_t permitted_target(const RbmU340eInput *input, int target)
{
    if (target < 1 || target > range_limit[input->selector] ||
        !input->actual_gear || input->shifting) {
        return 0;
    }
    return input->allowed_gears & (1u << (target - 1)) ? (uint8_t)target : 0;
}

static void check_automatic(const RbmU340ePolicy *policy, RbmU340eInput input,
                            uint8_t donor_gear, uint8_t donor_speed)
{
    RbmU340eController controller;
    assert(rbm_u340e_init(&controller, policy));
    input.auto_request_valid = donor_gear != 0;
    input.auto_request.speed_4549 = donor_speed;
    const RbmU340eOutput output = sample(&controller, &input, 0);
    if (output.auto_request_valid) {
        assert(output.auto_request.index_4854 + 1 == donor_gear);
    }
    const int limit_fourth = !policy->initial_overdrive_enabled &&
                             (policy->overdrive_limit_modes & RBM_U340E_OVERDRIVE_AUTO);
    const int target = donor_gear == 4 && limit_fourth ? 3 : donor_gear;
    assert(output.requested_gear == permitted_target(&input, target));
}

static void check_manual(const RbmU340ePolicy *policy, RbmU340eInput input, uint8_t button, int increment)
{
    RbmU340eController controller;
    assert(rbm_u340e_init(&controller, policy));
    assert(!sample(&controller, &input, 0).requested_gear);
    const int target = input.actual_gear + increment;
    const int range_enabled = policy->manual_selectors & (1u << input.selector);
    const int limit_fourth = !policy->initial_overdrive_enabled &&
                             (policy->overdrive_limit_modes & RBM_U340E_OVERDRIVE_TIPTRONIC);
    const uint8_t expected = range_enabled && !(limit_fourth && target == 4)
        ? permitted_target(&input, target) : 0;
    assert(sample(&controller, &input, button).requested_gear == expected);
    assert(!sample(&controller, &input, button).requested_gear);
}

static unsigned check_range_matrix(const RbmU340ePolicy *policy, const uint8_t donor_speeds[5])
{
    RbmU340eInput input = {.buttons_valid = 1};
    unsigned cases = 0;
    for (input.selector = RBM_U340E_SELECTOR_UNKNOWN; input.selector <= RBM_U340E_SELECTOR_L;
         ++input.selector) {
        for (input.actual_gear = 0; input.actual_gear <= 4; ++input.actual_gear) {
            for (input.allowed_gears = 0; input.allowed_gears < 16; ++input.allowed_gears) {
                for (input.shifting = 0; input.shifting <= 1; ++input.shifting) {
                    if (policy->initial_mode == RBM_U340E_AUTO) {
                        for (uint8_t request = 0; request <= 4; ++request) {
                            check_automatic(policy, input, request, donor_speeds[request]);
                            ++cases;
                        }
                    } else {
                        check_manual(policy, input, RBM_U340E_BUTTON_UP, 1);
                        check_manual(policy, input, RBM_U340E_BUTTON_DOWN, -1);
                        cases += 2;
                    }
                }
            }
        }
    }
    return cases;
}

static void check_auto_conflicts(RbmU340ePolicy policy)
{
    RbmU340eController controller;
    RbmU340eInput input = {
        .selector = RBM_U340E_SELECTOR_D, .actual_gear = 3, .allowed_gears = 15,
        .buttons_valid = 1, .auto_request_valid = 1, .auto_request.speed_4549 = 254,
    };
    assert(rbm_u340e_init(&controller, &policy));
    const uint8_t normal = !policy.initial_overdrive_enabled &&
        (policy.overdrive_limit_modes & RBM_U340E_OVERDRIVE_AUTO) ? 3u : 4u;
    RbmU340eOutput output = sample(&controller, &input, 0);
    assert(output.requested_gear == (policy.initial_mode == RBM_U340E_AUTO ? normal : 0u));

    const uint8_t mode = RBM_U340E_BUTTON_MODE;
    const uint8_t up = RBM_U340E_BUTTON_UP;
    const uint8_t down = RBM_U340E_BUTTON_DOWN;
    const uint8_t conflict = policy.initial_mode == RBM_U340E_AUTO ? up | down : mode | up;

    output = sample(&controller, &input, conflict);
    assert(output.mode == RBM_U340E_AUTO && output.conflicting_buttons);
    assert(!output.requested_gear && !output.auto_request_valid);
    assert(output.overdrive_enabled == policy.initial_overdrive_enabled);

    output = sample(&controller, &input, up | down);
    assert(output.conflicting_buttons && !output.requested_gear && !output.auto_request_valid);
    output = sample(&controller, &input, up | down);
    assert(output.conflicting_buttons && !output.requested_gear && !output.auto_request_valid);

    output = sample(&controller, &input, up);
    assert(!output.conflicting_buttons && output.requested_gear == normal && output.auto_request_valid);
    output = sample(&controller, &input, 0);
    assert(!output.conflicting_buttons && output.requested_gear == normal && output.auto_request_valid);
}

int main(void)
{
    FactoryRequestState donor = {0};
    factory_lookup_thresholds(&donor);
    /* The normal Toyota bank produces 2 and 3 at the first two thresholds.
     * These are donor speed codes for test snapshots. */
    const uint8_t donor_speeds[5] = {0, 0, donor.thresholds_4541[0], donor.thresholds_4541[1], 254};
    RbmU340ePolicy policy;
    unsigned restart_cases = 0;
    unsigned range_cases = 0;
    for (unsigned mask = 0; mask < 8; ++mask) {
        policy.manual_selectors = (uint8_t)(mask << RBM_U340E_SELECTOR_D);
        for (policy.overdrive_limit_modes = 0; policy.overdrive_limit_modes <= 3;
             ++policy.overdrive_limit_modes) {
            for (policy.initial_mode = RBM_U340E_AUTO; policy.initial_mode <= RBM_U340E_TIPTRONIC;
                 ++policy.initial_mode) {
                for (policy.initial_overdrive_enabled = 0; policy.initial_overdrive_enabled <= 1;
                     ++policy.initial_overdrive_enabled) {
                    check_restart(&policy);
                    ++restart_cases;
                    check_auto_conflicts(policy);
                    range_cases += check_range_matrix(&policy, donor_speeds);
                }
            }
        }
    }
    printf("MODE-03 policy: %u restart profiles, %u conflict profiles and %u gear proposal cases PASS.\n",
           restart_cases, restart_cases, range_cases);
    return 0;
}
