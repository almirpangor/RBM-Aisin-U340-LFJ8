#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "factory_gears.h"
#include "rbm_u340e_hydraulic_workspace.h"
#ifdef H03_PROBE_CYCLE_ONLY
#include "lfj8_h03_cycle.h"
#endif

enum {
    BODY_WORDS = 1024,
    GUARD_WORDS = 8,
#ifdef H03_PROBE_CYCLE_ONLY
    STAGE_COUNT = 1,
#else
    STAGE_COUNT = 6,
#endif
    USER_STACK = 0x80
};

static uint32_t probe[GUARD_WORDS + BODY_WORDS + GUARD_WORDS];
static uint32_t seed;
static unsigned calls[STAGE_COUNT];
static unsigned high_water[STAGE_COUNT];

static uint32_t marker(unsigned index)
{
    return UINT32_C(0xa55a6996) ^ (UINT32_C(0x9e3779b9) * index) ^ seed;
}

uint32_t *h03_stack_probe_prepare(unsigned stage)
{
    uint32_t psw;
    __asm__ volatile ("mvfc %0,psw" : "=r"(psw));
    assert((psw & USER_STACK) == 0);
    assert(stage < STAGE_COUNT);
    ++calls[stage];
    seed += UINT32_C(0x7f4a7c15);
    for (unsigned i = 0; i < sizeof probe / sizeof probe[0]; ++i) {
        probe[i] = marker(i);
    }
    return probe + GUARD_WORDS + BODY_WORDS;
}

void h03_stack_probe_observe(unsigned stage, uintptr_t returned_spu, uintptr_t spi, uint32_t sampled_psw)
{
    const unsigned top = GUARD_WORDS + BODY_WORDS;
    assert(stage < STAGE_COUNT);
    assert(sampled_psw & USER_STACK);
    assert(returned_spu == (uintptr_t)(probe + top));
    assert(spi < (uintptr_t)probe || spi >= (uintptr_t)(probe + top + GUARD_WORDS));
    for (unsigned i = 0; i < GUARD_WORDS; ++i) {
        assert(probe[i] == marker(i));
        assert(probe[top + i] == marker(top + i));
    }
    unsigned first = GUARD_WORDS;
    while (first < top && probe[first] == marker(first)) {
        ++first;
    }
    const unsigned written = (top - first) * sizeof probe[0];
    if (written > high_water[stage]) {
        high_water[stage] = written;
    }
}

void __init(void) {}
void __fini(void) {}

#ifdef H03_PROBE_CYCLE_ONLY
int h03_stack_probe_cycle_test(void);
#else
void rbm_test_runtime(void);

/* The caller can overlay these only when its gear results have all been
 * copied out. The standstill test retains its separate gear snapshot. */
typedef union {
    FactoryGearState gear;
    FactoryHydraulics hydraulics;
} FixtureWorkspace;

int h03_stack_probe_compare_main(FactoryHydraulics *state)
{
    static FactoryHydraulics reference;
    static FixtureWorkspace work;
    reference = *state;
    const int expected = factory_hydraulics_control_main(&reference);
    const int actual = rbm_u340e_hydraulics_control_main_workspace(state, &work.hydraulics);
    assert(actual == expected);
    assert(memcmp(state, &reference, sizeof reference) == 0);
    return actual;
}

static void test_workspace_refusal(void)
{
    FactoryHydraulics state = {0};
    FactoryHydraulics before;
    /* This operand is only invalid for the torque stage. The preceding
     * hydraulic step is successful and clears bits in the working state. */
    assert(factory_hydraulics_set(&state, -4523, 1, 0xff));
    assert(factory_hydraulics_set(&state, -4841, 1, 0x0c));
    before = state;
    assert(factory_hydraulics_main(&state));
    assert(memcmp(&state, &before, sizeof state) != 0);
    state = before;
    assert(!h03_stack_probe_compare_main(&state));
    assert(memcmp(&state, &before, sizeof state) == 0);

    assert(!rbm_u340e_hydraulics_control_main_workspace(&state, &state));
    assert(!rbm_u340e_hydraulics_control_main_workspace(&state, NULL));
    assert(memcmp(&state, &before, sizeof state) == 0);
}
#endif

int main(void)
{
    uint32_t original_spi;
    uint32_t original_spu;
    __asm__ volatile ("mvfc %0,cr2\n\tmvfc %1,cr3"
                      : "=r"(original_spi), "=r"(original_spu));
#ifdef H03_PROBE_CYCLE_ONLY
    assert(h03_stack_probe_cycle_test() == 0);
#else
    rbm_test_runtime();
    test_workspace_refusal();
#endif
    uint32_t spi;
    uint32_t spu;
    __asm__ volatile ("mvfc %0,cr2\n\tmvfc %1,cr3"
                      : "=r"(spi), "=r"(spu));
    assert(spi == original_spi && spu == original_spu);
    for (unsigned stage = 0; stage < STAGE_COUNT; ++stage) {
        assert(calls[stage] != 0);
        printf("stack %u %u %u\n", stage, calls[stage], high_water[stage]);
    }
#ifdef H03_PROBE_CYCLE_ONLY
    printf("cycle_layout %u %u %u %u\n", (unsigned)sizeof(Lfj8H03Cycle),
           (unsigned)sizeof(Lfj8H03CycleWorkspace), (unsigned)sizeof(Lfj8H03CycleInput),
           (unsigned)sizeof(Lfj8H03MainResult));
#else
    printf("layout %u %u %u\n", (unsigned)sizeof(FactoryGearState),
           (unsigned)sizeof(FactoryHydraulics), (unsigned)sizeof(FixtureWorkspace));
#endif
    return 0;
}
