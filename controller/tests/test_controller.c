#include "rbm_u340e.h"
#include "factory_hydraulics.h"

#undef NDEBUG
#include <assert.h>
#ifndef RBM_TEST_QUIET
#include <stdio.h>
#endif
#include <string.h>

static RbmU340eOutput sample(RbmU340eController *controller, RbmU340eInput *input, uint8_t buttons)
{
    RbmU340eOutput output;
    input->stable_buttons = buttons;
    assert(rbm_u340e_step(controller, input, &output));
    return output;
}

static void check_driver_controls(void)
{
    RbmU340eController controller;
    const RbmU340ePolicy policy = {
        .manual_selectors = 1u << RBM_U340E_SELECTOR_D,
        .overdrive_limit_modes = RBM_U340E_OVERDRIVE_AUTO | RBM_U340E_OVERDRIVE_TIPTRONIC,
        .initial_mode = RBM_U340E_AUTO,
        .initial_overdrive_enabled = 1,
    };
    assert(rbm_u340e_init(&controller, &policy));

    RbmU340eInput input = {
        .selector = RBM_U340E_SELECTOR_D,
        .buttons_valid = 1,
        .actual_gear = 2,
        .allowed_gears = 0x0f,
    };
    assert(sample(&controller, &input, RBM_U340E_BUTTON_MODE).mode == RBM_U340E_AUTO);
    sample(&controller, &input, 0);
    assert(sample(&controller, &input, RBM_U340E_BUTTON_MODE).mode == RBM_U340E_TIPTRONIC);
    assert(sample(&controller, &input, RBM_U340E_BUTTON_MODE).mode == RBM_U340E_TIPTRONIC);
    assert(sample(&controller, &input, RBM_U340E_BUTTON_UP).requested_gear == 3);
    assert(sample(&controller, &input, RBM_U340E_BUTTON_UP).requested_gear == 0);
    assert(sample(&controller, &input, RBM_U340E_BUTTON_DOWN).requested_gear == 1);
    sample(&controller, &input, 0);
    RbmU340eOutput conflict = sample(&controller, &input, RBM_U340E_BUTTON_UP | RBM_U340E_BUTTON_DOWN);
    assert(conflict.conflicting_buttons && !conflict.requested_gear);

    input.shifting = 1;
    sample(&controller, &input, 0);
    assert(!sample(&controller, &input, RBM_U340E_BUTTON_UP).requested_gear);
    input.shifting = 0;
    assert(!sample(&controller, &input, RBM_U340E_BUTTON_UP).requested_gear);
    input.allowed_gears = 0x03;
    sample(&controller, &input, 0);
    assert(!sample(&controller, &input, RBM_U340E_BUTTON_UP).requested_gear);

    input.buttons_valid = 0;
    sample(&controller, &input, 0);
    input.buttons_valid = 1;
    assert(sample(&controller, &input, RBM_U340E_BUTTON_MODE).mode == RBM_U340E_TIPTRONIC);
    input.actual_gear = 3;
    input.allowed_gears = 0x0f;
    RbmU340eOutput overdrive = sample(&controller, &input, RBM_U340E_BUTTON_OVERDRIVE);
    assert(overdrive.overdrive_pressed && !overdrive.overdrive_enabled);
    assert(!sample(&controller, &input, RBM_U340E_BUTTON_OVERDRIVE).overdrive_pressed);
    assert(!sample(&controller, &input, RBM_U340E_BUTTON_UP).requested_gear);
    assert(sample(&controller, &input, RBM_U340E_BUTTON_MODE).mode == RBM_U340E_AUTO);

    input.auto_request_valid = 1;
    input.auto_request.speed_4549 = 254;
    RbmU340eOutput automatic = sample(&controller, &input, 0);
    assert(automatic.auto_request_valid && automatic.auto_request.index_4854 == 3);
    assert(automatic.requested_gear == 3);
    assert(sample(&controller, &input, RBM_U340E_BUTTON_OVERDRIVE).requested_gear == 4);
    input.auto_request.index_4854 = 4;
    assert(!sample(&controller, &input, 0).auto_request_valid);
    input.auto_request.index_4854 = 0;
    input.auto_request.speed_4549 = 0;
    assert(sample(&controller, &input, 0).requested_gear == 1);

    input.selector = RBM_U340E_SELECTOR_R;
    RbmU340eOutput reverse = sample(&controller, &input, 0);
    assert(reverse.relay_mask == 3 && !reverse.requested_gear);
    input.selector = RBM_U340E_SELECTOR_L;
    assert(sample(&controller, &input, 0).relay_mask == RBM_U340E_RELAY_AUXILIARY);
    input.selector = RBM_U340E_SELECTOR_N;
    assert(!sample(&controller, &input, 0).relay_mask);
}

static void check_output_path(void)
{
    const FactoryDriverState snapshot[3] = {
        {.state_5302 = 1}, {.state_5302 = 1}, {.state_5302 = 1},
    };
    RbmU340eOutputState state;
    assert(rbm_u340e_outputs_init(&state, snapshot));

    RbmU340eHydraulicInput input = {
        .qualified = 1,
        .slt_inputs = {.selected_p1158 = 2560, .limit_7138 = 25600},
    };
    RbmU340eHydraulicOutput output;
    assert(rbm_u340e_outputs_step(&state, &input, &output));
    assert(output.slt_result.selected_7244 == 2560);
    assert(output.slt_result.characteristic_7132 == factory_slt_characteristic(2560));
    assert(output.write_count == 3);
    assert(output.writes[0].channel == RBM_U340E_DONOR_CHANNEL_S1 && output.writes[0].value);
    assert(output.writes[1].channel == RBM_U340E_DONOR_CHANNEL_S2 && output.writes[1].value);
    assert(output.writes[2].channel == RBM_U340E_DONOR_CHANNEL_ST && !output.writes[2].value);

    input.shift = output.shift;
    input.st = output.st;
    input.slt = output.slt;
    input.driver_status[0] = 2;
    input.st.flags_4832 = 0x60;
    assert(rbm_u340e_outputs_step(&state, &input, &output));
    assert(output.write_count == 3);
    assert(!output.writes[0].value && output.writes[1].value && output.writes[2].value);

    input.st = output.st;
    input.driver_status[2] = 2;
    input.st.count_4804 = 8;
    assert(rbm_u340e_outputs_step(&state, &input, &output));
    assert(!output.writes[2].value);

    const RbmU340eOutputState before = state;
    input.shift.index_4852 = 4;
    assert(!rbm_u340e_outputs_step(&state, &input, &output));
    assert(!output.write_count && memcmp(&state, &before, sizeof(state)) == 0);
    input.shift.index_4852 = 0;
    input.slt_inputs.flags_p1156 = 1;
    input.slt_inputs.override_7134 = -1;
    assert(!rbm_u340e_outputs_step(&state, &input, &output));
    assert(!output.write_count && memcmp(&state, &before, sizeof(state)) == 0);
    input.qualified = 0;
    assert(!rbm_u340e_outputs_step(&state, &input, &output));
    assert(!output.write_count && memcmp(&state, &before, sizeof(state)) == 0);
}

static uint32_t fixture_hash(const FactoryHydraulics *state)
{
    uint32_t hash = 2166136261u;
    for (unsigned i = 0; i < sizeof state->data; ++i) {
        hash = (hash ^ state->data[i]) * 16777619u;
    }
    return hash;
}

static void check_hydraulic_cycle(void)
{
    static const struct { int gp; unsigned width; uint32_t value; } fixture[] = {
        {-9044,2,0x0e21}, {-9030,2,0x0267}, {-8310,2,0x2a64}, {-8306,2,0x0248},
        {-8302,2,0x1f40}, {-8298,2,0x01b7}, {-8272,2,0x0c11}, {-8270,2,0x0b9a},
        {1102,2,0x17d3}, {1104,2,0x1023}, {1106,2,0x2154}, {1108,2,0x3285},
        {1110,2,0x43b6}, {1100,1,3}, {-4731,1,10}, {-4851,1,1}, {-4852,1,2},
        {-4854,1,2}, {-4548,1,50}, {-9732,4,0x01020304}, {-9728,4,0x20314253},
        {-9724,4,0x34567789}, {-9720,4,0x456789ab}, {-7184,2,0x1153},
    };
    FactoryHydraulics state = {0};
    for (unsigned i = 0; i < sizeof fixture / sizeof fixture[0]; ++i) {
        assert(factory_hydraulics_set(&state, fixture[i].gp, fixture[i].width, fixture[i].value));
    }
    /* Hashes of all 561 canonical bytes from the unmodified R1 x86-64 build. */
    factory_hydraulics_load_main(&state);
    assert(fixture_hash(&state) == 0xf69e6d93u);
    factory_hydraulics_load_observer(&state);
    assert(fixture_hash(&state) == 0xb8457a0eu);
    assert(factory_hydraulics_main(&state));
    assert(fixture_hash(&state) == 0x5b7f02c4u);
    assert(factory_hydraulics_torque_main(&state));
    assert(fixture_hash(&state) == 0x8b8723a4u);
    assert(factory_hydraulics_fast_learning(&state));
    assert(fixture_hash(&state) == 0x8b8723a4u);

    assert(factory_hydraulics_set(&state, -4619, 2, 0x5ca3));
    assert(factory_hydraulics_set(&state, -4594, 2, 0xb14e));
    FactoryAdaptation saved;
    factory_hydraulics_capture(&state, &saved);
    assert(saved.learned_flags[0] == 0xa3 && saved.learned_flags[1] == 0x5c);
    assert(saved.down_counts[0] == 0x4e && saved.down_counts[1] == 0xb1);
}

#ifdef RBM_TEST_TRANSFERS
unsigned rbm_test_hydraulic_transfer(void);
#endif

int main(void)
{
    check_driver_controls();
    check_output_path();
    check_hydraulic_cycle();
#ifdef RBM_TEST_TRANSFERS
    const unsigned verified_fields = rbm_test_hydraulic_transfer();
    assert(verified_fields == 292);
#ifndef RBM_TEST_QUIET
    printf("Verified %u GP transfer fields and five donor hydraulic snapshots.\n", verified_fields);
#endif
#endif
#ifndef RBM_TEST_QUIET
    puts("Controller tests passed: selector, relays, Auto, Tiptronic, OD, S1/S2, ST, SLT and rejection.");
#endif
    return 0;
}
