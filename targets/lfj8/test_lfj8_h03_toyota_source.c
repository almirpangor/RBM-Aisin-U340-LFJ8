#include "lfj8_h03_toyota_source.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>

#define TML0CT (*(volatile uint32_t *)(uintptr_t)0x8003e0u)
#define OEM_PHASE (*(volatile uint8_t *)(uintptr_t)0x804adeu)

static Lfj8H03ToyotaRelease release;
static Lfj8H03Application application;
static Lfj8H03SensorSnapshot sensors = {.epoch = 7u};
static RbmU340eQualifiedLoadFeed load_sample = {.coherent = 1u};
static Lfj8H03CycleInput input;
static Lfj8H03CycleLoad load;
static uint32_t deadline;
static uint32_t captured_due;
static uint32_t capture_delay;
static unsigned captures;
static int owns_ram;
static int qualified_clock;
static int capture_ok;
static int drop_ownership_after_capture;
static int drop_clock_after_capture;

static int irq_enabled(void)
{
    uint32_t psw;
    __asm__ volatile ("mvfc %0,psw" : "=r"(psw) : : "memory");
    return (psw & 0x40u) != 0u;
}

static int ram_owned(void *context)
{
    assert(context == &owns_ram);
    assert(!irq_enabled());
    return owns_ram;
}

static int clock_ready(void *context)
{
    assert(context == &owns_ram);
    assert(!irq_enabled() && owns_ram);
    return qualified_clock;
}

static int capture(void *context, const Lfj8H03SensorSnapshot *snapshot, uint32_t due_at,
                   Lfj8H03CycleInput *out, Lfj8H03CycleLoad *out_load)
{
    assert(context == &owns_ram);
    assert(irq_enabled() && snapshot == &sensors && snapshot->epoch == 7u);
    captures++;
    captured_due = due_at;
    out->command_at = due_at - 4u;
    out->event = 777u; /* The release owner supplies the actual event number. */
    out_load->sample = &load_sample;
    out_load->now_us = TML0CT;
    TML0CT += capture_delay;
    if (drop_ownership_after_capture) {
        owns_ram = 0;
    }
    if (drop_clock_after_capture) {
        qualified_clock = 0;
    }
    return capture_ok;
}

static Lfj8H03ToyotaSource config = {
    .release = &release, .application = &application, .period_ticks = 10u,
    .max_lateness_ticks = 3u, .platform = &owns_ram, .ram_owned = ram_owned,
    .clock_ready = clock_ready, .capture = capture,
};

static const Lfj8H03ApplicationBinding binding = {
    .take_toyota = lfj8_h03_toyota_source_take,
};

static void start(uint32_t at)
{
    lfj8_h03_toyota_source_reset(&release);
    application = (Lfj8H03Application){.last_toyota_at = at, .running = 1u};
    input = (Lfj8H03CycleInput){.event = UINT32_MAX};
    deadline = UINT32_MAX;
    captures = 0u;
    capture_delay = 0u;
    drop_ownership_after_capture = 0;
    drop_clock_after_capture = 0;
    owns_ram = 1;
    qualified_clock = 1;
    capture_ok = 1;
}

static Lfj8H03ToyotaEvent poll(uint32_t at)
{
    TML0CT = at;
    const Lfj8H03ToyotaEvent result = binding.take_toyota(
        &config, &sensors, &input, &load, &deadline);
    assert(irq_enabled());
    return result;
}

int main(void)
{
    __asm__ volatile ("setpsw #0x40" ::: "memory", "cc");
    start(1000u);

    OEM_PHASE = 1u;
    assert(poll(1009u) == LFJ8_H03_TOYOTA_WAIT && !captures && deadline == UINT32_MAX);
    OEM_PHASE = 0u;
    assert(poll(1010u) == LFJ8_H03_TOYOTA_EVENT);
    assert(input.event == 0u && deadline == 1010u && captured_due == deadline);
    assert(input.command_at == 1006u && load.sample == &load_sample);
    assert(poll(1023u) == LFJ8_H03_TOYOTA_EVENT && deadline == 1020u && input.event == 1u);
    assert(poll(1023u) == LFJ8_H03_TOYOTA_WAIT && captures == 2u);
    assert(poll(1034u) == LFJ8_H03_TOYOTA_FAULT && captures == 2u);
    assert(poll(1040u) == LFJ8_H03_TOYOTA_FAULT && captures == 2u);

    start(1000u);
    assert(poll(1020u) == LFJ8_H03_TOYOTA_FAULT && !captures); /* Missed first release. */
    start(UINT32_MAX - 6u);
    assert(poll(UINT32_MAX) == LFJ8_H03_TOYOTA_WAIT);
    assert(poll(3u) == LFJ8_H03_TOYOTA_EVENT && deadline == 3u);
    release.sequence = UINT32_MAX;
    assert(poll(13u) == LFJ8_H03_TOYOTA_EVENT && input.event == 0u);

    start(1000u);
    assert(poll(1005u) == LFJ8_H03_TOYOTA_WAIT);
    assert(poll(1004u) == LFJ8_H03_TOYOTA_FAULT && !captures);
    start(1000u);
    assert(poll(UINT32_C(0x800003e8)) == LFJ8_H03_TOYOTA_FAULT && !captures);

    start(1000u);
    owns_ram = 0;
    assert(poll(1010u) == LFJ8_H03_TOYOTA_FAULT && !release.status && !captures);
    owns_ram = 1;
    application.running = 0;
    assert(poll(1010u) == LFJ8_H03_TOYOTA_FAULT && !release.status && !captures);
    application.running = 1;
    qualified_clock = 0;
    assert(poll(1010u) == LFJ8_H03_TOYOTA_FAULT && !captures);
    qualified_clock = 1;
    assert(poll(1010u) == LFJ8_H03_TOYOTA_FAULT && !captures);

    start(1000u);
    capture_ok = 0;
    assert(poll(1010u) == LFJ8_H03_TOYOTA_FAULT && deadline == UINT32_MAX && captures == 1u);
    capture_ok = 1;
    assert(poll(1020u) == LFJ8_H03_TOYOTA_FAULT && captures == 1u);

    start(1000u);
    capture_delay = 2u;
    assert(poll(1011u) == LFJ8_H03_TOYOTA_EVENT && deadline == 1010u);
    assert(poll(1012u) == LFJ8_H03_TOYOTA_FAULT && captures == 1u);
    start(1000u);
    capture_delay = 4u;
    assert(poll(1010u) == LFJ8_H03_TOYOTA_FAULT && deadline == UINT32_MAX && captures == 1u);

    start(1000u);
    drop_ownership_after_capture = 1;
    assert(poll(1010u) == LFJ8_H03_TOYOTA_FAULT && deadline == UINT32_MAX && captures == 1u);
    start(1000u);
    drop_clock_after_capture = 1;
    assert(poll(1010u) == LFJ8_H03_TOYOTA_FAULT && deadline == UINT32_MAX && captures == 1u);
    start(1000u);
    config.period_ticks = 0u;
    assert(poll(1010u) == LFJ8_H03_TOYOTA_FAULT && !release.status && !captures);
    config.period_ticks = 10u;
    config.max_lateness_ticks = 10u;
    assert(poll(1010u) == LFJ8_H03_TOYOTA_FAULT && !release.status && !captures);
    config.period_ticks = UINT32_C(0x7ffffff0);
    config.max_lateness_ticks = 16u;
    assert(poll(1010u) == LFJ8_H03_TOYOTA_FAULT && !release.status && !captures);
    assert(sizeof release == 16u);
    puts("H03 Toyota release: native TML0, fixed deadlines, faults and rollover PASS");
    return 0;
}
