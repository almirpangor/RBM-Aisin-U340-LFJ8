#include "rbm_u340e_runtime.h"
#include "rbm_u340e.h"
#include "rbm_u340e_scheduler.h"

#undef NDEBUG
#include <assert.h>
#include <stddef.h>
#include <string.h>
#ifndef RBM_TEST_QUIET
#include <stdio.h>
#endif

static uint32_t gp_value(const FactoryHydraulics *gp, int offset, unsigned width)
{
    uint32_t value;
    assert(factory_hydraulics_get(gp, offset, width, &value));
    return value;
}

static void check_initialization(void)
{
    RbmU340eRuntime runtime = {0};
    FactoryGearState gear = {0};
    FactoryGearState work;
    FactoryHydraulics gp = {0};
    FactoryGearWrites writes = {.count = 1u};
    assert(!rbm_u340e_runtime_snapshot_gears(&runtime, &work));
    assert(!rbm_u340e_runtime_gears_outputs(&runtime, &work, &writes));
    assert(!writes.count);

    gear.b4852 = 2;
    assert(!rbm_u340e_runtime_init(&runtime, &gear, &gp));
    assert(!runtime.initialized);
    assert(factory_hydraulics_set(&gp, -4852, 1, 2));
    assert(rbm_u340e_runtime_init(&runtime, &gear, &gp));
    gear.b4852 = 0;
    assert(!rbm_u340e_runtime_init(&runtime, &gear, &gp));
    assert(rbm_u340e_runtime_snapshot_gears(&runtime, &work));
    assert(work.b4852 == 2);
}

static void check_compact_storage(void)
{
    struct UnalignedState {
        uint8_t before;
        RbmU340eRuntime runtime;
        uint8_t after;
    };
    union {
        uint32_t alignment;
        struct UnalignedState state;
    } fixture = {.state = {.before = 0x5au, .after = 0xa5u}};
    _Static_assert(sizeof(RbmU340eRuntime) == 829u, "runtime persistent bytes");
    _Static_assert(offsetof(struct UnalignedState, runtime) == 1u, "runtime at an odd address");

    FactoryGearState source = {
        .v1304 = {0x01234567u}, .v1360 = {0x1357u}, .u7166 = 0x2468u,
        .u7128 = 0xabceu, .thresholds = {0x65u},
        .b8880 = 0x17u, .b7419 = 0x29u, .b7193 = 0x31u, .b5722 = 0x43u,
        .b5297 = 0x53u, .b5153 = 0x67u, .b4839 = 0x74u, .b4837 = 0x81u,
        .b4828 = 0x94u, .b4821 = 0xa2u, .b4535 = 0xb3u, .b4850 = 0xc4u,
        .b4533 = 0xd8u, .driver5302 = {0xe9u, 0xfeu},
    };
    RbmU340eRuntime *runtime = &fixture.state.runtime;
    assert(((uintptr_t)runtime & 1u) == 1u);
    assert(rbm_u340e_runtime_init(runtime, &source, &runtime->gp));
    FactoryGearState work;
    memset(&work, 0x5c, sizeof work);
    assert(rbm_u340e_runtime_snapshot_gears(runtime, &work));
    assert(memcmp(&source, &work, sizeof work) == 0);
    assert(fixture.state.before == 0x5au && fixture.state.after == 0xa5u);
}

static void check_workspace_overlap(void)
{
    union {
        RbmU340eRuntime runtime;
        FactoryGearState work;
        FactoryGearWrites writes;
        struct { uint32_t prefix; FactoryGearState work; } shifted;
    } overlay = {.runtime = {0}};
    union {
        FactoryGearState work;
        FactoryGearWrites writes;
    } workspace = {.work = {0}};
    RbmU340eRuntime *runtime = &overlay.runtime;
    FactoryGearWrites writes = {.count = 1u};
    assert(rbm_u340e_runtime_init(runtime, &workspace.work, &runtime->gp));
    const RbmU340eRuntime before = *runtime;
    const FactoryGearState before_work = workspace.work;

    assert(!rbm_u340e_runtime_snapshot_gears(runtime, &overlay.work));
    assert(!rbm_u340e_runtime_snapshot_gears(runtime, &overlay.shifted.work));
    assert(!rbm_u340e_runtime_gears_outputs(runtime, &overlay.shifted.work, &writes));
    assert(!writes.count);
    assert(!rbm_u340e_runtime_gears_outputs(runtime, &workspace.work, &overlay.writes));
    assert(!rbm_u340e_runtime_gears_outputs(runtime, &workspace.work, &workspace.writes));
    assert(memcmp(runtime, &before, sizeof before) == 0);
    assert(memcmp(&workspace.work, &before_work, sizeof before_work) == 0);
}

static void check_live_stages(void)
{
    const uint32_t history[] = {0x01020304u, 0x20314253u, 0x34567789u, 0x456789abu};
    RbmU340eRuntime runtime = {0};
    FactoryGearState gear = {.driver5302 = {1u, 1u}, .b4841 = 0x0c};
    FactoryHydraulics gp = {0};
    assert(factory_hydraulics_set(&gp, -4841, 1, 0x0c));
    assert(rbm_u340e_runtime_init(&runtime, &gear, &gp));

    /* Mark the unshared half of the hydraulic history and the upper bytes
     * of the hydraulic flags object. The gear step must preserve them. */
    assert(factory_hydraulics_set(&runtime.gp, -9716, 4, 0x11223344u));
    assert(factory_hydraulics_set(&runtime.gp, -9704, 4, 0x55667788u));
    assert(factory_hydraulics_set(&runtime.gp, -9748, 4, 0xa37bc100u));
    assert(factory_hydraulics_set(&runtime.gp, -7184, 2, 0x1153u));
    assert(factory_hydraulics_set(&runtime.gp, -4771, 1, 254u));
    for (int i = 0; i < 4; ++i) {
        assert(factory_hydraulics_set(&runtime.gp, -9732 + 4 * i, 4, history[i]));
    }
    assert(rbm_u340e_runtime_snapshot_gears(&runtime, &gear));
    assert(gear.b4771 == 254u && gear.u7184 == 0x1153u && gear.b9748 == 0);
    for (int i = 0; i < 4; ++i) {
        assert(gear.d9732[i] == history[i]);
    }

    factory_hydraulics_counters_begin(&runtime.gp);
    assert(gp_value(&runtime.gp, -4771, 1) == 255u);
    gear.b4771 = 0; /* Stale shared fields must never replace a later FAST publication. */
    gear.b9748 = UINT8_MAX;
    gear.u7184 = 0;
    gear.periods[0] = 0x1234u; /* Gear-only state is supplied through the typed workspace. */
    FactoryGearWrites writes;
    assert(rbm_u340e_runtime_gears_outputs(&runtime, &gear, &writes));
    assert(writes.count == 2u);
    for (uint8_t i = 0; i < writes.count; ++i) {
        assert(writes.writes[i].write_pending && writes.writes[i].channel == i && writes.writes[i].value == 1u);
    }
    assert(gp_value(&runtime.gp, -4771, 1) == 255u);
    assert(gp_value(&runtime.gp, -4838, 1) == 0x0cu);
    assert(gp_value(&runtime.gp, -9748, 4) == 0xa37bc100u);
    assert(gp_value(&runtime.gp, -7184, 2) == 0x1153u);
    assert(gp_value(&runtime.gp, -9716, 4) == 0x11223344u);
    assert(gp_value(&runtime.gp, -9704, 4) == 0x55667788u);
    for (int i = 0; i < 4; ++i) {
        assert(gp_value(&runtime.gp, -9732 + 4 * i, 4) == history[i]);
    }

    assert(factory_hydraulics_control_main(&runtime.gp));
    assert(rbm_u340e_runtime_snapshot_gears(&runtime, &gear));
    assert(gear.b4841 == 0 && gear.b4838 == 0x0c && gear.periods[0] == 0x1234u);

    /* Invalid driver states are rejected by the real vendor gear stage. */
    const RbmU340eRuntime committed = runtime;
    gear.driver5302[1] = 5;
    assert(!rbm_u340e_runtime_gears_outputs(&runtime, &gear, &writes));
    assert(!writes.count);
    assert(memcmp(&runtime, &committed, sizeof runtime) == 0);
    assert(rbm_u340e_runtime_snapshot_gears(&runtime, &gear));
    assert(gear.driver5302[1] == 1 && gear.driver5314[0] == 1 && gear.b4841 == 0);
}

static void check_engine_main_publications(void)
{
    RbmU340eRuntime runtime = {0};
    FactoryHydraulics gp = {0};
    FactoryGearState gear = {.b8677 = 0xb5u, .u7164 = 111u, .u7186 = 222u, .u7184 = 333u, .u7202 = 444u};
    assert(factory_hydraulics_set(&gp, -7164, 2u, gear.u7164));
    assert(factory_hydraulics_set(&gp, -7186, 2u, gear.u7186));
    assert(factory_hydraulics_set(&gp, -7184, 2u, gear.u7184));
    assert(factory_hydraulics_set(&gp, -7202, 2u, gear.u7202));
    assert(rbm_u340e_runtime_init(&runtime, &gear, &gp));

    RbmU340eQualifiedEngineFeed feed = {.fa62 = 9600u, .f9b8 = 137u};
    RbmU340eMainEngineInputs prepared = {.speed_9306 = 9u, .coolant_9006 = 12u};
    const RbmU340eRuntime before = runtime;
    assert(!rbm_u340e_runtime_prepare_engine(&runtime, &feed, &prepared));
    assert(memcmp(&runtime, &before, sizeof runtime) == 0);
    assert(prepared.speed_9306 == 9u && prepared.coolant_9006 == 12u);
    feed.coherent = 1u;

    assert(rbm_u340e_runtime_prepare_engine(&runtime, &feed, &prepared));
    assert(prepared.speed_9306 == 1536u && prepared.coolant_9006 == 139u);
    assert(rbm_u340e_runtime_snapshot_gears(&runtime, &gear));
    assert(gear.b8677 == 0xa5u && gear.u7164 == 111u && gear.u7186 == 222u);
    assert(rbm_u340e_runtime_main_coolant(&runtime, &prepared));
    assert(gp_value(&runtime.gp, -7164, 2u) == 32480u);
    assert(gp_value(&runtime.gp, -7186, 2u) == 222u);
    assert(rbm_u340e_runtime_main_engine_speed(&runtime, &prepared));
    assert(gp_value(&runtime.gp, -7164, 2u) == 32480u && gp_value(&runtime.gp, -7186, 2u) == 3072u);
    assert(gp_value(&runtime.gp, -7184, 2u) == 333u && gp_value(&runtime.gp, -7202, 2u) == 444u);

    feed.fd10 = 0x1000u;
    feed.e026 = 2u;
    assert(rbm_u340e_runtime_prepare_engine(&runtime, &feed, &prepared));
    assert(prepared.speed_9306 == 0u && prepared.coolant_9006 == 139u);
    assert(rbm_u340e_runtime_main_coolant(&runtime, &prepared));
    assert(rbm_u340e_runtime_main_engine_speed(&runtime, &prepared));
    assert(rbm_u340e_runtime_snapshot_gears(&runtime, &gear));
    assert(gear.b8677 == 0xb5u && gear.u7164 == 30720u && gear.u7186 == 0u);

    feed.fd10 = 0u;
    feed.e026 = 0u;
    feed.f9b8 = UINT8_MAX;
    feed.fa62 = UINT16_MAX; /* Exercise the arithmetic domain of qualified FA62. */
    assert(rbm_u340e_runtime_prepare_engine(&runtime, &feed, &prepared));
    assert(rbm_u340e_runtime_main_coolant(&runtime, &prepared));
    assert(rbm_u340e_runtime_main_engine_speed(&runtime, &prepared));
    assert(gp_value(&runtime.gp, -7164, 2u) == 30720u && gp_value(&runtime.gp, -7186, 2u) == 20970u);
    feed.f9b8 = 9u;
    assert(rbm_u340e_runtime_prepare_engine(&runtime, &feed, &prepared));
    assert(prepared.coolant_9006 == 0xffc0u);
    assert(rbm_u340e_runtime_main_coolant(&runtime, &prepared));
    assert(gp_value(&runtime.gp, -7164, 2u) == 0u);
}

static void check_secondary_load_publication(void)
{
    RbmU340eRuntime runtime = {0};
    FactoryHydraulics gp = {0};
    const FactoryGearState gear = {0};
    uint8_t request = 0xc0u;
    assert(!rbm_u340e_runtime_secondary_load_qualify(&runtime, 0, &request));
    assert(request == 0xc0u);
    assert(rbm_u340e_runtime_init(&runtime, &gear, &gp));
    assert(!rbm_u340e_runtime_secondary_load_qualify(&runtime, 0, runtime.gp.data));

    assert(factory_hydraulics_set(&runtime.gp, -8310, 2u, 32767u));
    assert(factory_hydraulics_set(&runtime.gp, -8302, 2u, 32767u));
    assert(factory_hydraulics_set(&runtime.gp, -8270, 2u, 79u));
    assert(factory_hydraulics_set(&runtime.gp, -8272, 2u, 80u));
    assert(rbm_u340e_runtime_secondary_load_qualify(&runtime, 0, &request) && request == 0xd1u);
    assert(rbm_u340e_runtime_secondary_load_qualify(&runtime, 0, &request) && request == 0xf3u);

    assert(factory_hydraulics_set(&runtime.gp, -8270, 2u, 143u));
    assert(rbm_u340e_runtime_secondary_load_qualify(&runtime, 0, &request) && request == 0xf3u);
    assert(factory_hydraulics_set(&runtime.gp, -8270, 2u, 144u));
    assert(rbm_u340e_runtime_secondary_load_qualify(&runtime, 0, &request) && request == 0xe2u);
    assert(rbm_u340e_runtime_secondary_load_qualify(&runtime, 0, &request) && request == 0xc0u);

    assert(factory_hydraulics_set(&runtime.gp, -8272, 2u, 1000u));
    assert(factory_hydraulics_set(&runtime.gp, -8302, 2u, 65535u)); /* Signed ceiling -1. */
    assert(rbm_u340e_runtime_secondary_load_qualify(&runtime, 4, &request) && request == 0xd4u);
    assert(rbm_u340e_runtime_secondary_load_qualify(&runtime, 4, &request) && request == 0xfcu);

    assert(factory_hydraulics_set(&runtime.gp, -5299, 1u, 2u)); /* Native fallback to 786. */
    const RbmU340eRuntime prepared = runtime;
    assert(rbm_u340e_runtime_secondary_load_qualify(&runtime, 4, &request) && request == 0xf8u);
    assert(rbm_u340e_runtime_secondary_load_qualify(&runtime, 4, &request) && request == 0xf0u);
    assert(rbm_u340e_runtime_secondary_load_qualify(&runtime, 0, &request) && request == 0xe0u);
    assert(rbm_u340e_runtime_secondary_load_qualify(&runtime, 0, &request) && request == 0xc0u);
    assert(memcmp(&runtime, &prepared, sizeof runtime) == 0);
}

static RbmU340eRelease publish_tick(RbmU340eScheduler *schedule)
{
    assert(rbm_u340e_schedule_timer_irq(schedule) == RBM_U340E_IRQ_PRODUCER);
    const RbmU340eRelease released = rbm_u340e_schedule_producer_publish(schedule);
    assert(released != RBM_U340E_RELEASE_INVALID);
    assert(rbm_u340e_schedule_producer_done(schedule));
    return released;
}

static void release_range_main(RbmU340eScheduler *schedule, RbmU340eRuntime *runtime,
                               RbmU340eRangeState *range, RbmU340eRangeInputs *input)
{
    RbmU340eRelease release;
    do {
        release = publish_tick(schedule);
        if (release == RBM_U340E_RELEASE_FAST) {
            assert(rbm_u340e_schedule_fast_claim(schedule));
            assert(rbm_u340e_schedule_fast_begin(schedule, &runtime->gp));
            assert(rbm_u340e_range_fast(range, input));
            assert(rbm_u340e_schedule_fast_end(schedule, &runtime->gp));
            assert(rbm_u340e_schedule_fast_done(schedule));
        } else if (release == RBM_U340E_RELEASE_SECONDARY) {
            assert(rbm_u340e_schedule_secondary_claim(schedule));
            assert(rbm_u340e_runtime_secondary_load_qualify(runtime, input->inhibit_5250,
                                                            &input->request_1120));
            if (rbm_u340e_schedule_secondary_done(schedule) == RBM_U340E_SECONDARY_RUN_MAIN) {
                return;
            }
        }
    } while (release <= RBM_U340E_RELEASE_SECONDARY);
    assert(0 && "unexpected scheduling state");
}

static void check_range_main(RbmU340eScheduler *schedule, RbmU340eRuntime *runtime,
                             RbmU340eRangeState *range, RbmU340eRangeInputs *input,
                             FactoryGearState *work, FactoryGearWrites *writes)
{
    release_range_main(schedule, runtime, range, input);
    assert(rbm_u340e_runtime_main_range(runtime, range, input, work));
    assert(rbm_u340e_runtime_gears_outputs(runtime, work, writes));
    assert(factory_hydraulics_control_main(&runtime->gp));
    assert(rbm_u340e_runtime_main_range_complete(runtime));
    assert(rbm_u340e_schedule_main_done(schedule));
}

static void check_selected_solenoids(const FactoryGearWrites *writes, unsigned s1, unsigned s2)
{
    assert(writes->count == 2);
    assert(writes->writes[0].channel == 0 && writes->writes[0].value == s1);
    assert(writes->writes[1].channel == 1 && writes->writes[1].value == s2);
}

static void check_standstill_drive(uint16_t neutral_adc, uint8_t neutral_selector)
{
    RbmU340eScheduler schedule = {0};
    RbmU340eRuntime runtime = {0};
    RbmU340eRangeState range = {0};
    FactoryHydraulics gp = {0};
    const FactoryGearState start = {
        .driver5302 = {1, 1}, .u7184 = 20000, .u7164 = 26000, .u7186 = 3072,
        .periods = {65535, 65535, 65535, 65535, 65535, 65535},
    };
    FactoryGearState work;
    FactoryGearWrites writes;
    RbmU340eSelectorInput adc = {0};
    RbmU340eRangeInputs input = {.range_5722 = 5};
    assert(factory_hydraulics_set(&gp, -7184, 2, start.u7184));
    assert(factory_hydraulics_set(&gp, -7164, 2, start.u7164));
    assert(factory_hydraulics_set(&gp, -7186, 2, start.u7186));
    assert(factory_hydraulics_set(&gp, -8310, 2, 32767u));
    assert(factory_hydraulics_set(&gp, -8302, 2, 32767u));
    assert(factory_hydraulics_set(&gp, -8272, 2, 512u));
    assert(rbm_u340e_runtime_init(&runtime, &start, &gp));
    rbm_u340e_schedule_finish_init(&schedule);

    for (unsigned i = 0; i < 4; ++i) {
        input.selector = rbm_u340e_selector_sample(&adc, neutral_adc);
    }
    assert(input.selector == neutral_selector);
    check_range_main(&schedule, &runtime, &range, &input, &work, &writes);
    assert(input.request_1120 == 0x11u);
    assert(gp_value(&runtime.gp, -4844, 1) & 1u);
    assert(!(gp_value(&runtime.gp, -4830, 1) & 1u));

    for (unsigned i = 0; i < 4; ++i) {
        input.selector = rbm_u340e_selector_sample(&adc, 500);
    }
    assert(input.selector == RBM_U340E_SELECTOR_D);
    input.range_5722 = 1;
    check_range_main(&schedule, &runtime, &range, &input, &work, &writes);
    assert(input.request_1120 == 0x33u);
    assert(!(gp_value(&runtime.gp, -4844, 1) & 1u));
    assert(gp_value(&runtime.gp, -4830, 1) & 1u);
    assert(gp_value(&runtime.gp, -7134, 2) > 0);
    assert(work.b4852 == 0 && work.b4848 == 1);
    check_selected_solenoids(&writes, 1, 0);

    const uint8_t valid_drive = input.selector;
    input.selector = rbm_u340e_selector_sample(&adc, UINT16_MAX);
    const RbmU340eRuntime before_fault = runtime;
    const RbmU340eRangeState range_before_fault = range;
    assert(!rbm_u340e_range_fast(&range, &input));
    assert(!rbm_u340e_runtime_main_range(&runtime, &range, &input, &work));
    assert(memcmp(&before_fault, &runtime, sizeof runtime) == 0);
    assert(memcmp(&range_before_fault, &range, sizeof range) == 0);
    for (unsigned i = 0; i < 4; ++i) {
        input.selector = rbm_u340e_selector_sample(&adc, 500);
    }
    assert(input.selector == valid_drive);

    unsigned elapsed_main = 0;
    while (work.b4848 != 0 && elapsed_main < 255u) {
        check_range_main(&schedule, &runtime, &range, &input, &work, &writes);
        ++elapsed_main;
    }
    assert(elapsed_main > 0 && work.b4852 == 0 && work.b4848 == 0);
    check_selected_solenoids(&writes, 1, 1);

    /* Replay a plausible increasing donor speed observation with no imposed
     * current or requested gear. The stock request maps decide the change. */
    assert(factory_hydraulics_set(&runtime.gp, -4548, 1, 22));
    assert(factory_hydraulics_set(&runtime.gp, -4549, 1, 22));
    assert(factory_hydraulics_set(&runtime.gp, -7154, 2, 6400));
    for (unsigned i = 0; work.b4848 == 0 && i < 255u; ++i) {
        check_range_main(&schedule, &runtime, &range, &input, &work, &writes);
    }
    assert(work.b4852 == 1 && work.b4848 == 1);
    check_selected_solenoids(&writes, 1, 0);
}

static void check_schedule_nominal(void)
{
    const RbmU340eRelease expected[] = {
        RBM_U340E_RELEASE_NONE, RBM_U340E_RELEASE_NONE, RBM_U340E_RELEASE_FAST, RBM_U340E_RELEASE_NONE,
        RBM_U340E_RELEASE_SECONDARY, RBM_U340E_RELEASE_NONE, RBM_U340E_RELEASE_FAST, RBM_U340E_RELEASE_NONE,
        RBM_U340E_RELEASE_NONE, RBM_U340E_RELEASE_NONE, RBM_U340E_RELEASE_FAST, RBM_U340E_RELEASE_NONE,
        RBM_U340E_RELEASE_SECONDARY, RBM_U340E_RELEASE_NONE, RBM_U340E_RELEASE_FAST, RBM_U340E_RELEASE_NONE,
    };
    RbmU340eScheduler schedule = {0};
    FactoryHydraulics gp = {0};
    assert(rbm_u340e_schedule_timer_irq(&schedule) == RBM_U340E_IRQ_BEFORE_INIT);
    assert(schedule.irq_count == 1u && schedule.producer_count == 0u);
    assert(rbm_u340e_schedule_producer_publish(&schedule) == RBM_U340E_RELEASE_INVALID);
    rbm_u340e_schedule_finish_init(&schedule);
    unsigned main_calls = 0;

    for (unsigned i = 0; i < sizeof expected / sizeof expected[0]; ++i) {
        assert(publish_tick(&schedule) == expected[i]);
        if (expected[i] == RBM_U340E_RELEASE_FAST) {
            assert(rbm_u340e_schedule_fast_claim(&schedule));
            assert(rbm_u340e_schedule_fast_begin(&schedule, &gp));
            assert(rbm_u340e_schedule_fast_end(&schedule, &gp));
            assert(rbm_u340e_schedule_fast_done(&schedule));
        } else if (expected[i] == RBM_U340E_RELEASE_SECONDARY) {
            assert(!rbm_u340e_schedule_main_done(&schedule));
            assert(rbm_u340e_schedule_secondary_claim(&schedule));
            const RbmU340eSecondary done = rbm_u340e_schedule_secondary_done(&schedule);
            if (i == 4u) {
                assert(done == RBM_U340E_SECONDARY_RUN_MAIN && schedule.secondary_count == 0u);
                assert(rbm_u340e_schedule_main_done(&schedule));
                ++main_calls;
            } else {
                assert(done == RBM_U340E_SECONDARY_DONE);
            }
        }
    }
    assert(schedule.irq_count == 17u && schedule.producer_count == 16u);
    assert(schedule.fast_count == 4u && schedule.secondary_count == 2u && main_calls == 1u);
    assert(gp_value(&gp, 1060, 1u) == 4u);
}

static void check_fast_schedule(void)
{
    RbmU340eScheduler schedule = {.producer_count = 2u, .fast_count = UINT16_MAX};
    FactoryHydraulics gp = {0};
    assert(factory_hydraulics_set(&gp, 1060, 1u, 255u));
    assert(factory_hydraulics_set(&gp, -4816, 1u, 253u));
    assert(factory_hydraulics_set(&gp, -4771, 1u, 21u));
    assert(factory_hydraulics_set(&gp, -4619, 1u, 35u));

    rbm_u340e_schedule_finish_init(&schedule);
    assert(!rbm_u340e_schedule_fast_begin(&schedule, &gp));
    assert(!rbm_u340e_schedule_fast_end(&schedule, &gp));
    assert(publish_tick(&schedule) == RBM_U340E_RELEASE_FAST);
    while (schedule.producer_count < 6u) {
        (void)publish_tick(&schedule);
    }
    assert(publish_tick(&schedule) == RBM_U340E_RELEASE_FAST_COALESCED);
    assert(rbm_u340e_schedule_fast_claim(&schedule));
    assert(!rbm_u340e_schedule_fast_done(&schedule));
    assert(rbm_u340e_schedule_fast_begin(&schedule, &gp));
    assert(!rbm_u340e_schedule_fast_begin(&schedule, &gp));
    assert(gp_value(&gp, 1060, 1u) == 255u);
    assert(gp_value(&gp, -4816, 1u) == 254u);
    assert(gp_value(&gp, -4771, 1u) == 21u);
    assert(gp_value(&gp, -4619, 1u) == 35u);
    while (schedule.producer_count < 10u) {
        (void)publish_tick(&schedule);
    }
    assert(publish_tick(&schedule) == RBM_U340E_RELEASE_FAST);
    while (schedule.producer_count < 14u) {
        (void)publish_tick(&schedule);
    }
    assert(publish_tick(&schedule) == RBM_U340E_RELEASE_FAST_COALESCED);
    assert(!rbm_u340e_schedule_fast_claim(&schedule));

    /* Toyota writes the phase saved at 05425C plus one at 054348. */
    assert(factory_hydraulics_set(&gp, 1060, 1u, 17u));
    assert(rbm_u340e_schedule_fast_end(&schedule, &gp));
    assert(!rbm_u340e_schedule_fast_end(&schedule, &gp));
    assert(gp_value(&gp, 1060, 1u) == 0u);
    assert(schedule.fast_count == UINT16_MAX && schedule.fast_pending);
    assert(rbm_u340e_schedule_fast_done(&schedule));
    assert(schedule.fast_count == 0u);
    assert(rbm_u340e_schedule_fast_claim(&schedule));
    assert(!schedule.fast_pending);
    assert(rbm_u340e_schedule_fast_begin(&schedule, &gp));
    assert(gp_value(&gp, -4816, 1u) == 255u);
    assert(gp_value(&gp, -4771, 1u) == 22u);
}

static void check_secondary_and_producer_overrun(void)
{
    RbmU340eScheduler schedule = {.irq_count = UINT16_MAX, .producer_count = UINT16_MAX};
    rbm_u340e_schedule_finish_init(&schedule);
    assert(publish_tick(&schedule) == RBM_U340E_RELEASE_NONE);
    assert(schedule.irq_count == 0u && schedule.producer_count == 0u);
    for (unsigned i = 0; i <= 36u; ++i) {
        const RbmU340eRelease released = publish_tick(&schedule);
        if (i == 4u || i == 36u) {
            assert(released == RBM_U340E_RELEASE_SECONDARY);
        } else if (i == 12u || i == 20u || i == 28u) {
            assert(released == RBM_U340E_RELEASE_SECONDARY_DROPPED);
        }
        if (i == 12u) {
            assert(rbm_u340e_schedule_secondary_claim(&schedule));
        } else if (i == 20u) {
            assert(rbm_u340e_schedule_secondary_done(&schedule) == RBM_U340E_SECONDARY_RUN_MAIN);
            assert(schedule.secondary_count == 0u);
            assert(!rbm_u340e_schedule_secondary_done(&schedule));
        } else if (i == 28u) {
            assert(rbm_u340e_schedule_main_done(&schedule));
        } else if (i == 36u) {
            assert(rbm_u340e_schedule_secondary_claim(&schedule));
            assert(rbm_u340e_schedule_secondary_done(&schedule) == RBM_U340E_SECONDARY_DONE);
        }
    }
    assert(schedule.secondary_count == 2u);

    /* IRQ while task 2 is published but before termination is still late. */
    assert(rbm_u340e_schedule_timer_irq(&schedule) == RBM_U340E_IRQ_PRODUCER);
    assert(!rbm_u340e_schedule_producer_done(&schedule));
    assert(rbm_u340e_schedule_producer_publish(&schedule) == RBM_U340E_RELEASE_NONE);
    assert(rbm_u340e_schedule_producer_publish(&schedule) == RBM_U340E_RELEASE_INVALID);
    assert(rbm_u340e_schedule_timer_irq(&schedule) == RBM_U340E_IRQ_PRODUCER_OVERRUN);
    const uint16_t halted_count = schedule.irq_count;
    assert(!rbm_u340e_schedule_producer_done(&schedule));
    assert(!rbm_u340e_schedule_fast_claim(&schedule));
    assert(rbm_u340e_schedule_timer_irq(&schedule) == RBM_U340E_IRQ_PRODUCER_OVERRUN);
    assert(schedule.irq_count == halted_count);
}

void rbm_test_runtime(void)
{
    check_initialization();
    check_compact_storage();
    check_workspace_overlap();
    check_live_stages();
    check_engine_main_publications();
    check_secondary_load_publication();
    check_standstill_drive(925, RBM_U340E_SELECTOR_P);
    check_standstill_drive(670, RBM_U340E_SELECTOR_N);
    check_schedule_nominal();
    check_fast_schedule();
    check_secondary_and_producer_overrun();
#ifndef RBM_TEST_QUIET
    puts("Toyota GP runtime: typed shared state, FAST and MAIN handoff, and rollback passed.");
    puts("Toyota MAIN engine inputs: qualified source, ECT/RPM publication, and fallback passed.");
    puts("Toyota 05518C: SECONDARY load qualifiers, hysteresis, clamp, fallback and MAIN handoff passed.");
    puts("Toyota S01 range: P/N to warm low-load D, standstill fill, S1/S2 and first upshift passed.");
    puts("Toyota scheduler: event release, FAST phase latch, busy drop and rollover passed.");
#endif
}

#ifdef RBM_TEST_RUNTIME_STANDALONE
int main(void)
{
    rbm_test_runtime();
    return 0;
}
#endif
