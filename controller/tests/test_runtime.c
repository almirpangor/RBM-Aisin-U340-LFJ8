#include "rbm_u340e_runtime.h"

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

void rbm_test_runtime(void)
{
    check_initialization();
    check_live_stages();
#ifndef RBM_TEST_QUIET
    puts("Toyota GP runtime: typed shared state, FAST and MAIN handoff, and rollback passed.");
#endif
}

#ifdef RBM_TEST_RUNTIME_STANDALONE
int main(void)
{
    rbm_test_runtime();
    return 0;
}
#endif
