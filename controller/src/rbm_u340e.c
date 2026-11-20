#include "rbm_u340e.h"

#include <stddef.h>

enum {
    BUTTON_MASK = RBM_U340E_BUTTON_MODE | RBM_U340E_BUTTON_UP |
        RBM_U340E_BUTTON_DOWN | RBM_U340E_BUTTON_OVERDRIVE,
    GEAR_MASK = 0x0f,
    SHIFT_BUTTON_MASK = RBM_U340E_BUTTON_UP | RBM_U340E_BUTTON_DOWN,
    OVERDRIVE_MODE_MASK = RBM_U340E_OVERDRIVE_AUTO | RBM_U340E_OVERDRIVE_TIPTRONIC
};

uint8_t rbm_u340e_selector_sample(RbmU340eSelectorInput *state, uint16_t adc)
{
    static const uint16_t limits[][2] = {
        [RBM_U340E_SELECTOR_P] = {889, 980},
        [RBM_U340E_SELECTOR_R] = {784, 857},
        [RBM_U340E_SELECTOR_N] = {624, 717},
        [RBM_U340E_SELECTOR_D] = {456, 544},
        [RBM_U340E_SELECTOR_2] = {301, 377},
        [RBM_U340E_SELECTOR_L] = {164, 224},
    };
    if (!state) {
        return RBM_U340E_SELECTOR_UNKNOWN;
    }

    uint8_t range = RBM_U340E_SELECTOR_UNKNOWN;
    for (uint8_t position = RBM_U340E_SELECTOR_P; position <= RBM_U340E_SELECTOR_L; ++position) {
        if (adc >= limits[position][0] && adc < limits[position][1]) {
            range = position;
            break;
        }
    }
    if (range == RBM_U340E_SELECTOR_UNKNOWN) {
        *state = (RbmU340eSelectorInput){0};
    } else if (range != state->candidate) {
        state->candidate = range;
        state->samples = 1;
    } else if (state->samples < 4) {
        ++state->samples;
    }
    return state->samples == 4 ? range : RBM_U340E_SELECTOR_UNKNOWN;
}

int rbm_u340e_init(RbmU340eController *controller, const RbmU340ePolicy *policy)
{
    if (!controller) {
        return 0;
    }
    controller->initialized = 0u;
    if (!policy || policy->initial_mode > RBM_U340E_TIPTRONIC ||
        policy->initial_overdrive_enabled > 1 ||
        (policy->manual_selectors & ~RBM_U340E_FORWARD_SELECTORS) ||
        (policy->overdrive_limit_modes & ~OVERDRIVE_MODE_MASK)) {
        return 0;
    }

    RbmU340eController initial = {0};
    initial.policy = *policy;
    initial.mode = policy->initial_mode;
    initial.overdrive_enabled = policy->initial_overdrive_enabled;
    initial.initialized = 1u;
    *controller = initial;
    return 1;
}

static uint8_t button_edges(RbmU340eController *controller, const RbmU340eInput *input)
{
    if (!input->buttons_valid) {
        controller->buttons_seen = 0;
        return 0;
    }

    uint8_t rising = 0;
    if (controller->buttons_seen) {
        rising = input->stable_buttons & (uint8_t)~controller->previous_buttons;
    }
    controller->previous_buttons = input->stable_buttons;
    controller->buttons_seen = 1;
    return rising;
}

static uint8_t relay_commands(uint8_t selector)
{
    if (selector == RBM_U340E_SELECTOR_R) {
        return RBM_U340E_RELAY_REVERSE | RBM_U340E_RELAY_AUXILIARY;
    }
    if (selector == RBM_U340E_SELECTOR_L) {
        return RBM_U340E_RELAY_AUXILIARY;
    }
    return 0;
}

static uint8_t propose_gear(const RbmU340eController *controller,
    const RbmU340eInput *input, uint8_t rising, RbmU340eOutput *output)
{
    static const uint8_t range_mask[] = {
        [RBM_U340E_SELECTOR_D] = GEAR_MASK,
        [RBM_U340E_SELECTOR_2] = 0x03,
        [RBM_U340E_SELECTOR_L] = 0x01,
    };
    const unsigned allowed = input->allowed_gears & range_mask[input->selector];
    const unsigned selector_bit = 1u << input->selector;
    if (input->shifting || !input->actual_gear || !allowed) {
        return 0;
    }

    const int overdrive_limited = !controller->overdrive_enabled &&
        (controller->policy.overdrive_limit_modes & (1u << controller->mode));
    int gear;
    if (controller->mode == RBM_U340E_AUTO) {
        if (!input->auto_request_valid) {
            return 0;
        }
        output->auto_request = input->auto_request;
        if (!factory_request_stage(&output->auto_request) || output->auto_request.index_4854 > 3) {
            return 0;
        }
        output->auto_request_valid = 1;
        gear = output->auto_request.index_4854 + 1;
        if (overdrive_limited && gear == 4) {
            gear = 3;
        }
    } else {
        const uint8_t shift_button = rising & SHIFT_BUTTON_MASK;
        if (!(selector_bit & controller->policy.manual_selectors) || !shift_button) {
            return 0;
        }
        gear = input->actual_gear + (shift_button == RBM_U340E_BUTTON_UP ? 1 : -1);
    }

    if (gear < 1 || gear > 4 || (overdrive_limited && gear == 4) ||
        !(allowed & (1u << (gear - 1)))) {
        return 0;
    }
    return (uint8_t)gear;
}

int rbm_u340e_step(RbmU340eController *controller, const RbmU340eInput *input,
    RbmU340eOutput *output)
{
    if (!output) {
        return 0;
    }
    *output = (RbmU340eOutput){0};
    if (!controller || controller->initialized != 1u) {
        return 0;
    }
    if (!input || controller->mode > RBM_U340E_TIPTRONIC ||
        input->selector > RBM_U340E_SELECTOR_L || input->actual_gear > 4 ||
        (input->allowed_gears & ~GEAR_MASK) || (input->stable_buttons & ~BUTTON_MASK) ||
        input->buttons_valid > 1 || input->auto_request_valid > 1 || input->shifting > 1) {
        /* The next valid button sample establishes a new edge baseline. */
        controller->buttons_seen = 0;
        return 0;
    }

    const uint8_t rising = button_edges(controller, input);
    const uint8_t held_shift_buttons = input->stable_buttons & SHIFT_BUTTON_MASK;
    if (rising & RBM_U340E_BUTTON_MODE) {
        controller->mode ^= 1u;
    }
    if (rising & RBM_U340E_BUTTON_OVERDRIVE) {
        controller->overdrive_enabled ^= 1u;
        output->overdrive_pressed = 1;
    }

    output->mode = controller->mode;
    output->overdrive_enabled = controller->overdrive_enabled;
    /* A mode edge conflicts with either held shift button, even when
     * pressing that button and changing mode took separate samples. */
    output->conflicting_buttons = input->buttons_valid &&
        (held_shift_buttons == SHIFT_BUTTON_MASK ||
         (held_shift_buttons && (rising & RBM_U340E_BUTTON_MODE)));
    output->relay_mask = relay_commands(input->selector);
    if (!output->conflicting_buttons) {
        output->requested_gear = propose_gear(controller, input, rising, output);
    }
    return 1;
}

int rbm_u340e_outputs_init(RbmU340eOutputState *state, const FactoryDriverState snapshot[3])
{
    if (!state || !snapshot) {
        return 0;
    }
    for (size_t i = 0; i < 3; ++i) {
        const FactoryDriverState *driver = &snapshot[i];
        if (driver->state_5302 > 4 || driver->requested_5314 > 1 ||
            driver->inhibit_5311 > 1 || driver->override_5308 > 1 ||
            driver->forced_5305 > 1) {
            return 0;
        }
    }

    *state = (RbmU340eOutputState){.driver = {snapshot[0], snapshot[1], snapshot[2]}};
    return 1;
}

static int dispatch(const FactoryDriverBatch *batch, RbmU340eOutputState *state,
    RbmU340eHydraulicOutput *output)
{
    for (size_t i = 0; i < batch->count; ++i) {
        const FactoryDriverCommand command = batch->commands[i];
        const size_t index = command.channel == RBM_U340E_DONOR_CHANNEL_ST ? 2 : command.channel;
        FactoryDriverWrite write;
        if (index >= 3 || !factory_driver_dispatch(&state->driver[index], command.mode,
                command.channel, &write)) {
            return 0;
        }
        if (write.write_pending) {
            output->writes[output->write_count++] = write;
        }
    }
    return 1;
}

int rbm_u340e_outputs_step(RbmU340eOutputState *state,
    const RbmU340eHydraulicInput *input, RbmU340eHydraulicOutput *output)
{
    if (!output) {
        return 0;
    }
    *output = (RbmU340eHydraulicOutput){0};
    if (!state || !input || input->qualified != 1) {
        return 0;
    }

    RbmU340eOutputState pending = *state;
    output->shift = input->shift;
    output->st = input->st;
    output->slt = input->slt;
    FactoryDriverBatch shift_batch;
    FactoryDriverBatch st_batch;
    if (!factory_shift_outputs(&output->shift, input->driver_status[0], input->driver_status[1], &shift_batch) ||
        !factory_slt_correction_step(&output->slt, &input->slt_inputs, &output->slt_result) ||
        output->slt_result.selected_7244 < 0 ||
        !factory_st_output(&output->st, input->driver_status[2], &st_batch) ||
        !dispatch(&shift_batch, &pending, output) ||
        !dispatch(&st_batch, &pending, output)) {
        *output = (RbmU340eHydraulicOutput){0};
        return 0;
    }

    *state = pending;
    return 1;
}
