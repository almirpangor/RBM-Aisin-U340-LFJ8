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
                      Lfj8H03MainResult *result, const RbmU340eQualifiedLoadFeed *load)
{
    for (unsigned i = 0; i < 17u; ++i) {
        ++input->event;
        input->command_at += 1000u; /* Fixture time; not a hardware period. */
        Lfj8H03CycleResult status;
        if (load) {
            RbmU340eQualifiedLoadFeed sample = *load;
            sample.sampled_at = input->command_at;
            status = lfj8_h03_cycle_tick_with_load(cycle, runtime, input, work, result,
                (Lfj8H03CycleLoad){.sample = &sample, .now_us = input->command_at});
        } else {
            status = lfj8_h03_cycle_tick(cycle, runtime, input, work, result);
        }
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
    next_main(&cycle, &runtime, &input, &work, &result, NULL);
    assert(read_gp(&runtime, -4844, 1u) & 1u);
    assert(read_gp(&runtime, -7186, 2u) == 3072u);
    assert(read_gp(&runtime, -7164, 2u) == 32480u);
    assert((cycle.request_1120 & 3u) == 1u);
    next_main(&cycle, &runtime, &input, &work, &result, NULL);
    assert((cycle.request_1120 & 3u) == 3u && input.event < 20u);

    input.range_5722 = 1u;
    input.selector = forward_selector;
    next_main(&cycle, &runtime, &input, &work, &result, NULL);
    assert((read_gp(&runtime, -7252, 1u) & 6u) == expected_range_flags);
    assert((read_gp(&runtime, -4845, 1u) & 6u) == expected_range_flags);
    assert(read_gp(&runtime, -4830, 1u) & 1u);
    assert(read_gp(&runtime, -7134, 2u) > 0u);
    check_shift(&result, 1u, forward_selector == RBM_U340E_SELECTOR_L);
    for (unsigned i = 0; result.gear_4848 != 0u && i < 255u; ++i) {
        next_main(&cycle, &runtime, &input, &work, &result, NULL);
    }
    assert(result.gear_4852 == 0u && result.gear_4848 == 0u);
    check_shift(&result, 1u, 1u);

    assert(factory_hydraulics_set(&runtime.gp, -4548, 1u, 22u));
    assert(factory_hydraulics_set(&runtime.gp, -4549, 1u, 22u));
    assert(factory_hydraulics_set(&runtime.gp, -7154, 2u, 6400u));
    for (unsigned i = 0; i < 255u; ++i) {
        next_main(&cycle, &runtime, &input, &work, &result, NULL);
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

static void test_manual_request(void)
{
    RbmU340eRuntime runtime = {0};
    Lfj8H03Cycle cycle;
    Lfj8H03CycleWorkspace work;
    Lfj8H03MainResult result;
    const RbmU340eQualifiedLoadFeed load = {.coherent = 1u};
    Lfj8H03CycleInput input = {
        .engine = {.fa62 = 9600, .f9b8 = 137, .coherent = 1},
        .selector = RBM_U340E_SELECTOR_N, .range_5722 = 5u, .qualified = 1u,
    };
    clear_seed(&runtime);
    assert(lfj8_h03_cycle_init(&cycle, &(RbmU340eRangeState){0}, 0u));
    for (unsigned i = 0; i < 2; ++i) {
        next_main(&cycle, &runtime, &input, &work, &result, &load);
    }
    input.selector = RBM_U340E_SELECTOR_D;
    input.range_5722 = 1u;
    assert(factory_hydraulics_set(&runtime.gp, -7154, 2u, 6400u));
    for (unsigned i = 0; i < 130; ++i) {
        next_main(&cycle, &runtime, &input, &work, &result, &load);
    }
    assert(factory_hydraulics_set(&runtime.gp, -4548, 1u, 19u));
    assert(factory_hydraulics_set(&runtime.gp, -4549, 1u, 19u));
    next_main(&cycle, &runtime, &input, &work, &result, &load);
    assert(result.gear_4852 == 0u && read_gp(&runtime, -4854, 1u) == 0u);

    input.requested_gear = 2u;
    for (unsigned call = 1u; call <= 20u; ++call) {
        next_main(&cycle, &runtime, &input, &work, &result, &load);
        const unsigned index = call >= 10u;
        assert(read_gp(&runtime, -4854, 1u) == 1u);
        assert(result.gear_4852 == index && result.gear_4848 == index);
        assert(!!(read_gp(&runtime, -4838, 1u) & 2u) == (call == 10u));
        assert(read_gp(&runtime, -4851, 1u) == index);
        check_shift(&result, 1u, !index);
    }

    /* Below the S01 2->1 threshold, an authorized hold in second keeps
     * the S1/S2 command until the producer withdraws the request. */
    assert(factory_hydraulics_set(&runtime.gp, -4548, 1u, 17u));
    assert(factory_hydraulics_set(&runtime.gp, -4549, 1u, 17u));
    next_main(&cycle, &runtime, &input, &work, &result, &load);
    check_shift(&result, 1u, 0u);
    input.requested_gear = 0u;
    next_main(&cycle, &runtime, &input, &work, &result, &load);
    assert(result.gear_4852 == 0u && result.gear_4848 == 0u);
    check_shift(&result, 1u, 1u);

    /* Reverse is carried to the donor phase code in GP-7252.3. */
    assert(factory_hydraulics_set(&runtime.gp, -4548, 1u, 0u));
    assert(factory_hydraulics_set(&runtime.gp, -4549, 1u, 0u));
    input.selector = RBM_U340E_SELECTOR_N;
    input.range_5722 = 5u;
    next_main(&cycle, &runtime, &input, &work, &result, &load);
    input.selector = RBM_U340E_SELECTOR_R;
    input.range_5722 = 2u;
    next_main(&cycle, &runtime, &input, &work, &result, &load);
    assert((read_gp(&runtime, -7252, 1u) & 0x0fu) == 9u);
    assert(read_gp(&runtime, -7250, 1u) == read_gp(&runtime, -7252, 1u));

    const RbmU340eRuntime before = runtime;
    const uint16_t releases = cycle.scheduler.producer_count;
    ++input.event;
    input.requested_gear = 2u;
    assert(lfj8_h03_cycle_tick(&cycle, &runtime, &input, &work, &result) == LFJ8_H03_CYCLE_FAULT);
    assert(cycle.faulted && !result.valid && !result.shift.count);
    assert(cycle.scheduler.producer_count == releases);
    assert(memcmp(&runtime, &before, sizeof runtime) == 0);
}

typedef struct {
    int16_t load_operand;
    uint16_t expected_load;
    uint8_t thresholds[6]; /* S01 rows 0..2 up and 3..5 down, in ROM order. */
} SpeedMapProfile;

static void test_speed_map(uint8_t coolant, bool cold, const SpeedMapProfile *profile)
{
    /* Check just below and exactly at each S01 threshold. The stimulus
     * uses donor speed and load codes, with gear numbers here starting at 1. */
    static const struct {
        uint8_t threshold_row;
        bool below_threshold;
        uint8_t gear[2];
        uint8_t shift_main[2]; /* 1-based MAIN call, zero if no shift. */
    } steps[] = {
        {0, true,  {1, 1}, { 0,  0}}, {0, false, {2, 2}, {10, 10}},
        {1, true,  {2, 2}, { 0,  0}}, {1, false, {3, 3}, {10, 10}},
        {2, true,  {3, 3}, { 0,  0}}, {2, false, {4, 3}, {20,  0}},
        {5, false, {4, 3}, { 0,  0}}, {5, true,  {3, 3}, { 1,  0}},
        {4, false, {3, 3}, { 0,  0}}, {4, true,  {2, 2}, { 1,  1}},
        {3, false, {2, 2}, { 0,  0}}, {3, true,  {1, 1}, { 1,  1}},
    };
    RbmU340eRuntime runtime = {0};
    Lfj8H03Cycle cycle;
    Lfj8H03CycleWorkspace work;
    Lfj8H03MainResult result;
    const RbmU340eRangeState range = {0};
    const int16_t operand = profile->load_operand;
    const RbmU340eQualifiedLoadFeed load = {
        .gp_8270 = operand, .gp_8272 = operand, .gp_8302 = operand,
        .gp_8310 = operand, .gp_9044 = operand, .coherent = 1u,
    };
    const RbmU340eQualifiedLoadFeed *feed = operand != 0 ? &load : NULL;
    Lfj8H03CycleInput input = {
        .engine = {.fa62 = 9600, .f9b8 = coolant, .coherent = 1},
        .selector = RBM_U340E_SELECTOR_N, .range_5722 = 5u, .qualified = 1u,
    };
    clear_seed(&runtime);
    assert(lfj8_h03_cycle_init(&cycle, &range, 0u));
    next_main(&cycle, &runtime, &input, &work, &result, NULL);
    next_main(&cycle, &runtime, &input, &work, &result, NULL);
    input.selector = RBM_U340E_SELECTOR_D;
    input.range_5722 = 1u;
    assert(factory_hydraulics_set(&runtime.gp, -7154, 2u, 6400u));
    for (unsigned call = 0; call < 130u; ++call) {
        next_main(&cycle, &runtime, &input, &work, &result, NULL);
    }
    assert(result.gear_4852 == 0u && result.gear_4848 == 0u);

    unsigned previous = 1u;
    for (size_t i = 0; i < sizeof steps / sizeof steps[0]; ++i) {
        const unsigned speed = profile->thresholds[steps[i].threshold_row] - steps[i].below_threshold;
        const unsigned target = steps[i].gear[cold];
        const unsigned transition = steps[i].shift_main[cold];
        assert(factory_hydraulics_set(&runtime.gp, -4548, 1u, speed));
        assert(factory_hydraulics_set(&runtime.gp, -4549, 1u, speed));
        /* Below the warm fourth-gear threshold, request fourth explicitly
         * in the cold trace. S01 must still inhibit the transition. */
        input.requested_gear = cold && steps[i].threshold_row == 2u && steps[i].below_threshold ? 4u : 0u;
        for (unsigned call = 1; call <= 24u; ++call) {
            next_main(&cycle, &runtime, &input, &work, &result, feed);
            const unsigned gear = call < transition ? previous : target;
            assert(read_gp(&runtime, -7202, 2u) == profile->expected_load);
            assert(read_gp(&runtime, -7200, 2u) == profile->expected_load);
            assert(read_gp(&runtime, -7198, 2u) == profile->expected_load);
            if (operand != 0 && call >= 2u) {
                assert((cycle.request_1120 & 0x0fu) == 0u);
            }
            assert(!(read_gp(&runtime, -4846, 1u) & 32u));
            assert(read_gp(&runtime, -4854, 1u) == target - 1u);
            assert(result.gear_4852 == gear - 1u && result.gear_4848 == gear - 1u);
            assert(!!(read_gp(&runtime, -4838, 1u) & 2u) == (call == transition));
            check_shift(&result, gear <= 2u, gear == 1u || gear == 4u);
            if (steps[i].threshold_row == 2u && call == 1u) {
                const bool fourth_requested = !steps[i].below_threshold || input.requested_gear == 4u;
                assert(!!(read_gp(&runtime, -4835, 1u) & 32u) == (cold && fourth_requested));
                if (!cold && fourth_requested) {
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

typedef struct {
    RbmU340eRuntime runtime;
    Lfj8H03Cycle cycle;
    Lfj8H03CycleWorkspace work;
    Lfj8H03CycleInput input;
    Lfj8H03MainResult result;
    RbmU340eQualifiedLoadFeed load;
    Lfj8H03SluSnapshot sample;
    Lfj8H03SluState slu;
    Lfj8H03SluOutput output;
    uint32_t now;
} SluFixture;

static void seed_slu(SluFixture *fixture)
{
    *fixture = (SluFixture){0};
    clear_seed(&fixture->runtime);
    assert(lfj8_h03_cycle_init(&fixture->cycle, &(RbmU340eRangeState){0}, 0u));
    fixture->input = (Lfj8H03CycleInput){
        .engine = {.fa62 = 9600, .f9b8 = 137, .coherent = 1u},
        .event = UINT32_MAX - 4u, .selector = RBM_U340E_SELECTOR_D,
        .range_5722 = 1u, .qualified = 1u,
    };
    fixture->load.coherent = 1u;
    fixture->sample = (Lfj8H03SluSnapshot){
        .base_7054 = 10000u, .mode_4505 = 1u, .selector_4544 = 0xa5u,
        .flags_4828 = 0x80u, .flags_1636 = 0xa7u, .offset_7028 = -1000, .offset_7030 = 2000,
        .learning_4616 = {128}, .qualified = 1u,
    };
    fixture->now = UINT32_MAX - 4990u;
    assert(factory_hydraulics_set(&fixture->runtime.gp, -4735, 1u, 254u));
}

static void prepare_slu(SluFixture *fixture)
{
    fixture->now += 1000u;
    ++fixture->input.event;
    fixture->input.command_at = fixture->now - 10u;
    fixture->load.sampled_at = fixture->now - 20u;
    fixture->sample.event = fixture->input.event;
    fixture->sample.sampled_at = fixture->now - 40u;
}

static Lfj8H03CycleResult tick_slu(SluFixture *fixture, const Lfj8H03SluSnapshot *sample)
{
    return lfj8_h03_cycle_tick_with_slu(&fixture->cycle, &fixture->runtime,
        &fixture->input, &fixture->work, &fixture->result,
        (Lfj8H03CycleLoad){.sample = &fixture->load, .now_us = fixture->now, .max_age_us = 40u},
        (Lfj8H03CycleSlu){sample, &fixture->slu, &fixture->output});
}

static void test_slu_schedule(void)
{
    static const uint16_t pressure[] = {2560u, 23040u, 23040u, 12000u, 12800u};
    static const uint8_t timer[] = {255u, 0u, 1u, 2u, 3u};
    static const uint16_t ages_in[] = {0x0b07u, 0x1703u, 0x1704u, 0x0c07u, 0xff02u};
    static const uint16_t ages_out[] = {0x0b00u, 0x0003u, 0x0004u, 0x0c00u, 0xff00u};
    static const uint8_t flags_in[] = {0xa1u, 0xa5u, 0xa5u, 0xa1u, 0xadu};
    static const uint8_t flags_out[] = {0xa1u, 0xa5u, 0xa1u, 0xa5u, 0xadu};
    SluFixture fixture;
    seed_slu(&fixture);
    for (unsigned step = 0; step <= 36u; ++step) {
        const bool secondary = (step & 7u) == 4u;
        const unsigned index = step / 8u;
        prepare_slu(&fixture);
        if (secondary) {
            /* Donor-domain operands from the stages ahead of 05DA44. */
            assert(factory_hydraulics_set(&fixture.runtime.gp, -4852, 1u, 1u));
            assert(factory_hydraulics_set(&fixture.runtime.gp, -7200, 2u, 0u));
            assert(factory_hydraulics_set(&fixture.runtime.gp, -7184, 2u, 2560u));
            assert(factory_hydraulics_set(&fixture.runtime.gp, -4829, 1u, flags_in[index]));
            assert(factory_hydraulics_set(&fixture.runtime.gp, -4741, 2u, ages_in[index]));
            fixture.sample.mode_4505 = index == 0u ? 1u : 2u;
            fixture.sample.override_7082 = 12800u;
            fixture.sample.flags_4822 = index == 4u ? 0x80u : 0u;
            if (index == 3u) {
                fixture.sample.sampled_at = fixture.now - 10u;
            }
        }
        const uint32_t before = read_gp(&fixture.runtime, -4735, 1u);
        const uint32_t low_age = read_gp(&fixture.runtime, -4741, 1u);
        const uint32_t high_age = read_gp(&fixture.runtime, -4740, 1u);
        const unsigned phase = read_gp(&fixture.runtime, 1060, 1u);
        const Lfj8H03CycleResult result = tick_slu(&fixture, secondary ? &fixture.sample : NULL);
        assert(result == (secondary && (index & 1u) == 0u ? LFJ8_H03_CYCLE_MAIN : LFJ8_H03_CYCLE_NO_MAIN));
        if (secondary) {
            assert(fixture.output.valid && fixture.output.event == fixture.input.event);
            assert(fixture.output.command_at == (index == 3u ? fixture.load.sampled_at : fixture.sample.sampled_at));
            assert(fixture.output.result.pressure_7136 == pressure[index]);
            assert(fixture.output.result.command.selected_7246 == 25600u - pressure[index]);
            assert(fixture.output.result.command.force == (index == 4u));
            assert(fixture.output.post_reset_flags_1636 == 0xa5u &&
                   fixture.output.post_reset_offset_7028 == 0);
            assert(fixture.sample.flags_1636 == 0xa7u && fixture.sample.offset_7028 == -1000);
            assert(read_gp(&fixture.runtime, -4735, 1u) == timer[index]);
            assert(read_gp(&fixture.runtime, -4741, 2u) == ages_out[index]);
            /* MAIN also owns bit zero, independently of the SLU diagnostic bit. */
            const unsigned mask = result == LFJ8_H03_CYCLE_MAIN ? 0xfeu : 0xffu;
            assert((read_gp(&fixture.runtime, -4829, 1u) & mask) == (flags_out[index] & mask));
            assert(tick_slu(&fixture, NULL) == LFJ8_H03_CYCLE_NO_MAIN);
            assert(!fixture.output.valid && read_gp(&fixture.runtime, -4735, 1u) == timer[index]);
            assert(read_gp(&fixture.runtime, -4741, 2u) == ages_out[index]);
        } else {
            const bool advances = (step & 3u) == 2u && (phase & 1u) == 0u;
            assert(!fixture.output.valid);
            assert(read_gp(&fixture.runtime, -4735, 1u) == before + (advances && before < 255u));
            assert(read_gp(&fixture.runtime, -4741, 1u) == low_age + (advances && low_age < 255u));
            assert(read_gp(&fixture.runtime, -4740, 1u) == high_age + (advances && high_age < 255u));
        }
    }
    prepare_slu(&fixture);
    ++fixture.input.event;
    assert(tick_slu(&fixture, &fixture.sample) == LFJ8_H03_CYCLE_FAULT);
    assert(fixture.cycle.faulted && !fixture.output.valid && fixture.output.result.pressure_7136 == 0u);
    assert(read_gp(&fixture.runtime, -4735, 1u) == timer[4]);
}

static void test_slu_refusals(void)
{
    for (unsigned which = 0; which < 6u; ++which) {
        SluFixture fixture;
        seed_slu(&fixture);
        for (unsigned step = 0; step < 4u; ++step) {
            prepare_slu(&fixture);
            assert(tick_slu(&fixture, NULL) == LFJ8_H03_CYCLE_NO_MAIN);
        }
        assert(factory_hydraulics_set(&fixture.runtime.gp, -4829, 1u, 0xa5u));
        assert(factory_hydraulics_set(&fixture.runtime.gp, -4741, 2u, 0x1704u));
        prepare_slu(&fixture);
        switch (which) {
        case 1: fixture.sample.qualified = 0u; break;
        case 2: --fixture.sample.event; break;
        case 3: --fixture.sample.sampled_at; break;
        case 4: fixture.sample.sampled_at = fixture.now + 1u; break;
        case 5: fixture.input.command_at = fixture.now - 41u; break;
        default: break;
        }
        fixture.output = (Lfj8H03SluOutput){
            .valid = 1u, .result.pressure_7136 = 9999u,
            .post_reset_flags_1636 = 0xffu, .post_reset_offset_7028 = 123,
        };
        assert(tick_slu(&fixture, which ? &fixture.sample : NULL) == LFJ8_H03_CYCLE_FAULT);
        assert(fixture.cycle.faulted && !fixture.result.valid && !fixture.output.valid);
        assert(fixture.output.result.pressure_7136 == 0u && fixture.slu.previous_mode_1637 == 0u);
        assert(fixture.output.post_reset_flags_1636 == 0u && fixture.output.post_reset_offset_7028 == 0);
        assert(read_gp(&fixture.runtime, -4735, 1u) == 255u);
        assert(read_gp(&fixture.runtime, -4829, 1u) == 0xa5u);
        assert(read_gp(&fixture.runtime, -4741, 2u) == 0x1704u);
    }
}

int main(void)
{
    test_slu_schedule();
    test_slu_refusals();
    puts("SLU SECONDARY: 5 publications, reset, diagnostic gates, FAST timers and 7 refusals PASS");
    test_range(RBM_U340E_SELECTOR_P, RBM_U340E_SELECTOR_D, 0u, 1u);
    test_range(RBM_U340E_SELECTOR_N, RBM_U340E_SELECTOR_D, 0u, 1u);
    test_range(RBM_U340E_SELECTOR_N, RBM_U340E_SELECTOR_2, 2u, 1u);
    test_range(RBM_U340E_SELECTOR_N, RBM_U340E_SELECTOR_L, 4u, 0u);
    puts("H03 Toyota cycle: P/N to D, 1->2, ranges 2/L, rollover and lost event passed.");
    test_manual_request();
    puts("H03 Toyota cycle: manual 1->2, hold, withdrawal, reverse range and request refusal passed.");
    /* Thresholds decoded from the pinned S01 bank at ROM 0x1078. */
    const SpeedMapProfile unloaded = {0, 0, {20, 34, 64, 18, 20, 48}};
    const SpeedMapProfile load_20 = {2202, 5120, {37, 69, 99, 18, 27, 56}};
    const SpeedMapProfile load_50 = {5505, 12800, {62, 114, 159, 32, 64, 103}};
    test_speed_map(137u, false, &unloaded);
    test_speed_map(100u, true, &unloaded);
    puts("H03 Toyota cycle: two 12-point D traces, S1/S2, cold fourth-gear inhibit and pending-shift loss passed.");
    test_speed_map(137u, false, &load_20);
    test_speed_map(137u, false, &load_50);
    puts("H03 Toyota cycle: two loaded D maps, qualified GP feed, six shift thresholds and S1/S2 passed.");
    return 0;
}
