#include <stdio.h>

#include "lfj8_h03_mmio.h"
#include "lfj8_h03_toyota_source.h"

static uint32_t simulated_tml;
static uint32_t simulated_capture_ticks;

static uint32_t enter(void *context)
{
    (void)context;
    return 0u;
}

static void leave(void *context, uint32_t saved)
{
    (void)context;
    (void)saved;
}

const Lfj8RegisterIo lfj8_h03_mmio = {.enter = enter, .leave = leave};

uint32_t lfj8_h03_tml0ct_m32r(void *context)
{
    (void)context;
    return simulated_tml;
}

static int qualified(void *context)
{
    (void)context;
    return 1;
}

static int capture(void *context, const Lfj8H03SensorSnapshot *sensors,
    uint32_t due_at, Lfj8H03CycleInput *input, Lfj8H03CycleLoad *load)
{
    (void)context;
    (void)sensors;
    (void)due_at;
    (void)input;
    (void)load;
    simulated_tml += simulated_capture_ticks;
    return 1;
}

static Lfj8H03ToyotaEvent take(Lfj8H03ToyotaSource *source, uint32_t *due_at)
{
    static Lfj8H03SensorSnapshot sensors;
    static Lfj8H03CycleInput input;
    static Lfj8H03CycleLoad load;
    return lfj8_h03_toyota_source_take(source, &sensors, &input, &load, due_at);
}

#define CHECK(test) do { \
    if (!(test)) { \
        printf("FAIL line %d: %s\n", __LINE__, #test); \
        return 1; \
    } \
} while (0)

#ifdef __m32r__
void __init(void) {}
#endif

int main(void)
{
    const uint32_t anchor = UINT32_MAX - 999u;
    Lfj8H03Application app = {.last_toyota_at = anchor, .running = 1u};
    Lfj8H03ToyotaRelease release = {.status = 0u};
    Lfj8H03ToyotaSource source = {
        .application = &app,
        .release = &release,
        .ram_owned = qualified,
        .clock_ready = qualified,
        .capture = capture,
    };

    /* One hypothetical Toyota event per 5000 TML0 ticks and a regular H03 poll.
     * These numbers are scheduling witnesses only, not calibrated Toyota settings. */
    source.period_ticks = 5000u;
    source.max_lateness_ticks = 4499u;
    uint32_t due = 0u;
    for (unsigned n = 1; n <= 4u; ++n) {
        simulated_tml = anchor + n * 5000u;
        CHECK(take(&source, &due) == LFJ8_H03_TOYOTA_EVENT);
        CHECK(due == simulated_tml && release.sequence == n - 1u);
    }

    /* A 5500-tick H03 publication gap is consistent with its admitted period.
     * If it recurs, equating the two clocks accumulates lateness and fails. */
    lfj8_h03_toyota_source_reset(&release);
    for (unsigned n = 1; n <= 9u; ++n) {
        simulated_tml = anchor + n * 5500u;
        const Lfj8H03ToyotaEvent event = take(&source, &due);
        CHECK(event == (n <= 8u ? LFJ8_H03_TOYOTA_EVENT : LFJ8_H03_TOYOTA_FAULT));
    }
    puts("PASS independent clock counterexample: 5000 period and 5500 polls fault on release 9");

    /* Capture completion is part of the lateness budget, even after the
     * pre-capture poll passed the deadline check. */
    source.period_ticks = 10000u;
    source.max_lateness_ticks = 5599u;
    lfj8_h03_toyota_source_reset(&release);
    simulated_capture_ticks = 100u;
    simulated_tml = anchor + 10000u + 5499u;
    CHECK(take(&source, &due) == LFJ8_H03_TOYOTA_EVENT);
    CHECK(simulated_tml - due == 5599u);
    lfj8_h03_toyota_source_reset(&release);
    simulated_capture_ticks = 101u;
    simulated_tml = anchor + 10000u + 5499u;
    CHECK(take(&source, &due) == LFJ8_H03_TOYOTA_FAULT);
    puts("PASS Toyota deadline includes capture completion, equality and one-tick overrun");
    return 0;
}

