#include <stdio.h>

#define RBM_H03_BENCH_TOYOTA_PERIOD_TICKS 20u
#define RBM_H03_BENCH_TOYOTA_MAX_LATENESS_TICKS 7u
#define RBM_H03_BENCH_TOYOTA_WATCHDOG_TICKS 27u
#define RBM_H03_BENCH_STARTUP_RANGE 0u
#define RBM_H03_BENCH_STARTUP_REQUEST_1120 0u
#include "bench_application_profile.h"
#include "lfj8_h03_phase_startup.h"

/* The five Toyota macros are fixture-only, and are not used by this check.
 * The four H03 phase settings come from the real application profile. */
static const Lfj8H03PhaseStartupConfig selected = RBM_H03_PROFILE_PHASE_CONFIG;

typedef struct {
    uint32_t now;
    unsigned entered;
    unsigned left;
    int lock_error;
} TestClock;

static uint8_t read8(void *context, uint32_t address)
{
    (void)context;
    (void)address;
    return 0u;
}

static uint16_t read16(void *context, uint32_t address)
{
    (void)context;
    (void)address;
    return 0u;
}

static uint32_t read32(void *context, uint32_t address)
{
    (void)context;
    (void)address;
    return 0u;
}

static void write8(void *context, uint32_t address, uint8_t value)
{
    (void)context;
    (void)address;
    (void)value;
}

static uint32_t enter(void *context)
{
    TestClock *const test = context;
    if (test->entered != test->left) {
        test->lock_error = 1;
    }
    ++test->entered;
    return 0xa5u;
}

static void leave(void *context, uint32_t saved)
{
    TestClock *const test = context;
    if (test->entered != test->left + 1u || saved != 0xa5u) {
        test->lock_error = 1;
    }
    ++test->left;
}

static uint32_t clock_ticks(void *context)
{
    TestClock *const test = context;
    if (test->entered != test->left + 1u) {
        test->lock_error = 1;
    }
    return test->now;
}

static void inhibit(void *context)
{
    /* This harness only validates phase startup and clock limits. */
    (void)context;
}

#define CHECK(test) do { \
    if (!(test)) { \
        printf("FAIL line %d: %s\n", __LINE__, #test); \
        return 1; \
    } \
} while (0)

#ifdef __m32r__
/* No constructors in this standalone M32R simulator harness. */
void __init(void) {}
#endif

int main(void)
{
    TestClock source = {.now = UINT32_MAX - 2000u};
    Lfj8H03PhaseClock phase = {.faulted = 0u};
    Lfj8H03Takeover takeover = {0};
    const Lfj8RegisterIo io = {
        .context = &source,
        .read8 = read8,
        .read16 = read16,
        .read32 = read32,
        .write8 = write8,
        .enter = enter,
        .leave = leave,
    };
    const Lfj8H03TakeoverOps ops = {
        .io = &io,
        .clock_ticks = clock_ticks,
        .inhibit = inhibit,
        .phase_clock = &phase,
    };
    const int started = lfj8_h03_phase_startup(&takeover, &ops, &selected);
    printf("PROFILE min=%lu max=%lu age=%lu command=%lu startup=%d\n",
        (unsigned long)selected.min_period_ticks, (unsigned long)selected.max_period_ticks,
        (unsigned long)selected.phase_max_age_ticks, (unsigned long)selected.command_max_age_ticks,
        started);
    CHECK(started == 1);
    CHECK(takeover.ops == &ops && takeover.max_age_ticks == 10000u);
    CHECK(phase.min_period == 4500u && phase.max_period == 5500u && phase.max_age == 4499u);
    CHECK(source.entered == source.left && !source.lock_error);

    uint32_t released = source.now + phase.min_period;
    lfj8_h03_phase_clock_release(&phase, released);
    Lfj8H03PhaseEvent event;
    CHECK(lfj8_h03_phase_clock_take(&phase, released + 4499u, &event) == LFJ8_H03_PHASE_EVENT);
    CHECK(event.released_at == released && event.sequence == 1u);
    CHECK(lfj8_h03_phase_clock_check(&phase, released + 5000u) == LFJ8_H03_PHASE_WAIT);
    CHECK(lfj8_h03_phase_clock_check(&phase, released + 5500u) == LFJ8_H03_PHASE_WAIT);

    released += 5500u;
    lfj8_h03_phase_clock_release(&phase, released);
    CHECK(lfj8_h03_phase_clock_take(&phase, released + 4500u, &event) == LFJ8_H03_PHASE_FAULT);
    CHECK(phase.faulted);

    CHECK(lfj8_h03_phase_startup(&takeover, &ops, &selected) == 1);
    released = source.now + 4500u;
    lfj8_h03_phase_clock_release(&phase, released);
    lfj8_h03_phase_clock_release(&phase, released + 4500u);
    CHECK(phase.faulted);

    const Lfj8H03PhaseStartupConfig ambiguous = {
        .min_period_ticks = selected.min_period_ticks,
        .max_period_ticks = selected.max_period_ticks,
        .phase_max_age_ticks = selected.min_period_ticks,
        .command_max_age_ticks = selected.command_max_age_ticks,
    };
    CHECK(lfj8_h03_phase_startup(&takeover, &ops, &ambiguous) == 0);
    CHECK(takeover.ops == NULL && phase.faulted);
    CHECK(source.entered == source.left && !source.lock_error);
    puts("PASS selected H03 startup, phase age, wait, rollover and backlog boundaries");
    return 0;
}



