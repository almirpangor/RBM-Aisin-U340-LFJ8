/* Simulator state only. The clock and OEM phase flag are driven by the test. */
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
    LOCK_TOKEN = 0x37,
};

static volatile uint8_t *const oem_flag = (volatile uint8_t *)0x804ade;
static volatile Lfj8H03PhaseClock phase;
/* Drive the simulated free-running counter independently of the callback. */
volatile uint32_t fixture_ticks;
static const uint32_t origin = SCENARIO == DELAYED ? UINT32_MAX - 5u : 100u;
static uint32_t last_check;
static unsigned expected_checks;
static unsigned checks;
static unsigned inhibits;
static int locked;
static int invalid;

static uint32_t enter(void *context)
{
    (void)context;
    invalid |= locked;
    locked = 1;
    return LOCK_TOKEN;
}

static void leave(void *context, uint32_t saved)
{
    (void)context;
    invalid |= !locked || saved != LOCK_TOKEN;
    locked = 0;
}

static uint32_t ticks(void *context)
{
    (void)context;
    invalid |= !locked;
    return fixture_ticks;
}

static void inhibit(void *context)
{
    (void)context;
    invalid |= !locked;
    ++inhibits;
}

static const Lfj8RegisterIo io = {.enter = enter, .leave = leave};
static const Lfj8H03TakeoverOps ops = {
    .io = &io, .clock_ticks = ticks, .inhibit = inhibit, .phase_clock = &phase,
};
/* Begin with a staged command. Its prepare/apply path has separate tests. */
static Lfj8H03Takeover state = {.ops = &ops, .pending = 1};

static void publish(void)
{
    lfj8_h03_phase_clock_release(&phase, fixture_ticks);
    *oem_flag = 1;
}

int fixture_init(void)
{
    if (!lfj8_h03_phase_clock_init(&phase, origin, 8, LAST_VALID_AGE, 2)) {
        return 0;
    }
    if (SCENARIO == READY) {
        fixture_ticks = origin + RELEASE_AGE;
        expected_checks = 1;
        publish();
    } else if (SCENARIO == STALLED) {
        fixture_ticks = origin + 6u;
        expected_checks = 6;
    } else if (SCENARIO == EARLY_FLAG) {
        fixture_ticks = origin + EARLY_RELEASE_AGE - 1u;
        expected_checks = 2;
    } else {
        fixture_ticks = origin + 4u;
        expected_checks = 3;
    }
    return 1;
}

int fixture_poll(void)
{
    const uint32_t now = fixture_ticks;
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
    if (invalid || locked || phase.consumed != 0) {
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
    if (*oem_flag || invalid || locked || checks != expected_checks) {
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
        !invalid && !locked && !inhibits;
}
