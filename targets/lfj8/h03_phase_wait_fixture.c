/* Simulator state only. The clock and OEM phase flag are driven by the test. */
#include "lfj8_h03_takeover.h"

enum {
    READY = 0,
    DELAYED = 1,
    STALLED = 2,
    START = 100,
    RELEASE_AT = 108,
    LAST_VALID = 112,
    LOCK_TOKEN = 0x37,
};

static volatile uint8_t *const oem_flag = (volatile uint8_t *)0x804ade;
static volatile Lfj8H03PhaseClock phase;
static uint32_t now;
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
    return now;
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
    lfj8_h03_phase_clock_release(&phase, now);
    *oem_flag = 1;
}

int fixture_init(void)
{
    if (!lfj8_h03_phase_clock_init(&phase, START, 8, LAST_VALID - START, 2)) {
        return 0;
    }
    now = SCENARIO == STALLED ? LAST_VALID - 3 : RELEASE_AT - 3;
    if (SCENARIO == READY) {
        now = RELEASE_AT;
        publish();
    }
    return 1;
}

int fixture_poll(void)
{
    ++checks;
    if (SCENARIO != READY) {
        ++now;
        if (now == RELEASE_AT || (SCENARIO == STALLED && now == LAST_VALID + 2)) {
            publish();
        }
    }

    const Lfj8H03PhaseResult result = lfj8_h03_takeover_check_phase(&state);
    if (invalid || locked || phase.consumed != 0) {
        return 0;
    }
    if (SCENARIO == STALLED && now > LAST_VALID) {
        return result == LFJ8_H03_PHASE_FAULT && phase.faulted &&
            !state.pending && inhibits == now - LAST_VALID;
    }
    const Lfj8H03PhaseResult expected = *oem_flag ? LFJ8_H03_PHASE_EVENT : LFJ8_H03_PHASE_WAIT;
    return result == expected && state.pending && !inhibits;
}

int fixture_finish(void)
{
    if (*oem_flag || invalid || locked) {
        return 0;
    }
    if (SCENARIO == STALLED) {
        return checks == 5 && inhibits == 2 && phase.faulted &&
            phase.latest.sequence == 0 && !state.pending;
    }

    Lfj8H03PhaseEvent event;
    return checks == (SCENARIO == READY ? 1u : 3u) &&
        lfj8_h03_takeover_take_phase(&state, &event) == LFJ8_H03_PHASE_EVENT &&
        event.sequence == 1 && event.released_at == RELEASE_AT &&
        !invalid && !locked && !inhibits;
}
