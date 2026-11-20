#include "lfj8_h03_input_binding.h"

#undef NDEBUG
#include <assert.h>
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
    f->io = (Lfj8RegisterIo){.context = f, .enter = enter, .leave = leave};
    f->binding = (Lfj8H03InputBinding){&f->adc, &f->control, &f->buttons, &f->io, &limits};
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

int main(void)
{
    test_six_positions();
    test_shift_and_od();
    test_auto_conflict();
    test_invalid_snapshots();
    test_adc_loss_and_recovery();
    puts("H03 input proposal: six ranges, debounce, conflict, Auto/OD, independent freshness, ADC loss and rearm PASS");
    return 0;
}
