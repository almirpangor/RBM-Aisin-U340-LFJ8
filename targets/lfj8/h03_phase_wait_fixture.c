/* Simulator state only. The clock and OEM phase flag are driven by the test. */
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_takeover.h"

enum {
    READY = 0,
    DELAYED = 1,
    STALLED = 2,
    EARLY_FLAG = 3,
    EARLY_RELEASE_AGE = 7,
    RELEASE_AGE = 8,
    LAST_VALID_AGE = 12,
    POLL_INTERVAL = 2,
    PSW_INTERRUPT_ENABLE = 0x40,
};

static volatile uint8_t *const oem_flag = (volatile uint8_t *)0x804ade;
static volatile Lfj8H03PhaseClock phase;
/* The simulator drives the RAM shadow at the real H03 clock address. */
static volatile uint32_t *const timer_shadow = (volatile uint32_t *)0x8003e0;
static const uint32_t origin = SCENARIO == DELAYED ? UINT32_MAX - 5u : 100u;
static uint32_t last_check;
static unsigned expected_checks;
static unsigned checks;
static unsigned inhibits;
static int invalid;

static int interrupts_enabled(void)
{
    uint32_t psw;
    __asm__ volatile ("mvfc %0,psw" : "=r"(psw) : : "memory");
    return (psw & PSW_INTERRUPT_ENABLE) != 0;
}

/* Debugger breakpoints in the simulator can enter with IE clear. Set the
 * fixture's starting state before calling the real critical section. */
static void enable_fixture_interrupts(void)
{
    uint32_t psw;
    __asm__ volatile ("mvfc %0,psw\n\tor3 %0,%0,#0x40\n\tmvtc %0,psw"
                      : "=&r"(psw) : : "memory", "cc");
}

static uint32_t ticks(void *context)
{
    invalid |= interrupts_enabled();
    return lfj8_h03_tml0ct_m32r(context);
}

static void inhibit(void *context)
{
    (void)context;
    invalid |= interrupts_enabled();
    ++inhibits;
}

static const Lfj8H03TakeoverOps ops = {
    .io = &lfj8_h03_mmio, .clock_ticks = ticks, .inhibit = inhibit, .phase_clock = &phase,
};
/* Begin with a staged command. Its prepare/apply path has separate tests. */
static Lfj8H03Takeover state = {.ops = &ops, .pending = 1};

static void publish(void)
{
    lfj8_h03_phase_clock_release(&phase, lfj8_h03_tml0ct_m32r(0));
    *oem_flag = 1;
}

int fixture_init(void)
{
    if (!lfj8_h03_phase_clock_init(&phase, origin, 8, LAST_VALID_AGE, 2)) {
        return 0;
    }
    if (SCENARIO == READY) {
        *timer_shadow = origin + RELEASE_AGE;
        expected_checks = 1;
        publish();
    } else if (SCENARIO == STALLED) {
        *timer_shadow = origin + 6u;
        expected_checks = 6;
    } else if (SCENARIO == EARLY_FLAG) {
        *timer_shadow = origin + EARLY_RELEASE_AGE - 1u;
        expected_checks = 2;
    } else {
        *timer_shadow = origin + 4u;
        expected_checks = 3;
    }
    return 1;
}

int fixture_poll(void)
{
    enable_fixture_interrupts();
    if (!interrupts_enabled()) {
        return 0;
    }
    const uint32_t now = lfj8_h03_tml0ct_m32r(0);
    const uint32_t age = now - origin;
    const int early_flag = SCENARIO == EARLY_FLAG && *oem_flag;
    if (checks && now - last_check != (early_flag ? 1u : POLL_INTERVAL)) {
        return 0;
    }
    ++checks;
    last_check = now;
    if ((SCENARIO == DELAYED && age == RELEASE_AGE) || early_flag) {
        publish();
    } else if (SCENARIO == STALLED && age == LAST_VALID_AGE + 2u * POLL_INTERVAL) {
        /* This is the first published flag since init. Revocation was due
         * two ticks earlier, with the foreground still in the wait loop. */
        if (!phase.faulted || state.pending || inhibits != 1) {
            return 0;
        }
        publish();
    }

    const Lfj8H03PhaseResult result = lfj8_h03_takeover_check_phase(&state);
    if (invalid || !interrupts_enabled() || phase.consumed != 0) {
        return 0;
    }
    if (SCENARIO == STALLED && age > LAST_VALID_AGE) {
        return result == LFJ8_H03_PHASE_FAULT && phase.faulted &&
            !state.pending && inhibits == (age - LAST_VALID_AGE) / POLL_INTERVAL;
    }
    const Lfj8H03PhaseResult expected = *oem_flag ? LFJ8_H03_PHASE_EVENT : LFJ8_H03_PHASE_WAIT;
    return result == expected && state.pending && !inhibits;
}

int fixture_finish(void)
{
    enable_fixture_interrupts();
    if (*oem_flag || invalid || !interrupts_enabled() || checks != expected_checks) {
        return 0;
    }
    if (SCENARIO == STALLED) {
        return inhibits == 2 && phase.faulted &&
            phase.latest.sequence == 0 && !state.pending;
    }

    const uint32_t release_age = SCENARIO == EARLY_FLAG ? EARLY_RELEASE_AGE : RELEASE_AGE;
    Lfj8H03PhaseEvent event;
    return lfj8_h03_takeover_take_phase(&state, &event) == LFJ8_H03_PHASE_EVENT &&
        event.sequence == 1 && event.released_at == origin + release_age &&
        !invalid && interrupts_enabled() && !inhibits;
}
