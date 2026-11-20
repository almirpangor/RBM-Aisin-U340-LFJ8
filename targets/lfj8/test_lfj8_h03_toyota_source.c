#include "lfj8_h03_toyota_source.h"
#include "lfj8_h03_input_binding.h"
#include "lfj8_h03_mmio.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>

#define TML0CT (*(volatile uint32_t *)(uintptr_t)0x8003e0u)
#define OEM_PHASE (*(volatile uint8_t *)(uintptr_t)0x804adeu)
#define P1DATA (*(volatile uint8_t *)(uintptr_t)LFJ8_H03_P1DATA_ADDRESS)

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
    assert(irq_enabled() && snapshot == &sensors);
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

static Lfj8SelectorAdc mode_adc;
static Lfj8RangeControl mode_control;
static Lfj8ButtonFilter mode_buttons;
static Lfj8H03InputProposal mode_proposal;
static RbmU340eInput driver;
static Lfj8H03RangeInputs range;

static int read_mode(void *context, const Lfj8H03SensorSnapshot *snapshot, uint32_t due_at,
                     Lfj8H03CycleInput *out, Lfj8H03CycleLoad *out_load,
                     Lfj8H03InputSources *sources)
{
    const int ready = capture(context, snapshot, due_at, out, out_load);
    out->qualified = 1u;
    out->engine.coherent = 0u;
    out->requested_gear = 4u;
    for (unsigned i = 0; i < 4u; ++i) {
        range.range_5722[i] = (Lfj8H03RangeBit){due_at - i, snapshot->epoch, i == 0u, 1u};
    }
    range.inhibit_5250_2 = (Lfj8H03RangeBit){due_at - 2u, snapshot->epoch, 0u, 1u};
    sources->driver = &driver;
    sources->range = &range;
    return ready;
}

static const Lfj8H03RangeAgeLimits mode_limits = {{20u, 20u, 20u, 20u}, 20u};
static const Lfj8H03ButtonMap mode_pins = {{
    {LFJ8_H03_BUTTON_P1, 8u, 1u}, {LFJ8_H03_BUTTON_P1, 64u, 0u},
    {LFJ8_H03_BUTTON_P1, 32u, 0u}, {0},
}};
static const Lfj8H03InputBinding mode_input = {
    .adc = &mode_adc, .control = &mode_control, .button_filter = &mode_buttons,
    .io = &lfj8_h03_mmio, .range_limits = &mode_limits, .p1_button_map = &mode_pins,
    .manual_max_age_us = 30u,
};
static const Lfj8H03ToyotaInputCapture mode_capture = {
    .binding = &mode_input, .proposal = &mode_proposal, .platform = &owns_ram,
    .ram_owned = ram_owned, .read = read_mode,
};

static int mode_ram_owned(void *context)
{
    assert(context == &mode_capture);
    return ram_owned(mode_capture.platform);
}

static int mode_clock_ready(void *context)
{
    assert(context == &mode_capture);
    return clock_ready(mode_capture.platform);
}

static void mode_sample(uint32_t at, uint8_t port)
{
    TML0CT = at;
    P1DATA = port;
    lfj8_selector_adc_publish_h03(&mode_adc, &lfj8_h03_mmio, 500u, at);
    lfj8_h03_input_capture(&mode_input, NULL, at);
}

static void start_mode(void)
{
    static const RbmU340ePolicy policy = {
        .manual_selectors = 1u << RBM_U340E_SELECTOR_D,
        .initial_mode = RBM_U340E_TIPTRONIC, .initial_overdrive_enabled = 1u,
    };
    start(1000u);
    config.period_ticks = 10u;
    config.max_lateness_ticks = 3u;
    config.platform = (void *)&mode_capture;
    config.ram_owned = mode_ram_owned;
    config.clock_ready = mode_clock_ready;
    config.capture = lfj8_h03_input_capture_toyota;
    sensors.epoch = 7u;
    driver = (RbmU340eInput){.actual_gear = 2u, .allowed_gears = 15u};
    assert(lfj8_range_control_init(&mode_control, &policy, 25u));
    assert(lfj8_button_filter_init(&mode_buttons, 1u, 25u));
    lfj8_selector_adc_init(&mode_adc);
    for (uint32_t at = 1001u; at < 1007u; ++at) {
        mode_sample(at, 8u);
    }
    assert(poll(1010u) == LFJ8_H03_TOYOTA_EVENT && !input.requested_gear);
    mode_sample(1011u, 72u);
    mode_sample(1012u, 72u);
    assert(poll(1019u) == LFJ8_H03_TOYOTA_WAIT && !mode_control.manual_gear);
    assert(poll(1020u) == LFJ8_H03_TOYOTA_EVENT && input.event == 1u);
    assert(input.requested_gear == 3u && input.qualified && !input.engine.coherent);
    assert(input.selector == RBM_U340E_SELECTOR_D && input.command_at == 1012u);
}

static void test_mode_capture(void)
{
    start_mode();
    mode_sample(1021u, 8u);
    mode_sample(1022u, 8u);
    driver.actual_gear = 0u;
    driver.shifting = 1u;
    assert(poll(1030u) == LFJ8_H03_TOYOTA_EVENT && input.requested_gear == 3u);
    assert(!mode_proposal.driver.requested_gear && input.command_at == 1022u);
    driver.actual_gear = 3u;
    driver.shifting = 0;
    assert(poll(1040u) == LFJ8_H03_TOYOTA_EVENT && !input.requested_gear);

    start_mode();
    ++sensors.epoch;
    assert(poll(1030u) == LFJ8_H03_TOYOTA_FAULT && !input.requested_gear);
    assert(!mode_control.manual_gear && !mode_buttons.armed && deadline == 1020u);

    start_mode();
    drop_ownership_after_capture = 1;
    assert(poll(1030u) == LFJ8_H03_TOYOTA_FAULT && deadline == 1020u);
    assert(mode_control.manual_gear == 3u && mode_proposal.cycle.event == 777u);
    start_mode();
    lfj8_selector_adc_clock_lost(&mode_adc, &lfj8_h03_mmio);
    assert(!lfj8_h03_input_capture(&mode_input, NULL, 1021u));
    assert(!mode_control.manual_gear && poll(1030u) == LFJ8_H03_TOYOTA_FAULT);
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
    test_mode_capture();
    puts("H03 Toyota release: native TML0, fixed deadlines, faults, rollover and manual target PASS");
    return 0;
}
