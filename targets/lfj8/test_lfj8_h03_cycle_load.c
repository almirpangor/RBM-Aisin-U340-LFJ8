#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "lfj8_h03_cycle.h"
#include "rbm_u340e.h"

typedef struct {
    RbmU340eRuntime runtime;
    Lfj8H03Cycle cycle;
    Lfj8H03CycleWorkspace work;
    Lfj8H03CycleInput input;
    Lfj8H03MainResult result;
    RbmU340eQualifiedLoadFeed feed;
    Lfj8H03CycleLoad load;
} Fixture;

static void init(Fixture *fixture)
{
    *fixture = (Fixture){0};
    const FactoryGearState startup = {
        .driver5302 = {1, 1}, .u7184 = 20000, .u7164 = 26000, .u7186 = 3072,
        .periods = {65535, 65535, 65535, 65535, 65535, 65535},
    };
    FactoryHydraulics gp = {0};
    assert(factory_hydraulics_set(&gp, -7184, 2u, startup.u7184));
    assert(factory_hydraulics_set(&gp, -7164, 2u, startup.u7164));
    assert(factory_hydraulics_set(&gp, -7186, 2u, startup.u7186));
    assert(rbm_u340e_runtime_init(&fixture->runtime, &startup, &gp));
    assert(lfj8_h03_cycle_init(&fixture->cycle, &(RbmU340eRangeState){0}, 0u));

    fixture->input = (Lfj8H03CycleInput){
        .engine = {.fa62 = 9600, .f9b8 = 137, .coherent = 1},
        .event = UINT32_MAX - 3u, .selector = RBM_U340E_SELECTOR_N, .range_5722 = 5u, .qualified = 1u,
    };
    fixture->feed = (RbmU340eQualifiedLoadFeed){
        .gp_8270 = 79, .gp_8272 = 80, .gp_8298 = -11, .gp_8306 = INT16_MIN,
        .gp_8302 = 1024, .gp_8310 = INT16_MAX, .gp_9044 = -50, .gp_9030 = -200, .coherent = 1u,
    };
    fixture->load = (Lfj8H03CycleLoad){
        .sample = &fixture->feed, .now_us = UINT32_MAX - 4u, .max_age_us = 5u,
    };
}

static Lfj8H03CycleResult poll(Fixture *fixture)
{
    return lfj8_h03_cycle_tick_with_load(&fixture->cycle, &fixture->runtime, &fixture->input,
                                       &fixture->work, &fixture->result, fixture->load);
}

static void next_event(Fixture *fixture, uint32_t source_age, uint32_t other_age)
{
    ++fixture->input.event;
    ++fixture->load.now_us; /* A wrapping test clock in the same time domain. */
    fixture->feed.sampled_at = fixture->load.now_us - source_age;
    fixture->input.command_at = fixture->load.now_us - other_age;
}

static void next_main(Fixture *fixture, uint32_t source_age, uint32_t other_age)
{
    for (unsigned i = 0; i < 17u; ++i) {
        next_event(fixture, source_age, other_age);
        Lfj8H03CycleResult status = poll(fixture);
        if (status == LFJ8_H03_CYCLE_MAIN) {
            assert(fixture->result.valid == 1u);
            return;
        }
        assert(status == LFJ8_H03_CYCLE_NO_MAIN && !fixture->result.valid);
    }
    assert(0 && "MAIN did not run");
}

static uint32_t read_word(const Fixture *fixture, int gp)
{
    uint32_t value;
    assert(factory_hydraulics_get(&fixture->runtime.gp, gp, 2u, &value));
    return value;
}

static void check_load_used(void)
{
    Fixture fixture;
    init(&fixture);
    next_main(&fixture, 5u, 2u);
    assert(fixture.load.now_us < 17u);
    assert(fixture.result.command_at == fixture.feed.sampled_at);
    assert(read_word(&fixture, -8270) == 79u && read_word(&fixture, -8272) == 80u);
    assert(read_word(&fixture, -7202) == ((factory_load_code(79u) + 64u) & 0xff80u));
    assert(read_word(&fixture, -7200) == ((factory_load_code(80u) + 64u) & 0xff80u));

    fixture.feed.gp_8270 = 300;
    next_main(&fixture, 1u, 4u);
    assert(fixture.result.command_at == fixture.input.command_at);
    assert(read_word(&fixture, -8270) == 300u);
    assert(read_word(&fixture, -7202) == ((factory_load_code(300u) + 64u) & 0xff80u));
}

static void expect_fault(Fixture *fixture, const RbmU340eRuntime *last_runtime)
{
    const uint16_t last_tick = fixture->cycle.scheduler.producer_count;
    const uint32_t last_event = fixture->cycle.last_event;
    assert(poll(fixture) == LFJ8_H03_CYCLE_FAULT);
    assert(fixture->cycle.faulted && fixture->cycle.last_event == last_event);
    assert(fixture->cycle.scheduler.producer_count == last_tick);
    assert(!fixture->result.valid && !fixture->result.shift.count && !fixture->result.torque.active);
    assert(memcmp(&fixture->runtime, last_runtime, sizeof *last_runtime) == 0);
}

static void check_refusals(void)
{
    static const struct {
        uint32_t source_age, other_age, max_age;
        uint8_t coherent, fallback;
        bool missing;
    } cases[] = {
        {6u,         2u,         5u,                   1u, 0u, false}, /* expired */
        {UINT32_MAX, 2u,         5u,                   1u, 0u, false}, /* future load */
        {1u,         UINT32_MAX, 5u,                   1u, 0u, false}, /* future command */
        {1u,         2u,         UINT32_C(0x80000000),  1u, 0u, false}, /* ambiguous lifetime */
        {1u,         2u,         5u,                   0u, 0u, false}, /* incoherent */
        {1u,         2u,         5u,                   1u, 2u, false}, /* invalid donor mode */
        {1u,         2u,         5u,                   1u, 0u, true},  /* absent */
    };
    for (unsigned i = 0; i < sizeof cases / sizeof cases[0]; ++i) {
        Fixture fixture;
        init(&fixture);
        next_main(&fixture, 1u, 2u);
        const RbmU340eRuntime last_runtime = fixture.runtime;
        next_event(&fixture, cases[i].source_age, cases[i].other_age);
        fixture.feed.gp_8270 = 900;
        fixture.feed.coherent = cases[i].coherent;
        fixture.feed.fallback_5299_bit1 = cases[i].fallback;
        fixture.load.max_age_us = cases[i].max_age;
        if (cases[i].missing) {
            fixture.load.sample = NULL;
        }
        expect_fault(&fixture, &last_runtime);
        fixture.feed.coherent = 1u;
        fixture.feed.fallback_5299_bit1 = 0u;
        fixture.load.sample = &fixture.feed;
        fixture.load.max_age_us = 5u;
        next_event(&fixture, 1u, 2u);
        expect_fault(&fixture, &last_runtime);
    }
}

static Lfj8H03LoadEvidence make_evidence(uint32_t now_us, uint32_t generation)
{
    return (Lfj8H03LoadEvidence){
        .group = {
            [LFJ8_H03_LOAD_SECONDARY] = {now_us - 1u, generation},
            [LFJ8_H03_LOAD_MAIN] = {now_us - 3u, generation},
            [LFJ8_H03_LOAD_MODE] = {now_us - 2u, generation},
        },
        .qualified_groups = LFJ8_H03_LOAD_ALL_GROUPS,
    };
}

static void check_group_age(void)
{
    for (unsigned group = 0; group < LFJ8_H03_LOAD_GROUPS; ++group) {
        Fixture fixture;
        init(&fixture);
        Lfj8H03LoadEvidence evidence;
        fixture.load.evidence = &evidence;
        for (unsigned i = 0; i < 17u; ++i) {
            next_event(&fixture, fixture.load.max_age_us, 1u);
            evidence = make_evidence(fixture.load.now_us, fixture.load.generation);
            evidence.group[group].captured_at = fixture.feed.sampled_at;
            uint32_t oldest_us = fixture.load.now_us;
            assert(lfj8_h03_load_oldest_us(&evidence, fixture.load.generation, fixture.load.now_us,
                                           fixture.load.max_age_us, &oldest_us));
            assert(oldest_us == fixture.feed.sampled_at);
            const Lfj8H03CycleResult result = poll(&fixture);
            assert(result != LFJ8_H03_CYCLE_FAULT);
            if (result == LFJ8_H03_CYCLE_MAIN) {
                break;
            }
        }
        assert(fixture.result.valid && fixture.result.command_at == fixture.feed.sampled_at);
        assert(fixture.load.now_us < 17u);
        assert(read_word(&fixture, -8270) == 79u);
    }
}

static void check_group_refusals(void)
{
    enum { GROUP_MISSING, EXPIRED, FUTURE, OLD_GENERATION, RELABELLED, CASES };
    for (unsigned group = 0; group < LFJ8_H03_LOAD_GROUPS; ++group) {
        for (unsigned scenario = 0; scenario < CASES; ++scenario) {
            Fixture fixture;
            init(&fixture);
            next_main(&fixture, 1u, 1u);
            const RbmU340eRuntime last_runtime = fixture.runtime;
            next_event(&fixture, 4u, 1u);
            const uint32_t now = fixture.load.now_us;
            Lfj8H03LoadEvidence evidence = make_evidence(now, fixture.load.generation);
            fixture.load.evidence = &evidence;
            evidence.group[group].captured_at = now - 4u;
            fixture.feed.gp_8270 = 901;
            switch (scenario) {
            case GROUP_MISSING:
                evidence.qualified_groups &= (uint8_t)~(1u << group);
                break;
            case EXPIRED:
                evidence.group[group].captured_at = now - fixture.load.max_age_us - 1u;
                break;
            case FUTURE:
                evidence.group[group].captured_at = now + 1u;
                break;
            case OLD_GENERATION:
                evidence.group[group].generation = UINT32_MAX;
                break;
            case RELABELLED:
                fixture.feed.sampled_at = now - 1u;
                break;
            }
            expect_fault(&fixture, &last_runtime);
        }
    }
}

static void check_epoch_restart(void)
{
    Fixture fixture;
    init(&fixture);
    next_event(&fixture, 3u, 1u);
    Lfj8H03LoadEvidence evidence = make_evidence(fixture.load.now_us, UINT32_MAX);
    fixture.load.evidence = &evidence;
    const RbmU340eRuntime initial_runtime = fixture.runtime;
    expect_fault(&fixture, &initial_runtime);

    init(&fixture);
    next_event(&fixture, 3u, 1u);
    fixture.load.evidence = &evidence;
    expect_fault(&fixture, &initial_runtime); /* Same clock count, stale acquisition epoch. */

    init(&fixture);
    next_event(&fixture, 3u, 1u);
    evidence = make_evidence(fixture.load.now_us, fixture.load.generation);
    fixture.load.evidence = &evidence;
    assert(poll(&fixture) == LFJ8_H03_CYCLE_NO_MAIN && fixture.cycle.have_event);
    assert(read_word(&fixture, -8270) == 79u);
}

static void check_evidence_loss(void)
{
    for (unsigned without_load = 0; without_load <= 1u; ++without_load) {
        Fixture fixture;
        init(&fixture);
        next_event(&fixture, 3u, 1u);
        const Lfj8H03LoadEvidence evidence = make_evidence(fixture.load.now_us, fixture.load.generation);
        fixture.load.evidence = &evidence;
        assert(poll(&fixture) == LFJ8_H03_CYCLE_NO_MAIN);
        assert(fixture.cycle.require_load_evidence);

        const RbmU340eRuntime last_runtime = fixture.runtime;
        const uint32_t last_event = fixture.cycle.last_event;
        next_event(&fixture, 1u, 1u);
        fixture.feed.gp_8270 = 901;
        fixture.load.evidence = NULL;
        if (without_load) {
            assert(lfj8_h03_cycle_tick(&fixture.cycle, &fixture.runtime, &fixture.input,
                                       &fixture.work, &fixture.result) == LFJ8_H03_CYCLE_FAULT);
            assert(fixture.cycle.faulted && fixture.cycle.last_event == last_event);
            assert(!fixture.result.valid);
            assert(memcmp(&fixture.runtime, &last_runtime, sizeof last_runtime) == 0);
        } else {
            expect_fault(&fixture, &last_runtime);
        }
    }
}

static void check_event_order(void)
{
    Fixture fixture;
    init(&fixture);
    next_main(&fixture, 1u, 2u);
    const RbmU340eRuntime last_runtime = fixture.runtime;
    fixture.feed.gp_8270 = 900;
    assert(poll(&fixture) == LFJ8_H03_CYCLE_NO_MAIN && !fixture.result.valid);
    assert(memcmp(&fixture.runtime, &last_runtime, sizeof last_runtime) == 0);
    fixture.input.event += 2u;
    expect_fault(&fixture, &last_runtime);
}

int main(void)
{
    check_load_used();
    check_refusals();
    check_group_age();
    check_group_refusals();
    check_epoch_restart();
    check_evidence_loss();
    check_event_order();
    puts("H03 qualified load cycle: oldest group, expiry, epoch restart, clock wrap and event ordering PASS");
    return 0;
}
