#include "rbm_u340e.h"
#include "rbm_u340e_runtime.h"
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

    input.qualified = 1;
    input.slt_inputs.flags_p1156 = 0;
    state.driver[2].state_5302 = UINT8_MAX;
    const RbmU340eOutputState invalid_driver = state;
    assert(!rbm_u340e_outputs_step(&state, &input, &output));
    assert(!output.write_count && !output.slt_result.selected_7244 &&
           !output.writes[0].write_pending && !output.writes[1].write_pending);
    assert(memcmp(&state, &invalid_driver, sizeof(state)) == 0);
}

static void check_analog_selector(void)
{
    const struct {
        uint16_t low;
        uint16_t high;
        uint8_t position;
    } windows[] = {
        {889, 979, RBM_U340E_SELECTOR_P},
        {784, 856, RBM_U340E_SELECTOR_R},
        {624, 716, RBM_U340E_SELECTOR_N},
        {456, 543, RBM_U340E_SELECTOR_D},
        {301, 376, RBM_U340E_SELECTOR_2},
        {164, 223, RBM_U340E_SELECTOR_L},
    };
    RbmU340eSelectorInput selector = {0};
    for (unsigned int i = 0; i < sizeof(windows) / sizeof(windows[0]); ++i) {
        const uint16_t low = windows[i].low;
        const uint16_t high = windows[i].high;
        for (unsigned int sample_index = 0; sample_index < 3; ++sample_index) {
            assert(rbm_u340e_selector_sample(&selector, low) == RBM_U340E_SELECTOR_UNKNOWN);
        }
        assert(rbm_u340e_selector_sample(&selector, high) == windows[i].position);
        assert(rbm_u340e_selector_sample(&selector, high) == windows[i].position);
        for (unsigned int sample_index = 0; sample_index < 4; ++sample_index) {
            assert(rbm_u340e_selector_sample(&selector, high + 1) == RBM_U340E_SELECTOR_UNKNOWN);
            assert(rbm_u340e_selector_sample(&selector, low - 1) == RBM_U340E_SELECTOR_UNKNOWN);
        }
    }

    RbmU340eController controller;
    const RbmU340ePolicy policy = {.initial_mode = RBM_U340E_AUTO, .initial_overdrive_enabled = 1};
    assert(rbm_u340e_init(&controller, &policy));
    RbmU340eInput input = {.actual_gear = 2, .allowed_gears = 0x0f, .auto_request_valid = 1};
    input.auto_request.speed_4549 = 254;

    for (unsigned int i = 0; i < 4; ++i) {
        input.selector = rbm_u340e_selector_sample(&selector, 347);
    }
    assert(input.selector == RBM_U340E_SELECTOR_2);
    RbmU340eOutput range2 = sample(&controller, &input, 0);
    assert(range2.auto_request_valid && range2.auto_request.index_4854 == 3);
    assert(!range2.requested_gear && !range2.relay_mask);

    input.auto_request.speed_4549 = 0;
    assert(sample(&controller, &input, 0).requested_gear == 1);
    for (unsigned int i = 0; i < 3; ++i) {
        input.selector = rbm_u340e_selector_sample(&selector, 194);
        RbmU340eOutput transition = sample(&controller, &input, 0);
        assert(!transition.requested_gear && !transition.relay_mask);
    }
    input.selector = rbm_u340e_selector_sample(&selector, 194);
    assert(input.selector == RBM_U340E_SELECTOR_L);
    RbmU340eOutput low_range = sample(&controller, &input, 0);
    assert(low_range.requested_gear == 1 && low_range.relay_mask == RBM_U340E_RELAY_AUXILIARY);
    input.allowed_gears = 0x02;
    assert(!sample(&controller, &input, 0).requested_gear);
    input.allowed_gears = 0x0f;

    const uint16_t unavailable[] = {0, 1023, UINT16_MAX};
    for (unsigned int i = 0; i < sizeof(unavailable) / sizeof(unavailable[0]); ++i) {
        input.selector = rbm_u340e_selector_sample(&selector, unavailable[i]);
        assert(input.selector == RBM_U340E_SELECTOR_UNKNOWN);
        const RbmU340eOutput fault = sample(&controller, &input, 0);
        assert(!fault.requested_gear && !fault.relay_mask);
        for (unsigned int recovery = 0; recovery < 3; ++recovery) {
            assert(rbm_u340e_selector_sample(&selector, 194) == RBM_U340E_SELECTOR_UNKNOWN);
        }
        assert(rbm_u340e_selector_sample(&selector, 194) == RBM_U340E_SELECTOR_L);
    }
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

typedef struct {
    uint8_t records[2][FACTORY_ADAPT_RECORD_BYTES];
    unsigned prefix;
    unsigned writes;
    int corrupt_after_write;
} AdaptationStoreModel;

static const uint8_t *adaptation_read(void *context, unsigned slot)
{
    AdaptationStoreModel *store = context;
    assert(slot < 2);
    return store->records[slot];
}

static int adaptation_write(void *context, unsigned slot, const uint8_t *record, unsigned bytes)
{
    AdaptationStoreModel *store = context;
    assert(slot < 2 && bytes == FACTORY_ADAPT_RECORD_BYTES && store->prefix <= bytes);
    ++store->writes;
    memset(store->records[slot], 0xFF, bytes);
    memcpy(store->records[slot], record, store->prefix);
    if (store->corrupt_after_write) {
        store->records[slot][48] ^= 1u; /* First payload byte. */
    }
    return store->prefix == bytes;
}

static void check_adaptation_store(void)
{
    const FactoryAdaptation learned = {
        .learned_flags = {0xA3, 0x5C}, .up_counts = {1, 2, 3, 4, 5, 6},
        .down_counts = {7, 8}, .down = {-40, 40, -3, 0, 13}, .down_seen = 0x81,
    };
    const FactoryAdaptation reset_fixture = {0};
    AdaptationStoreModel store = {.prefix = FACTORY_ADAPT_RECORD_BYTES};
    memset(store.records, 0xFF, sizeof store.records);

    FactoryAdaptation loaded = learned;
    uint32_t generation = 42;
    assert(factory_adaptation_load(store.records[0], store.records[1], &loaded, &generation) == -1);
    assert(generation == 42 && memcmp(&loaded, &learned, sizeof loaded) == 0);

    FactoryAdaptation invalid = learned;
    invalid.down[0] = -41;
    assert(!factory_adaptation_valid(&invalid));
    invalid.down[0] = 41;
    assert(!factory_adaptation_save(&invalid, 1, adaptation_read, adaptation_write, &store));
    assert(!factory_adaptation_save(&learned, 0, adaptation_read, adaptation_write, &store));
    assert(store.writes == 0);
    assert(factory_adaptation_save(&learned, 1, adaptation_read, adaptation_write, &store) == 1);
    assert(factory_adaptation_save(&learned, 1, adaptation_read, adaptation_write, &store) == 2);
    assert(store.writes == 1);
    assert(factory_adaptation_load(store.records[0], store.records[1], &loaded, &generation) == 0);
    assert(generation == 1 && memcmp(&loaded, &learned, sizeof loaded) == 0);

    uint8_t first[FACTORY_ADAPT_RECORD_BYTES];
    memcpy(first, store.records[0], sizeof first);
    for (unsigned cut = 0; cut < FACTORY_ADAPT_RECORD_BYTES; ++cut) {
        store.prefix = cut;
        assert(!factory_adaptation_save(&reset_fixture, 1, adaptation_read, adaptation_write, &store));
        assert(memcmp(store.records[0], first, sizeof first) == 0);
        assert(factory_adaptation_load(store.records[0], store.records[1], &loaded, &generation) == 0);
        assert(generation == 1 && memcmp(&loaded, &learned, sizeof loaded) == 0);
    }
    store.prefix = FACTORY_ADAPT_RECORD_BYTES;
    store.corrupt_after_write = 1;
    assert(!factory_adaptation_save(&reset_fixture, 1, adaptation_read, adaptation_write, &store));
    assert(factory_adaptation_load(store.records[0], store.records[1], &loaded, &generation) == 0);
    assert(generation == 1 && memcmp(&loaded, &learned, sizeof loaded) == 0);
    store.corrupt_after_write = 0;

    assert(factory_adaptation_encode(store.records[0], &learned, UINT32_MAX));
    assert(factory_adaptation_save(&reset_fixture, 1, adaptation_read, adaptation_write, &store) == 1);
    assert(factory_adaptation_load(store.records[0], store.records[1], &loaded, &generation) == 1);
    assert(generation == 0 && memcmp(&loaded, &reset_fixture, sizeof loaded) == 0);

    FactoryHydraulics restarted = {0};
    assert(factory_hydraulics_set(&restarted, -7184, 2, 0x1153u));
    assert(factory_hydraulics_restore(&restarted, &learned));
    assert(factory_hydraulics_restore(&restarted, &loaded));
    factory_hydraulics_capture(&restarted, &loaded);
    assert(memcmp(&loaded, &reset_fixture, sizeof loaded) == 0);
    uint32_t unrelated;
    assert(factory_hydraulics_get(&restarted, -7184, 2, &unrelated) && unrelated == 0x1153u);

    /* A damaged newest record triggers the donor's fallback to older data,
     * including when the newest record contained a reset. */
    for (unsigned byte = 0; byte < FACTORY_ADAPT_RECORD_BYTES; ++byte) {
        for (unsigned bit = 0; bit < 8; ++bit) {
            const uint8_t mask = (uint8_t)(1u << bit);
            store.records[1][byte] ^= mask;
            assert(factory_adaptation_load(store.records[0], store.records[1], &loaded, &generation) == 0);
            assert(generation == UINT32_MAX && memcmp(&loaded, &learned, sizeof loaded) == 0);
            store.records[1][byte] ^= mask;
        }
    }

    assert(factory_adaptation_encode(store.records[0], &learned, UINT32_C(0x80000000)));
    assert(factory_adaptation_load(store.records[0], store.records[1], &loaded, &generation) == -1);
    assert(generation == UINT32_MAX && memcmp(&loaded, &learned, sizeof loaded) == 0);
    const unsigned writes = store.writes;
    assert(!factory_adaptation_save(&reset_fixture, 1, adaptation_read, adaptation_write, &store));
    assert(store.writes == writes);
#ifndef RBM_TEST_QUIET
    puts("Toyota adaptation store: 96 write cuts, 768 bit faults, reset and rollover passed.");
#endif
}

static void expect_adaptation_restore(RbmU340eRuntime *runtime, const FactoryAdaptation *baseline,
                                      const uint8_t *slot0, const uint8_t *slot1,
                                      RbmU340eAdaptationResult result, const FactoryAdaptation *expected)
{
    assert(rbm_u340e_runtime_restore_adaptation(runtime, baseline, slot0, slot1) == result);
    FactoryAdaptation actual;
    factory_hydraulics_capture(&runtime->gp, &actual);
    assert(memcmp(&actual, expected, sizeof actual) == 0);
    uint32_t unrelated;
    assert(factory_hydraulics_get(&runtime->gp, -7184, 2, &unrelated) && unrelated == 0x1153u);
}

static void check_adaptation_recovery(void)
{
    const FactoryAdaptation baseline = {.down = {-2}};
    const FactoryAdaptation learned = {.down_counts = {3, 17}, .down = {13, -3}, .down_seen = 0x81};
    const FactoryAdaptation reset_fixture = {0};
    const FactoryAdaptation invalid = {.down = {41}};
    RbmU340eRuntime runtime = {0};
    FactoryGearState gear = {0};
    uint8_t previous[FACTORY_ADAPT_RECORD_BYTES];
    uint8_t reset[FACTORY_ADAPT_RECORD_BYTES];
    uint8_t slot[FACTORY_ADAPT_RECORD_BYTES];
    memset(previous, 0xFF, sizeof previous);
    memset(slot, 0xFF, sizeof slot);

    assert(rbm_u340e_runtime_restore_adaptation(&runtime, &baseline, previous, slot) ==
           RBM_U340E_ADAPTATION_INVALID);
    assert(rbm_u340e_runtime_init(&runtime, &gear, &runtime.gp));
    assert(factory_hydraulics_set(&runtime.gp, -7184, 2, 0x1153u));
    expect_adaptation_restore(&runtime, &baseline, previous, slot,
                              RBM_U340E_ADAPTATION_BASELINE_UNPUBLISHED, &baseline);

    assert(factory_adaptation_encode(previous, &learned, UINT32_MAX));
    assert(factory_adaptation_encode(reset, &reset_fixture, 0));
    enum { marker_offset = FACTORY_ADAPT_RECORD_BYTES - 4u };
    for (unsigned cut = 0; cut < FACTORY_ADAPT_RECORD_BYTES; ++cut) {
        memset(slot, 0xFF, sizeof slot);
        memcpy(slot, reset, cut);
        if (cut <= marker_offset) {
            expect_adaptation_restore(&runtime, &baseline, previous, slot,
                                      RBM_U340E_ADAPTATION_LOADED, &learned);
        } else {
            expect_adaptation_restore(&runtime, &baseline, previous, slot,
                                      RBM_U340E_ADAPTATION_BASELINE_UNTRUSTED, &baseline);
        }
    }

    expect_adaptation_restore(&runtime, &baseline, previous, reset,
                              RBM_U340E_ADAPTATION_LOADED, &reset_fixture);
    expect_adaptation_restore(&runtime, &baseline, reset, previous,
                              RBM_U340E_ADAPTATION_LOADED, &reset_fixture);
    memcpy(slot, reset, sizeof slot);
    for (unsigned byte = 0; byte < FACTORY_ADAPT_RECORD_BYTES; ++byte) {
        for (unsigned bit = 0; bit < 8u; ++bit) {
            const uint8_t mask = (uint8_t)(1u << bit);
            slot[byte] ^= mask;
            expect_adaptation_restore(&runtime, &baseline, previous, slot,
                                      RBM_U340E_ADAPTATION_BASELINE_UNTRUSTED, &baseline);
            expect_adaptation_restore(&runtime, &baseline, slot, previous,
                                      RBM_U340E_ADAPTATION_BASELINE_UNTRUSTED, &baseline);
            slot[byte] ^= mask;
        }
    }
    expect_adaptation_restore(&runtime, &baseline, previous, NULL,
                              RBM_U340E_ADAPTATION_BASELINE_UNTRUSTED, &baseline);
    expect_adaptation_restore(&runtime, &baseline, NULL, previous,
                              RBM_U340E_ADAPTATION_BASELINE_UNTRUSTED, &baseline);
    expect_adaptation_restore(&runtime, &baseline, NULL, NULL,
                              RBM_U340E_ADAPTATION_BASELINE_UNTRUSTED, &baseline);
    assert(factory_adaptation_encode(previous, &learned, UINT32_C(0x80000000)));
    expect_adaptation_restore(&runtime, &baseline, previous, reset,
                              RBM_U340E_ADAPTATION_BASELINE_UNTRUSTED, &baseline);

    assert(factory_hydraulics_restore(&runtime.gp, &learned));
    expect_adaptation_restore(&runtime, &invalid, previous, reset, RBM_U340E_ADAPTATION_INVALID, &learned);
    expect_adaptation_restore(&runtime, NULL, previous, reset, RBM_U340E_ADAPTATION_INVALID, &learned);
    expect_adaptation_restore(&runtime, &baseline, previous, previous, RBM_U340E_ADAPTATION_INVALID, &learned);
#ifndef RBM_TEST_QUIET
    puts("Toyota adaptation recovery: 96 write cuts, 768 bit faults in either slot, and rollover passed.");
#endif
}

#ifdef RBM_TEST_TRANSFERS
unsigned rbm_test_hydraulic_transfer(void);
#endif
#ifdef RBM_TEST_RUNTIME
void rbm_test_runtime(void);
#endif

int main(void)
{
    check_driver_controls();
    check_analog_selector();
    check_output_path();
    check_hydraulic_cycle();
    check_adaptation_store();
    check_adaptation_recovery();
#ifdef RBM_TEST_RUNTIME
    rbm_test_runtime();
#endif
#ifdef RBM_TEST_TRANSFERS
    const unsigned verified_fields = rbm_test_hydraulic_transfer();
    assert(verified_fields == 292);
#ifndef RBM_TEST_QUIET
    printf("Verified %u GP transfer fields and five donor hydraulic snapshots.\n", verified_fields);
#endif
#endif
#ifndef RBM_TEST_QUIET
    puts("Controller tests passed: six ADC ranges, relays, Auto, Tiptronic, OD, S1/S2, ST and SLT.");
#endif
    return 0;
}
