/* Simulator state only. The clock and OEM phase flag are driven by the test. */
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_phase_startup.h"

enum {
    READY = 0,
    DELAYED = 1,
    STALLED = 2,
    EARLY_FLAG = 3,
    COALESCED = 4,
    FROZEN_COUNTER = 5,
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

static void unexpected_hardware_action(void *context)
{
    (void)context;
    invalid = 1;
}

static int qualified(void *context)
{
    unexpected_hardware_action(context);
    return 0;
}

static void unexpected_write(void *context, uint32_t address, uint32_t value)
{
    (void)address;
    (void)value;
    unexpected_hardware_action(context);
}

static const Lfj8H03TakeoverOps ops = {
    .io = &lfj8_h03_mmio, .clock_ticks = ticks, .inhibit = inhibit, .phase_clock = &phase,
    .write32 = unexpected_write, .qualified = qualified,
    .arbitrate = unexpected_hardware_action, .apply = unexpected_hardware_action,
    .isolated_pwm_mask = LFJ8_H03_ALL_SPARE_PWM_ISOLATED,
};
static Lfj8H03Takeover state;

static int start_phase(void)
{
    Lfj8H03PhaseStartupConfig config = {8u, 16u, 2u, 16u};
    *timer_shadow = origin;
    enable_fixture_interrupts();

    /* The failed start must leave neither the IRQ publisher nor the
     * command path armed. A later qualified startup may reuse the storage. */
    if (lfj8_h03_phase_startup(&state, &ops, &config) || state.ops ||
        !phase.faulted || phase.min_period || !interrupts_enabled()) {
        return 0;
    }

    config.max_period_ticks = LAST_VALID_AGE;
    Lfj8H03TakeoverOps missing_callback = ops;
    missing_callback.inhibit = 0;
    if (lfj8_h03_phase_startup(&state, &missing_callback, &config) || state.ops ||
        !phase.faulted || phase.min_period || !interrupts_enabled()) {
        return 0;
    }

    if (!lfj8_h03_phase_startup(&state, &ops, &config) || state.ops != &ops || state.pending ||
        phase.latest.released_at != origin || phase.have_release || phase.faulted ||
        lfj8_h03_takeover_check_phase(&state) != LFJ8_H03_PHASE_WAIT || invalid || inhibits ||
        !interrupts_enabled()) {
        return 0;
    }
    /* The prepare and apply paths have separate tests. */
    state.pending = 1u;
    return 1;
}

#if NATIVE_PUBLISH
static unsigned native_releases;

void fixture_native_publish(void);

void rbm_h03_phase_release_callback(uint32_t now)
{
    const uint8_t divider = lfj8_h03_mmio.read8(0, 0x804862);
    const uint8_t count_61 = lfj8_h03_mmio.read8(0, 0x804861);
    const uint8_t count_64 = lfj8_h03_mmio.read8(0, 0x804864);
    invalid |= !*oem_flag || divider != 10 || count_61 != 6 || count_64 != 4 ||
        now != lfj8_h03_tml0ct_m32r(0);
    ++native_releases;
    lfj8_h03_phase_clock_release(&phase, now);
}
#endif

static void publish(void)
{
#if NATIVE_PUBLISH
    fixture_native_publish();
#else
    lfj8_h03_phase_clock_release(&phase, lfj8_h03_tml0ct_m32r(0));
    *oem_flag = 1;
#endif
}

int fixture_init(void)
{
    if (!start_phase()) {
        return 0;
    }
    if (SCENARIO == READY) {
        *timer_shadow = origin + RELEASE_AGE;
        expected_checks = 1;
        publish();
    } else if (SCENARIO == COALESCED) {
        *timer_shadow = origin + RELEASE_AGE;
        publish();
        *timer_shadow = origin + RELEASE_AGE + 10u;
        publish();
        expected_checks = 1;
    } else if (SCENARIO == STALLED) {
        *timer_shadow = origin + 6u;
        expected_checks = 6;
    } else if (SCENARIO == FROZEN_COUNTER) {
        *timer_shadow = origin + 6u;
        expected_checks = 2;
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
    /* Model the clock authority declining the unchanged clock once the
     * native spin bound gets the foreground back into the guard. */
    if (SCENARIO == FROZEN_COUNTER && checks == 1u) {
        if (now != last_check || *oem_flag || !state.pending || inhibits) {
            return 0;
        }
        const uint32_t saved = lfj8_h03_mmio.enter(0);
        phase.faulted = 1u;
        lfj8_h03_takeover_revoke_locked(&state);
        lfj8_h03_mmio.leave(0, saved);
        ++checks;
        *oem_flag = 1u;
        return !invalid && interrupts_enabled() && !state.pending && inhibits == 1u;
    }
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
    if (SCENARIO == COALESCED) {
        return result == LFJ8_H03_PHASE_FAULT && phase.faulted && !state.pending && inhibits == 1;
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
#if NATIVE_PUBLISH
    if (native_releases != (SCENARIO == COALESCED ? 2u : 1u)) {
        return 0;
    }
#endif
    if (SCENARIO == COALESCED) {
        return inhibits == 1 && phase.faulted && phase.latest.sequence == 1 &&
            phase.consumed == 0 && !state.pending;
    }
    if (SCENARIO == FROZEN_COUNTER) {
        return inhibits == 1 && phase.faulted && phase.consumed == 0 && !state.pending;
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
