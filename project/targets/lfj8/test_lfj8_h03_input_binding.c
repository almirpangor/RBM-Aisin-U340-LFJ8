#include "lfj8_h03_input_binding.h"

#undef NDEBUG
#include <assert.h>
#include <stddef.h>
#include <stdio.h>

typedef struct {
    Lfj8SelectorAdc adc;
    Lfj8RangeControl control;
    Lfj8ButtonFilter buttons;
    Lfj8RegisterIo io;
    Lfj8H03InputBinding binding;
    Lfj8H03InputSources sources;
    Lfj8H03InputProposal proposal;
    Lfj8H03CycleInput cycle;
    RbmU340eInput driver;
    Lfj8H03RangeInputs range;
    Lfj8ButtonReading reading;
    uint8_t locked;
    uint8_t p1data;
    unsigned p1_reads;
} Fixture;

static uint32_t enter(void *context)
{
    Fixture *f = context;
    assert(!f->locked);
    f->locked = 1;
    return UINT32_C(0x40);
}

static void leave(void *context, uint32_t saved)
{
    Fixture *f = context;
    assert(f->locked && saved == 0x40u);
    f->locked = 0;
}

_Static_assert(sizeof(Lfj8SelectorAdc) == 12 && offsetof(Lfj8SelectorAdc, pending_event) == 8,
               "H03 mailbox layout changed");
_Static_assert(sizeof(Lfj8SelectorAdcReading) == 12 && offsetof(Lfj8SelectorAdcReading, event) == 8,
               "H03 observation layout changed");

static uint8_t read_p1(void *context, uint32_t address)
{
    Fixture *f = context;
    assert(f->locked && address == LFJ8_H03_P1DATA_ADDRESS);
    ++f->p1_reads;
    return f->p1data;
}

static void init(Fixture *f)
{
    static const RbmU340ePolicy policy = {
        .manual_selectors = 1u << RBM_U340E_SELECTOR_D,
        .overdrive_limit_modes = RBM_U340E_OVERDRIVE_TIPTRONIC,
        .initial_mode = RBM_U340E_TIPTRONIC,
        .initial_overdrive_enabled = 1,
    };
    static const Lfj8H03RangeAgeLimits limits = {
        .range_5722_us = {18, 19, 20, 21}, .inhibit_5250_2_us = 22,
    };
    *f = (Fixture){0};
    lfj8_selector_adc_init(&f->adc);
    assert(lfj8_range_control_init(&f->control, &policy, 15));
    assert(lfj8_button_filter_init(&f->buttons, 5, 15));
    f->io = (Lfj8RegisterIo){.context = f, .read8 = read_p1, .enter = enter, .leave = leave};
    f->binding = (Lfj8H03InputBinding){
        .adc = &f->adc, .control = &f->control, .button_filter = &f->buttons,
        .io = &f->io, .range_limits = &limits,
    };
    f->sources = (Lfj8H03InputSources){
        .cycle = &f->cycle, .driver = &f->driver, .range = &f->range, .buttons = &f->reading,
        .generation = 3, .now_us = UINT32_MAX - 20u,
    };
    f->cycle = (Lfj8H03CycleInput){
        .engine = {.fa62 = 9600, .coherent = 1}, .qualified = 1,
        .selector = UINT8_MAX, .range_5722 = UINT8_MAX, .inhibit_5250 = UINT8_MAX,
    };
    f->driver = (RbmU340eInput){
        .actual_gear = 2, .allowed_gears = 15, .selector = UINT8_MAX,
        .stable_buttons = UINT8_MAX, .buttons_valid = UINT8_MAX,
    };
}

static int ram_owned(void *platform)
{
    (void)platform;
    return 1;
}

static int read_non_engine(void *platform, const Lfj8H03SensorSnapshot *sensors,
    uint32_t due_at, Lfj8H03CycleInput *input, Lfj8H03CycleLoad *load,
    Lfj8H03InputSources *sources)
{
    Fixture *const f = platform;
    assert(!f->locked && sensors->epoch == f->sources.generation);
    const uint32_t event = input->event;
    *input = (Lfj8H03CycleInput){.event = event, .command_at = due_at - 1u, .qualified = 1u};
    *load = (Lfj8H03CycleLoad){.now_us = due_at};
    *sources = (Lfj8H03InputSources){
        .driver = &f->driver, .range = &f->range, .generation = sensors->epoch,
    };
    return 1;
}

static void prepare_sources(Fixture *f, uint8_t pressed)
{
    f->sources.now_us += 5;
    const uint32_t now = f->sources.now_us;
    const uint32_t generation = f->sources.generation;
    ++f->cycle.event;
    f->cycle.command_at = now - 1u;
    for (unsigned i = 0; i < 4; ++i) {
        f->range.range_5722[i] = (Lfj8H03RangeBit){now - 5u - i, generation, (uint8_t)(i & 1u), 1};
    }
    f->range.inhibit_5250_2 = (Lfj8H03RangeBit){now - 3u, generation, 1, 1};
    f->reading = (Lfj8ButtonReading){.captured_us = now - 2u, .pressed = pressed, .valid = 1};
    f->sources.buttons = &f->reading;
}

static void prepare(Fixture *f, uint16_t raw, uint8_t pressed)
{
    prepare_sources(f, pressed);
    lfj8_selector_adc_publish(&f->adc, &f->io, raw, f->sources.now_us);
}

static int propose(Fixture *f)
{
    const int result = lfj8_h03_input_propose(&f->binding, &f->sources, &f->proposal);
    assert(!f->locked);
    if (!result) {
        assert(!f->proposal.cycle.qualified && !f->proposal.driver.requested_gear &&
               !f->proposal.driver.auto_request_valid && !f->proposal.driver.overdrive_pressed);
    }
    return result;
}

static int tick(Fixture *f, uint16_t raw, uint8_t pressed)
{
    prepare(f, raw, pressed);
    return propose(f);
}

static void qualify(Fixture *f, uint16_t raw)
{
    for (unsigned i = 0; i < 4; ++i) {
        assert(!tick(f, raw, 0));
    }
    assert(tick(f, raw, 0));
}

static void test_six_positions(void)
{
    const uint16_t codes[] = {930, 820, 665, 500, 340, 190};
    Fixture f;
    init(&f);
    for (unsigned i = 0; i < sizeof codes / sizeof codes[0]; ++i) {
        qualify(&f, codes[i]);
        assert(f.proposal.cycle.selector == RBM_U340E_SELECTOR_P + i);
        assert(f.proposal.cycle.qualified == 1 && f.proposal.cycle.engine.fa62 == 9600);
        assert(f.proposal.cycle.event == f.cycle.event);
        assert(f.proposal.cycle.range_5722 == 0x0a && f.proposal.cycle.inhibit_5250 == 4);
        assert(f.proposal.cycle.command_at == f.range.range_5722[3].captured_us);
        assert(!f.proposal.driver.requested_gear && !f.proposal.driver.relay_mask);
    }
}

static void test_task2_feed_survives_capture(void)
{
    Fixture f;
    init(&f);
    f.binding.manual_max_age_us = 50u;
    f.cycle.engine = (RbmU340eQualifiedEngineFeed){
        .fa62 = 9600u, .fd10 = 0xd234u, .e026 = 0xa7u, .coherent = 1u,
    };
    qualify(&f, 500u);
    prepare(&f, 500u, 0u);
    assert(lfj8_h03_input_capture(&f.binding, &f.reading, f.sources.now_us));

    Lfj8H03InputProposal proposal = {0};
    Lfj8H03ToyotaInputCapture capture = {
        .binding = &f.binding, .proposal = &proposal, .platform = &f,
        .ram_owned = ram_owned, .read = read_non_engine,
    };
    const Lfj8H03SensorSnapshot sensors = {.epoch = f.sources.generation};
    Lfj8H03CycleLoad load = {0};
    assert(lfj8_h03_input_capture_toyota(&capture, &sensors, f.sources.now_us, &f.cycle, &load));
    assert(f.cycle.engine.fa62 == 9600u && f.cycle.engine.fd10 == 0xd234u &&
           f.cycle.engine.e026 == 0xa7u && f.cycle.engine.coherent == 1u);
}

static void test_shift_and_od(void)
{
    Fixture f;
    init(&f);
    qualify(&f, 500);
    const uint8_t up = RBM_U340E_BUTTON_UP;
    const uint8_t down = RBM_U340E_BUTTON_DOWN;
    const uint8_t od = RBM_U340E_BUTTON_OVERDRIVE;
    assert(tick(&f, 500, up) && !f.proposal.driver.requested_gear);
    assert(tick(&f, 500, 0) && !f.proposal.driver.requested_gear);
    assert(tick(&f, 500, up) && !f.proposal.driver.requested_gear);
    assert(tick(&f, 500, up) && f.proposal.driver.requested_gear == 3);
    assert(tick(&f, 500, up | down) && !f.proposal.driver.conflicting_buttons);
    assert(tick(&f, 500, up | down) && f.proposal.driver.conflicting_buttons);
    assert(!f.proposal.driver.requested_gear && !f.proposal.driver.auto_request_valid);
    assert(tick(&f, 500, 0));
    assert(tick(&f, 500, 0));

    assert(tick(&f, 500, od) && !f.proposal.driver.overdrive_pressed);
    assert(tick(&f, 500, od) && f.proposal.driver.overdrive_pressed && !f.proposal.driver.overdrive_enabled);
    assert(tick(&f, 500, 0));
    assert(tick(&f, 500, 0));
    f.driver.actual_gear = 3;
    assert(tick(&f, 500, up));
    assert(tick(&f, 500, up) && !f.proposal.driver.requested_gear);
}

static void test_auto_conflict(void)
{
    Fixture f;
    init(&f);
    qualify(&f, 500);
    f.driver.auto_request_valid = 1;
    f.driver.auto_request.speed_4549 = 254;
    const uint8_t mode_and_up = RBM_U340E_BUTTON_MODE | RBM_U340E_BUTTON_UP;
    assert(tick(&f, 500, mode_and_up));
    assert(tick(&f, 500, mode_and_up));
    assert(f.proposal.cycle.qualified == 1 && f.proposal.driver.mode == RBM_U340E_AUTO);
    assert(f.proposal.driver.conflicting_buttons && !f.proposal.driver.auto_request_valid &&
           !f.proposal.driver.requested_gear);
    assert(tick(&f, 500, 0) && f.proposal.driver.requested_gear == 4);

    const uint8_t both = RBM_U340E_BUTTON_UP | RBM_U340E_BUTTON_DOWN;
    assert(tick(&f, 500, both));
    assert(tick(&f, 500, both));
    assert(f.proposal.driver.conflicting_buttons && !f.proposal.driver.auto_request_valid &&
           !f.proposal.driver.requested_gear);
    assert(tick(&f, 500, 0));
    assert(tick(&f, 500, 0) && f.proposal.driver.auto_request_valid &&
           f.proposal.driver.requested_gear == 4);
}

static void test_invalid_snapshots(void)
{
    Fixture f;
    init(&f);
    qualify(&f, 500);
    const uint8_t mode = RBM_U340E_BUTTON_MODE;
    assert(tick(&f, 500, mode));
    prepare(&f, 500, mode);
    --f.range.range_5722[2].generation;
    assert(!propose(&f) && f.control.controller.mode == RBM_U340E_TIPTRONIC);
    assert(!tick(&f, 500, mode));
    assert(!tick(&f, 500, mode));
    assert(!tick(&f, 500, 0));
    assert(tick(&f, 500, 0));

    prepare(&f, 500, mode);
    f.range.inhibit_5250_2.captured_us = f.sources.now_us - f.binding.range_limits->inhibit_5250_2_us;
    assert(!propose(&f));
    prepare(&f, 500, 0);
    f.cycle.command_at = f.sources.now_us + 1u;
    assert(!propose(&f));
    assert(!tick(&f, 500, 0));
    assert(tick(&f, 500, 0));
    prepare(&f, 500, 0);
    f.sources.now_us += 5;
    f.cycle.command_at = f.sources.now_us - 14u;
    assert(propose(&f) && f.proposal.cycle.command_at == f.cycle.command_at);

    prepare(&f, 500, mode);
    f.reading.valid = 0;
    assert(!propose(&f));
    assert(!tick(&f, 500, mode));
    assert(!tick(&f, 500, 0));
    assert(tick(&f, 500, 0));
    for (unsigned i = 0; i < 4; ++i) {
        prepare(&f, 500, 0);
        f.sources.buttons = NULL;
        assert(propose(&f) == (i < 2));
        if (i == 1) {
            assert(f.proposal.cycle.command_at == f.buttons.last_sample_us);
        }
    }
    assert(!tick(&f, UINT16_MAX, 0));
    assert(f.control.selector == RBM_U340E_SELECTOR_UNKNOWN);
}

static void test_adc_loss_and_recovery(void)
{
    Fixture f;
    init(&f);
    qualify(&f, 500);
    const uint32_t last_adc = f.control.last_sample_us;
    prepare_sources(&f, 0);
    assert(propose(&f));
    prepare_sources(&f, 0);
    assert(propose(&f) && f.proposal.cycle.command_at == last_adc);
    prepare_sources(&f, 0);
    assert(!propose(&f) && f.control.selector == RBM_U340E_SELECTOR_UNKNOWN);
    qualify(&f, 500);
    prepare(&f, 500, 0);
    lfj8_selector_adc_publish(&f.adc, &f.io, 500, f.sources.now_us);
    assert(!propose(&f) && f.control.selector == RBM_U340E_SELECTOR_UNKNOWN);
    qualify(&f, 500);

    prepare(&f, 500, RBM_U340E_BUTTON_MODE);
    lfj8_selector_adc_clock_lost(&f.adc, &f.io);
    lfj8_selector_adc_publish(&f.adc, &f.io, 500, f.sources.now_us);
    assert(f.adc.pending_event == LFJ8_SELECTOR_ADC_CLOCK_LOST);
    assert(!propose(&f) && !f.control.sampled && !f.buttons.armed);
    for (unsigned i = 0; i < 4; ++i) {
        assert(!tick(&f, 500, RBM_U340E_BUTTON_MODE));
    }
    assert(!tick(&f, 500, 0));
    assert(tick(&f, 500, 0) && f.proposal.driver.mode == RBM_U340E_TIPTRONIC);
    assert(tick(&f, 500, RBM_U340E_BUTTON_MODE));
    assert(tick(&f, 500, RBM_U340E_BUTTON_MODE) && f.proposal.driver.mode == RBM_U340E_AUTO);
    f.driver.auto_request_valid = 1;
    f.driver.auto_request.speed_4549 = 254;
    assert(tick(&f, 500, 0) && f.proposal.driver.auto_request_valid &&
           f.proposal.driver.requested_gear == 4);
    prepare(&f, 500, 0);
    f.reading.valid = 0;
    assert(!propose(&f));
}

static void acquire_p1(Fixture *f, uint8_t port)
{
    prepare_sources(f, 0);
    f->sources.buttons = NULL;
    f->p1data = port;
    lfj8_selector_adc_publish_h03(&f->adc, &f->io, 500, f->sources.now_us);
}

static int step_p1(Fixture *f, uint8_t port)
{
    acquire_p1(f, port);
    return propose(f);
}

static int step_profiled_p1(Fixture *f, uint16_t raw, uint8_t port)
{
    prepare_sources(f, 0);
    f->sources.buttons = NULL;
    f->p1data = port;
    lfj8_selector_adc_publish_h03(&f->adc, &f->io, raw, f->sources.now_us);
    return propose(f);
}

static void test_profiled_selector_startup(void)
{
    /* Deliberately different simulator windows and qualification count. */
    static const RbmU340eSelectorProfile selector = {
        .windows = {{980, 990}, {860, 870}, {610, 620}, {550, 570}, {390, 400}, {230, 240}},
        .stable_samples = 2,
    };
    static const Lfj8H03InputStartup startup = {
        .policy = {.manual_selectors = 1u << RBM_U340E_SELECTOR_D,
                   .initial_mode = RBM_U340E_TIPTRONIC, .initial_overdrive_enabled = 1},
        .selector_max_age_us = 16, .button_debounce_us = 5, .button_max_age_us = 16,
    };
    static const Lfj8H03ButtonMap map = {{
        {LFJ8_H03_BUTTON_P1, 8, 1}, {LFJ8_H03_BUTTON_P1, 64, 0},
        {LFJ8_H03_BUTTON_P1, 32, 0}, {0},
    }};
    Fixture f;
    init(&f);
    f.binding.p1_button_map = &map;
    f.binding.manual_max_age_us = 16u;
    assert(!lfj8_h03_input_startup(&f.binding, &startup));
    RbmU340eSelectorProfile invalid = selector;
    f.binding.selector_profile = &invalid;
    invalid.windows[1][1] = 981u;
    assert(!lfj8_h03_input_startup(&f.binding, &startup));
    invalid = selector;
    invalid.windows[0][1] = 1025u;
    assert(!lfj8_h03_input_startup(&f.binding, &startup));
    invalid = selector;
    invalid.stable_samples = 0;
    assert(!lfj8_h03_input_startup(&f.binding, &startup));
    f.binding.selector_profile = &selector;
    assert(lfj8_h03_input_startup(&f.binding, &startup));

    for (unsigned i = 0; i < 6u; ++i) {
        const uint16_t low = selector.windows[i][0];
        assert(!step_profiled_p1(&f, low, 8u) && f.control.filter.samples == 1u);
        assert(!step_profiled_p1(&f, low, 8u) && !f.buttons.armed);
        assert(step_profiled_p1(&f, low, 8u));
        assert(f.proposal.cycle.selector == RBM_U340E_SELECTOR_P + i);
        assert(!step_profiled_p1(&f, selector.windows[i][1], 8u));
        assert(f.control.selector == RBM_U340E_SELECTOR_UNKNOWN && !f.buttons.armed);
    }

    const uint16_t drive = selector.windows[RBM_U340E_SELECTOR_D - 1][0];
    assert(!step_profiled_p1(&f, drive, 8u));
    assert(!step_profiled_p1(&f, drive, 8u));
    assert(step_profiled_p1(&f, drive, 8u));
    assert(step_profiled_p1(&f, drive, 72u));
    assert(step_profiled_p1(&f, drive, 72u) && f.proposal.cycle.requested_gear == 3u);
    assert(lfj8_h03_input_startup(&f.binding, &startup));
    assert(!f.control.manual_gear && !f.buttons.armed && !f.control.sampled);
    assert(!step_profiled_p1(&f, drive, 72u));
    assert(!step_profiled_p1(&f, drive, 72u));
    assert(!step_profiled_p1(&f, drive, 72u));
    assert(!step_profiled_p1(&f, drive, 8u));
    assert(step_profiled_p1(&f, drive, 8u) && !f.proposal.cycle.requested_gear);
}

static void test_p1_route(void)
{
    /* Synthetic pin layout including an active-low mode button. */
    static const Lfj8H03ButtonMap map = {{
        {LFJ8_H03_BUTTON_P1, 8, 1}, {LFJ8_H03_BUTTON_P1, 64, 0},
        {LFJ8_H03_BUTTON_P1, 32, 0}, {0},
    }};
    const uint8_t released = 8, up = released | 64;
    Fixture f;
    init(&f);
    f.binding.p1_button_map = &map;
    f.sources.now_us = UINT32_MAX - 33u;
    for (unsigned i = 0; i < 4u; ++i) {
        assert(!step_p1(&f, released));
    }
    assert(step_p1(&f, released) && f.buttons.armed);
    assert(f.p1_reads == 5u);

    assert(step_p1(&f, up) && !f.proposal.driver.requested_gear);
    acquire_p1(&f, up); /* Cross zero while debouncing the request. */
    f.p1data = released;
    assert(propose(&f) && f.proposal.driver.requested_gear == 3);
    assert(f.buttons.last_sample_us == f.sources.now_us && f.p1_reads == 7u);
    assert(propose(&f) && !f.proposal.driver.requested_gear && f.p1_reads == 7u);

    acquire_p1(&f, up);
    lfj8_selector_adc_publish_h03(&f.adc, &f.io, 500, f.sources.now_us);
    assert(f.p1_reads == 8u && !f.adc.pending_p1_valid && !f.adc.pending_p1data);
    assert(!propose(&f) && !f.buttons.armed);
    for (unsigned i = 0; i < 5u; ++i) {
        assert(!step_p1(&f, up));
    }
    assert(!step_p1(&f, released));
    assert(step_p1(&f, released) && f.buttons.armed && !f.proposal.driver.requested_gear);

    const unsigned reads = f.p1_reads;
    prepare_sources(&f, 0);
    f.sources.buttons = NULL;
    lfj8_selector_adc_publish_h03(&f.adc, &f.io, UINT16_MAX, f.sources.now_us);
    assert(f.p1_reads == reads && !propose(&f) && !f.buttons.armed);
    for (unsigned i = 0; i < 4u; ++i) {
        assert(!step_p1(&f, released));
    }
    assert(step_p1(&f, released) && f.buttons.armed);
    prepare_sources(&f, 0);
    f.sources.buttons = NULL;
    lfj8_selector_adc_publish(&f.adc, &f.io, 500, f.sources.now_us);
    assert(!propose(&f) && !f.buttons.armed);

    assert(!step_p1(&f, released));
    assert(step_p1(&f, released) && f.buttons.armed);
    acquire_p1(&f, up);
    f.sources.buttons = &f.reading;
    assert(!propose(&f) && !f.buttons.armed); /* No ambiguous source precedence. */

    Lfj8H03ButtonMap aux = map;
    aux.pins[3] = (Lfj8H03ButtonPin){LFJ8_H03_BUTTON_AUX, 1, 0};
    f.binding.p1_button_map = &aux;
    assert(!step_p1(&f, released) && !f.buttons.armed);

    acquire_p1(&f, up);
    lfj8_selector_adc_clock_lost(&f.adc, &f.io);
    const unsigned before = f.p1_reads;
    lfj8_selector_adc_publish_h03(&f.adc, &f.io, 500, f.sources.now_us);
    assert(f.p1_reads == before && !propose(&f) && !f.buttons.armed);
}

static void test_phase_capture(void)
{
    static const Lfj8H03ButtonMap map = {{
        {LFJ8_H03_BUTTON_P1, 8, 1}, {LFJ8_H03_BUTTON_P1, 64, 0},
        {LFJ8_H03_BUTTON_P1, 32, 0}, {0},
    }};
    const uint8_t released = 8u, up = released | 64u;
    Fixture f;
    init(&f);
    f.binding.p1_button_map = &map;
    f.sources.now_us = UINT32_MAX - 33u;
    for (unsigned pass = 0; pass < 5u; ++pass) {
        acquire_p1(&f, released);
        assert(lfj8_h03_input_capture(&f.binding, NULL, f.sources.now_us) == (pass == 4u));
        assert(!f.control.controller.buttons_seen);
        assert(f.adc.pending_event == LFJ8_SELECTOR_ADC_NONE);
    }
    assert(lfj8_h03_input_propose_captured(&f.binding, &f.sources, &f.proposal));
    assert(f.proposal.cycle.selector == RBM_U340E_SELECTOR_D && !f.proposal.driver.requested_gear);

    for (unsigned pass = 0; pass < 2u; ++pass) {
        acquire_p1(&f, up);
        assert(lfj8_h03_input_capture(&f.binding, NULL, f.sources.now_us));
        assert(f.control.controller.previous_buttons == 0u);
    }
    assert(f.buttons.stable == RBM_U340E_BUTTON_UP);
    assert(f.buttons.last_sample_us == 1u); /* A capture crossed the wrap. */

    acquire_p1(&f, released); /* The next mailbox belongs to the next H03 pass. */
    assert(lfj8_h03_input_propose_captured(&f.binding, &f.sources, &f.proposal));
    assert(f.proposal.driver.requested_gear == 3 && f.adc.pending_event == LFJ8_SELECTOR_ADC_VALUE);
    assert(lfj8_h03_input_propose_captured(&f.binding, &f.sources, &f.proposal));
    assert(!f.proposal.driver.requested_gear);
    assert(lfj8_h03_input_capture(&f.binding, NULL, f.sources.now_us));

    prepare_sources(&f, 0);
    f.sources.buttons = NULL;
    f.sources.now_us = f.control.last_sample_us + f.control.max_age_us;
    assert(!lfj8_h03_input_propose_captured(&f.binding, &f.sources, &f.proposal));
    assert(!f.proposal.cycle.qualified && !f.buttons.armed && !f.control.controller.buttons_seen);
    assert(!lfj8_h03_input_capture(&f.binding, NULL, f.sources.now_us));

    for (unsigned pass = 0; pass < 5u; ++pass) {
        acquire_p1(&f, up);
        assert(!lfj8_h03_input_capture(&f.binding, NULL, f.sources.now_us));
    }
    assert(!lfj8_h03_input_propose_captured(&f.binding, &f.sources, &f.proposal));
    lfj8_selector_adc_clock_lost(&f.adc, &f.io);
    assert(!lfj8_h03_input_capture(&f.binding, NULL, f.sources.now_us));
    assert(!f.control.sampled && !f.buttons.armed);
}

static void manual_edge(Fixture *f, uint8_t actual)
{
    init(f);
    f->sources.now_us = UINT32_MAX - 48u;
    f->binding.manual_max_age_us = 50u;
    f->driver.actual_gear = actual;
    f->cycle.requested_gear = 1u;
    qualify(f, 500);
    assert(!f->proposal.cycle.requested_gear);
    assert(tick(f, 500, RBM_U340E_BUTTON_UP) && !f->proposal.cycle.requested_gear);
    assert(tick(f, 500, RBM_U340E_BUTTON_UP));
    assert(f->proposal.driver.requested_gear == actual + 1u);
    assert(f->proposal.cycle.requested_gear == actual + 1u);
}

static void test_manual_target(void)
{
    Fixture f;
    const uint8_t up = RBM_U340E_BUTTON_UP;
    manual_edge(&f, 2);
    assert(tick(&f, 500, 0) && !f.proposal.driver.requested_gear);
    assert(f.proposal.cycle.requested_gear == 3);
    f.driver.shifting = 1;
    f.driver.actual_gear = 0;
    assert(tick(&f, 500, 0) && f.proposal.cycle.requested_gear == 3);
    f.driver.actual_gear = 3;
    f.driver.shifting = 0;
    assert(tick(&f, 500, 0) && !f.proposal.cycle.requested_gear);

    manual_edge(&f, 2);
    f.binding.manual_max_age_us = 15u;
    for (unsigned i = 1; i <= 4; ++i) {
        assert(tick(&f, 500, up));
        assert(f.proposal.cycle.requested_gear == (i < 3 ? 3 : 0));
    }
    assert(f.sources.now_us < 15u && !f.control.manual_gear);

    manual_edge(&f, 2);
    f.driver.allowed_gears &= (uint8_t)~4u;
    assert(tick(&f, 500, up) && !f.proposal.cycle.requested_gear);
    f.driver.allowed_gears |= 4u;
    assert(tick(&f, 500, up) && !f.proposal.cycle.requested_gear);

    manual_edge(&f, 3);
    const uint8_t od = RBM_U340E_BUTTON_OVERDRIVE;
    assert(tick(&f, 500, od) && f.proposal.cycle.requested_gear == 4);
    assert(tick(&f, 500, od) && !f.proposal.cycle.requested_gear);

    manual_edge(&f, 2);
    const uint8_t mode = RBM_U340E_BUTTON_MODE;
    assert(tick(&f, 500, mode) && f.proposal.cycle.requested_gear == 3);
    assert(tick(&f, 500, mode) && f.proposal.driver.mode == RBM_U340E_AUTO);
    assert(!f.proposal.cycle.requested_gear);

    manual_edge(&f, 2);
    const uint8_t both = up | RBM_U340E_BUTTON_DOWN;
    assert(tick(&f, 500, both) && f.proposal.cycle.requested_gear == 3);
    assert(tick(&f, 500, both) && !f.proposal.cycle.requested_gear);
    assert(!f.control.manual_gear && f.proposal.driver.conflicting_buttons);
    const uint8_t down = RBM_U340E_BUTTON_DOWN;
    assert(tick(&f, 500, down));
    assert(tick(&f, 500, down) && f.proposal.driver.conflicting_buttons);
    assert(!f.proposal.cycle.requested_gear);
    assert(tick(&f, 500, 0));
    assert(tick(&f, 500, 0) && !f.proposal.driver.conflicting_buttons);
    assert(tick(&f, 500, down));
    assert(tick(&f, 500, down) && f.proposal.cycle.requested_gear == 1);

    manual_edge(&f, 2);
    ++f.sources.generation;
    assert(!tick(&f, 500, up) && !f.control.manual_gear && !f.buttons.armed);
    assert(!tick(&f, 500, up));

    manual_edge(&f, 2);
    assert(!tick(&f, 665, up) && !f.control.manual_gear && !f.buttons.armed);

    manual_edge(&f, 2);
    prepare(&f, 500, up);
    f.reading.valid = 0;
    assert(!propose(&f) && !f.control.manual_gear && !f.buttons.armed);
}

int main(void)
{
    test_six_positions();
    test_task2_feed_survives_capture();
    test_shift_and_od();
    test_auto_conflict();
    test_invalid_snapshots();
    test_adc_loss_and_recovery();
    test_p1_route();
    test_profiled_selector_startup();
    test_phase_capture();
    test_manual_target();
    puts("H03 input proposal: six ranges, mode/OD, split phase capture, freshness, manual hold and revocation PASS");
    return 0;
}
