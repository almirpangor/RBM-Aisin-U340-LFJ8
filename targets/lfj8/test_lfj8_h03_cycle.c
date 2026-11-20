#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "lfj8_h03_cycle.h"
#include "rbm_u340e.h"

static uint32_t read_gp(const RbmU340eRuntime *runtime, int offset, unsigned bytes)
{
    uint32_t value;
    assert(factory_hydraulics_get(&runtime->gp, offset, bytes, &value));
    return value;
}

static void clear_seed(RbmU340eRuntime *runtime)
{
    const FactoryGearState startup = {
        .driver5302 = {1, 1}, .u7184 = 20000, .u7164 = 26000, .u7186 = 3072,
        .periods = {65535, 65535, 65535, 65535, 65535, 65535},
    };
    FactoryHydraulics gp = {0};
    assert(factory_hydraulics_set(&gp, -7184, 2u, startup.u7184));
    assert(factory_hydraulics_set(&gp, -7164, 2u, startup.u7164));
    assert(factory_hydraulics_set(&gp, -7186, 2u, startup.u7186));
    assert(rbm_u340e_runtime_init(runtime, &startup, &gp));
}

static void next_main(Lfj8H03Cycle *cycle, RbmU340eRuntime *runtime,
                      Lfj8H03CycleInput *input, Lfj8H03CycleWorkspace *work,
                      Lfj8H03MainResult *result)
{
    for (unsigned i = 0; i < 17u; ++i) {
        ++input->event;
        input->command_at += 1000u; /* Fixture time; not a hardware period. */
        const Lfj8H03CycleResult status = lfj8_h03_cycle_tick(cycle, runtime, input, work, result);
        if (status == LFJ8_H03_CYCLE_MAIN) {
            assert(result->valid == 1u && result->command_at == input->command_at);
            return;
        }
        assert(status == LFJ8_H03_CYCLE_NO_MAIN && !result->valid && !result->shift.count);
    }
    assert(0 && "MAIN did not run");
}

static void check_shift(const Lfj8H03MainResult *result, unsigned s1, unsigned s2)
{
    assert(result->shift.count == 2u);
    assert(result->shift.writes[0].channel == 0u && result->shift.writes[0].value == s1);
    assert(result->shift.writes[1].channel == 1u && result->shift.writes[1].value == s2);
}

static void test_range(uint8_t initial_selector)
{
    RbmU340eRuntime runtime = {0};
    Lfj8H03Cycle cycle;
    Lfj8H03CycleWorkspace work;
    Lfj8H03MainResult result;
    const RbmU340eRangeState range = {0};
    Lfj8H03CycleInput input = {
        .engine = {.fa62 = 9600, .f9b8 = 137, .coherent = 1},
        .command_at = UINT32_MAX - 4000u, .event = UINT32_MAX - 3u,
        .selector = initial_selector, .range_5722 = 5u, .qualified = 1u,
    };
    clear_seed(&runtime);
    assert(lfj8_h03_cycle_init(&cycle, &range, 0u));
    next_main(&cycle, &runtime, &input, &work, &result);
    assert(read_gp(&runtime, -4844, 1u) & 1u);
    assert(read_gp(&runtime, -7186, 2u) == 3072u);
    assert(read_gp(&runtime, -7164, 2u) == 32480u);
    assert((cycle.request_1120 & 3u) == 1u);
    next_main(&cycle, &runtime, &input, &work, &result);
    assert((cycle.request_1120 & 3u) == 3u && input.event < 20u);

    input.range_5722 = 1u;
    input.selector = RBM_U340E_SELECTOR_D;
    next_main(&cycle, &runtime, &input, &work, &result);
    assert(read_gp(&runtime, -4830, 1u) & 1u);
    assert(read_gp(&runtime, -7134, 2u) > 0u);
    check_shift(&result, 1u, 0u);
    for (unsigned i = 0; result.gear_4848 != 0u && i < 255u; ++i) {
        next_main(&cycle, &runtime, &input, &work, &result);
    }
    assert(result.gear_4852 == 0u && result.gear_4848 == 0u);
    check_shift(&result, 1u, 1u);

    assert(factory_hydraulics_set(&runtime.gp, -4548, 1u, 22u));
    assert(factory_hydraulics_set(&runtime.gp, -4549, 1u, 22u));
    assert(factory_hydraulics_set(&runtime.gp, -7154, 2u, 6400u));
    for (unsigned i = 0; result.gear_4848 == 0u && i < 255u; ++i) {
        next_main(&cycle, &runtime, &input, &work, &result);
    }
    assert(result.gear_4852 == 1u && result.gear_4848 == 1u);
    check_shift(&result, 1u, 0u);

    const RbmU340eRuntime last_good = runtime;
    const uint16_t ticks = cycle.scheduler.producer_count;
    assert(lfj8_h03_cycle_tick(&cycle, &runtime, &input, &work, &result) == LFJ8_H03_CYCLE_NO_MAIN);
    assert(!result.valid && cycle.scheduler.producer_count == ticks);
    input.event += 2u;
    assert(lfj8_h03_cycle_tick(&cycle, &runtime, &input, &work, &result) == LFJ8_H03_CYCLE_FAULT);
    assert(cycle.faulted && !result.valid && !result.shift.count);
    assert(memcmp(&runtime, &last_good, sizeof runtime) == 0);
}

int main(void)
{
    test_range(RBM_U340E_SELECTOR_P);
    test_range(RBM_U340E_SELECTOR_N);
    puts("H03 Toyota event and logical output cycle: P/N to D, 1->2, rollover and lost event passed.");
    return 0;
}
