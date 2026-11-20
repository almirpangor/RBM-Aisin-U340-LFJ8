#include "rbm_u340e_runtime.h"
#include "rbm_u340e_scheduler.h"

#undef NDEBUG
#include <assert.h>
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
    assert(!rbm_u340e_runtime_snapshot_gears(&runtime, &runtime.gear_state));
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
    assert(memcmp(&runtime.gp, &committed.gp, sizeof runtime.gp) == 0);
    assert(rbm_u340e_runtime_snapshot_gears(&runtime, &gear));
    assert(gear.driver5302[1] == 1 && gear.b4841 == 0);
}

static RbmU340eRelease publish_tick(RbmU340eScheduler *schedule)
{
    assert(rbm_u340e_schedule_timer_irq(schedule) == RBM_U340E_IRQ_PRODUCER);
    const RbmU340eRelease released = rbm_u340e_schedule_producer_publish(schedule);
    assert(released != RBM_U340E_RELEASE_INVALID);
    assert(rbm_u340e_schedule_producer_done(schedule));
    return released;
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
    check_live_stages();
    check_schedule_nominal();
    check_fast_schedule();
    check_secondary_and_producer_overrun();
#ifndef RBM_TEST_QUIET
    puts("Toyota GP runtime: typed shared state, FAST and MAIN handoff, and rollback passed.");
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
