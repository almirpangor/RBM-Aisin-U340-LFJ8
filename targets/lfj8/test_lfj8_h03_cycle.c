#undef NDEBUG
#include <assert.h>
#include <stdbool.h>
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

static void check_event_gap(Lfj8H03Cycle *cycle, RbmU340eRuntime *runtime,
                            Lfj8H03CycleInput input, Lfj8H03CycleWorkspace *work)
{
    const RbmU340eRuntime last_good = *runtime;
    const uint16_t ticks = cycle->scheduler.producer_count;
    Lfj8H03MainResult result;
    assert(lfj8_h03_cycle_tick(cycle, runtime, &input, work, &result) == LFJ8_H03_CYCLE_NO_MAIN);
    assert(!result.valid && cycle->scheduler.producer_count == ticks);
    input.event += 2u;
    assert(lfj8_h03_cycle_tick(cycle, runtime, &input, work, &result) == LFJ8_H03_CYCLE_FAULT);
    assert(cycle->faulted && !result.valid && !result.shift.count);
    assert(memcmp(runtime, &last_good, sizeof last_good) == 0);
}

static void test_range(uint8_t initial_selector, uint8_t forward_selector,
                       uint8_t expected_range_flags, uint8_t expected_gear)
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
    input.selector = forward_selector;
    next_main(&cycle, &runtime, &input, &work, &result);
    assert((read_gp(&runtime, -7252, 1u) & 6u) == expected_range_flags);
    assert((read_gp(&runtime, -4845, 1u) & 6u) == expected_range_flags);
    assert(read_gp(&runtime, -4830, 1u) & 1u);
    assert(read_gp(&runtime, -7134, 2u) > 0u);
    check_shift(&result, 1u, forward_selector == RBM_U340E_SELECTOR_L);
    for (unsigned i = 0; result.gear_4848 != 0u && i < 255u; ++i) {
        next_main(&cycle, &runtime, &input, &work, &result);
    }
    assert(result.gear_4852 == 0u && result.gear_4848 == 0u);
    check_shift(&result, 1u, 1u);

    assert(factory_hydraulics_set(&runtime.gp, -4548, 1u, 22u));
    assert(factory_hydraulics_set(&runtime.gp, -4549, 1u, 22u));
    assert(factory_hydraulics_set(&runtime.gp, -7154, 2u, 6400u));
    for (unsigned i = 0; i < 255u; ++i) {
        next_main(&cycle, &runtime, &input, &work, &result);
        if (expected_gear == 0u) {
            assert(result.gear_4852 == 0u && result.gear_4848 == 0u);
        } else if (result.gear_4848 == expected_gear) {
            break;
        }
    }
    assert(result.gear_4852 == expected_gear && result.gear_4848 == expected_gear);
    check_shift(&result, 1u, expected_gear == 0u);

    check_event_gap(&cycle, &runtime, input, &work);
}

static void test_speed_map(uint8_t coolant, bool cold)
{
    /* At zero load the S01 bank at 0x1078 requests up at 20/34/64 and
     * down below 48/20/18. The stimulus uses Toyota raw units only. */
    static const struct {
        uint8_t speed;
        uint8_t gear[2];
        uint8_t shift_main[2]; /* 1-based MAIN call, zero if no shift. */
    } steps[] = {
        {19, {1, 1}, { 0,  0}}, {20, {2, 2}, {10, 10}},
        {33, {2, 2}, { 0,  0}}, {34, {3, 3}, {10, 10}},
        {63, {3, 3}, { 0,  0}}, {64, {4, 3}, {20,  0}},
        {48, {4, 3}, { 0,  0}}, {47, {3, 3}, { 1,  0}},
        {20, {3, 3}, { 0,  0}}, {19, {2, 2}, { 1,  1}},
        {18, {2, 2}, { 0,  0}}, {17, {1, 1}, { 1,  1}},
    };
    RbmU340eRuntime runtime = {0};
    Lfj8H03Cycle cycle;
    Lfj8H03CycleWorkspace work;
    Lfj8H03MainResult result;
    const RbmU340eRangeState range = {0};
    Lfj8H03CycleInput input = {
        .engine = {.fa62 = 9600, .f9b8 = coolant, .coherent = 1},
        .selector = RBM_U340E_SELECTOR_N, .range_5722 = 5u, .qualified = 1u,
    };
    clear_seed(&runtime);
    assert(lfj8_h03_cycle_init(&cycle, &range, 0u));
    next_main(&cycle, &runtime, &input, &work, &result);
    next_main(&cycle, &runtime, &input, &work, &result);
    input.selector = RBM_U340E_SELECTOR_D;
    input.range_5722 = 1u;
    assert(factory_hydraulics_set(&runtime.gp, -7154, 2u, 6400u));
    for (unsigned call = 0; call < 130u; ++call) {
        next_main(&cycle, &runtime, &input, &work, &result);
    }
    assert(result.gear_4852 == 0u && result.gear_4848 == 0u);

    unsigned previous = 1u;
    for (size_t i = 0; i < sizeof steps / sizeof steps[0]; ++i) {
        const unsigned speed = steps[i].speed;
        const unsigned target = steps[i].gear[cold];
        const unsigned transition = steps[i].shift_main[cold];
        assert(factory_hydraulics_set(&runtime.gp, -4548, 1u, speed));
        assert(factory_hydraulics_set(&runtime.gp, -4549, 1u, speed));
        for (unsigned call = 1; call <= 24u; ++call) {
            next_main(&cycle, &runtime, &input, &work, &result);
            const unsigned gear = call < transition ? previous : target;
            assert(read_gp(&runtime, -7202, 2u) == 0u);
            assert(!(read_gp(&runtime, -4846, 1u) & 32u));
            assert(read_gp(&runtime, -4854, 1u) == target - 1u);
            assert(result.gear_4852 == gear - 1u && result.gear_4848 == gear - 1u);
            assert(!!(read_gp(&runtime, -4838, 1u) & 2u) == (call == transition));
            check_shift(&result, gear <= 2u, gear == 1u || gear == 4u);
            if (speed == 64u && call == 1u) {
                assert(!!(read_gp(&runtime, -4835, 1u) & 32u) == cold);
                if (!cold) {
                    /* Branch from a pending 3->4, then continue the good trace. */
                    Lfj8H03Cycle interrupted = cycle;
                    RbmU340eRuntime interrupted_runtime = runtime;
                    check_event_gap(&interrupted, &interrupted_runtime, input, &work);
                }
            }
        }
        previous = target;
    }
}

int main(void)
{
    test_range(RBM_U340E_SELECTOR_P, RBM_U340E_SELECTOR_D, 0u, 1u);
    test_range(RBM_U340E_SELECTOR_N, RBM_U340E_SELECTOR_D, 0u, 1u);
    test_range(RBM_U340E_SELECTOR_N, RBM_U340E_SELECTOR_2, 2u, 1u);
    test_range(RBM_U340E_SELECTOR_N, RBM_U340E_SELECTOR_L, 4u, 0u);
    puts("H03 Toyota cycle: P/N to D, 1->2, ranges 2/L, rollover and lost event passed.");
    test_speed_map(137u, false);
    test_speed_map(100u, true);
    puts("H03 Toyota cycle: two 12-point D traces, S1/S2, cold fourth-gear inhibit and pending-shift loss passed.");
    return 0;
}
