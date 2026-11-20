#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "chery_model_monitor.h"
#include "lfj8_bridge.h"
#include "lfj8_range_control.h"
#include "panel_pulse.h"
#include "rbm_u340e.h"
#include "ta2005_chery_inputs.h"
#include "ta2005_engine_qualifier.h"

void verify_lfj8_selector_adc(void);

static RbmU340eOutput sample_buttons(RbmU340eController *controller,
    RbmU340eInput *input, uint8_t buttons)
{
    RbmU340eOutput output;
    input->stable_buttons = buttons;
    assert(rbm_u340e_step(controller, input, &output));
    return output;
}

static void print_payload(const uint8_t frame[8])
{
    for (unsigned int index = 0; index < 8; ++index) {
        printf("%02x", (unsigned int)frame[index]);
    }
}

static void parse_payload(const char *hex, uint8_t frame[8])
{
    assert(strlen(hex) == 16);
    for (unsigned int index = 0; index < 8; ++index) {
        unsigned int byte;
        int read = 0;
        assert(sscanf(hex + 2 * index, "%2x%n", &byte, &read) == 1 && read == 2);
        frame[index] = (uint8_t)byte;
    }
}

static void check_selector_clock(void)
{
    const RbmU340ePolicy policy = {.initial_mode = RBM_U340E_AUTO, .initial_overdrive_enabled = 1};
    const RbmU340eInput input = {
        .selector = RBM_U340E_SELECTOR_R,
        .actual_gear = 2,
        .allowed_gears = 0x0f,
        .auto_request_valid = 1,
    };
    Lfj8SelectorAdcReading low = {.raw = 194, .event = LFJ8_SELECTOR_ADC_VALUE};
    Lfj8SelectorAdcReading reverse = {.raw = 812, .event = LFJ8_SELECTOR_ADC_VALUE};
    const Lfj8SelectorAdcReading no_event = {.event = LFJ8_SELECTOR_ADC_NONE};
    Lfj8SelectorAdcReading overrun = {.event = LFJ8_SELECTOR_ADC_OVERRUN};
    const uint32_t start = UINT32_MAX - 10000u;
    const uint32_t max_age = 15000;
    RbmU340eOutput output;
    Lfj8RangeControl control = {0};
    assert(!lfj8_range_control_init(&control, &policy, 0));
    assert(lfj8_range_control_init(&control, &policy, max_age));
    for (unsigned index = 0; index < 4; ++index) {
        const uint32_t at = start + index * 5000u;
        low.captured_us = at;
        assert(lfj8_range_control_step(&control, low, at, &input, &output));
        if (index < 3) {
            assert(!output.relay_mask && !output.requested_gear);
            assert(lfj8_range_control_step(&control, low, at, &input, &output));
            assert(!output.relay_mask && !output.requested_gear);
        }
    }
    const uint32_t last = start + 15000u;
    assert(output.relay_mask == RBM_U340E_RELAY_AUXILIARY && output.requested_gear == 1);
    reverse.captured_us = last - 5000u;
    assert(lfj8_range_control_step(&control, reverse, last + 1, &input, &output));
    assert(output.relay_mask == RBM_U340E_RELAY_AUXILIARY);
    reverse.captured_us = last + 2u;
    assert(lfj8_range_control_step(&control, reverse, last + 1, &input, &output));
    assert(output.relay_mask == RBM_U340E_RELAY_AUXILIARY);
    assert(lfj8_range_control_step(&control, no_event, last + max_age - 1, &input, &output));
    assert(output.relay_mask == RBM_U340E_RELAY_AUXILIARY);
    assert(lfj8_range_control_step(&control, low, last + max_age, &input, &output));
    assert(!output.relay_mask && !output.requested_gear);

    for (unsigned index = 0; index < 4; ++index) {
        const uint32_t at = last + max_age + index * 5000u;
        reverse.captured_us = at;
        assert(lfj8_range_control_step(&control, reverse, at, &input, &output));
        assert(output.relay_mask == (index == 3 ? 3u : 0u));
    }
    const uint32_t lost = last + max_age + 20000u;
    overrun.captured_us = lost;
    assert(lfj8_range_control_step(&control, overrun, lost, &input, &output));
    assert(!output.relay_mask && !output.requested_gear);
}

static void check_selector_fault(void)
{
    const RbmU340ePolicy policy = {.initial_mode = RBM_U340E_AUTO, .initial_overdrive_enabled = 1};
    const RbmU340eInput input = {.actual_gear = 2, .allowed_gears = 0x0f, .auto_request_valid = 1};
    const uint32_t now = 2u;
    const uint32_t last = now - 4u;
    const uint32_t max_age = 25u;
    const Lfj8SelectorAdcEvent faults[] = {LFJ8_SELECTOR_ADC_INVALID, LFJ8_SELECTOR_ADC_OVERRUN};
    const uint32_t fault_times[] = {last, last - 1u, now - max_age, now + 1u, now - 1u};
    for (unsigned kind = 0; kind < sizeof faults / sizeof faults[0]; ++kind) {
        for (unsigned timing = 0; timing < sizeof fault_times / sizeof fault_times[0]; ++timing) {
            Lfj8RangeControl control;
            RbmU340eOutput output;
            assert(lfj8_range_control_init(&control, &policy, max_age));
            Lfj8SelectorAdcReading low = {.raw = 194, .event = LFJ8_SELECTOR_ADC_VALUE};
            for (unsigned sample = 0; sample < 4; ++sample) {
                low.captured_us = last - 2u * (3u - sample);
                assert(lfj8_range_control_step(&control, low, low.captured_us, &input, &output));
            }
            assert(control.selector == RBM_U340E_SELECTOR_L && output.requested_gear == 1);

            const Lfj8SelectorAdcReading fault = {
                .captured_us = fault_times[timing], .raw = UINT16_MAX, .event = faults[kind],
            };
            assert(lfj8_range_control_step(&control, fault, now, &input, &output));
            assert(control.selector == RBM_U340E_SELECTOR_UNKNOWN);
            assert(!output.requested_gear && !output.relay_mask);
            const uint32_t watermark = timing == 4u ? fault.captured_us : last;
            assert(control.last_sample_us == watermark);

            low.captured_us = watermark;
            assert(lfj8_range_control_step(&control, low, now, &input, &output));
            assert(control.filter.samples == 0u && !output.requested_gear);
            for (unsigned sample = 0; sample < 4; ++sample) {
                low.captured_us = now + sample;
                assert(lfj8_range_control_step(&control, low, low.captured_us, &input, &output));
                assert(output.requested_gear == (sample == 3u ? 1u : 0u));
            }
        }
    }
}

static RbmU340eOutput step_range_buttons(Lfj8RangeControl *control, Lfj8ButtonFilter *filter,
    uint32_t now_us, const Lfj8ButtonReading *reading)
{
    const Lfj8SelectorAdcReading selector = {
        .raw = 500, .captured_us = now_us, .event = LFJ8_SELECTOR_ADC_VALUE,
    };
    const RbmU340eInput input = {
        .actual_gear = 2, .allowed_gears = 0x0f,
        .stable_buttons = RBM_U340E_BUTTON_MODE, .buttons_valid = 1,
    };
    RbmU340eOutput output;
    assert(lfj8_range_control_step_with_buttons(control, selector, filter, reading,
        now_us, &input, &output));
    return output;
}

static RbmU340eOutput capture_range_buttons(Lfj8RangeControl *control, Lfj8ButtonFilter *filter,
    uint32_t now_us, uint8_t pressed)
{
    const Lfj8ButtonReading reading = {.captured_us = now_us, .pressed = pressed, .valid = 1};
    return step_range_buttons(control, filter, now_us, &reading);
}

static void check_button_debounce(void)
{
    const RbmU340ePolicy policy = {
        .manual_selectors = 1u << RBM_U340E_SELECTOR_D,
        .initial_mode = RBM_U340E_AUTO, .initial_overdrive_enabled = 1,
    };
    Lfj8RangeControl control;
    Lfj8ButtonFilter filter;
    const uint32_t start = UINT32_MAX - 20u;
    const uint8_t mode = RBM_U340E_BUTTON_MODE;
    const uint8_t up = RBM_U340E_BUTTON_UP;
    const uint8_t down = RBM_U340E_BUTTON_DOWN;
    const uint8_t od = RBM_U340E_BUTTON_OVERDRIVE;

    assert(lfj8_range_control_init(&control, &policy, 30));
    assert(!lfj8_button_filter_init(&filter, 0, 30));
    assert(!lfj8_button_filter_init(&filter, 8, 0));
    assert(!lfj8_button_filter_init(&filter, 8, UINT32_C(0x80000000)));
    assert(lfj8_button_filter_init(&filter, 8, 30));

    assert(capture_range_buttons(&control, &filter, start, mode).mode == RBM_U340E_AUTO);
    assert(capture_range_buttons(&control, &filter, start + 8, mode).mode == RBM_U340E_AUTO);
    capture_range_buttons(&control, &filter, start + 9, 0);
    capture_range_buttons(&control, &filter, start + 17, 0);
    capture_range_buttons(&control, &filter, start + 18, mode);
    capture_range_buttons(&control, &filter, start + 20, 0);
    assert(capture_range_buttons(&control, &filter, start + 21, mode).mode == RBM_U340E_AUTO);
    assert(capture_range_buttons(&control, &filter, start + 28, mode).mode == RBM_U340E_AUTO);
    assert(capture_range_buttons(&control, &filter, start + 29, mode).mode == RBM_U340E_TIPTRONIC);
    assert(capture_range_buttons(&control, &filter, start + 30, mode).mode == RBM_U340E_TIPTRONIC);

    assert(!capture_range_buttons(&control, &filter, start + 31, up).requested_gear);
    assert(!step_range_buttons(&control, &filter, start + 39, NULL).requested_gear);
    assert(capture_range_buttons(&control, &filter, start + 40, up).requested_gear == 3);
    assert(!capture_range_buttons(&control, &filter, start + 41, up).requested_gear);
    capture_range_buttons(&control, &filter, start + 42, 0);
    assert(!capture_range_buttons(&control, &filter, start + 43, up).requested_gear);
    assert(!capture_range_buttons(&control, &filter, start + 51, up).requested_gear);
    capture_range_buttons(&control, &filter, start + 52, 0);
    capture_range_buttons(&control, &filter, start + 60, 0);
    capture_range_buttons(&control, &filter, start + 61, up);
    assert(capture_range_buttons(&control, &filter, start + 69, up).requested_gear == 3);
    capture_range_buttons(&control, &filter, start + 70, down);
    assert(capture_range_buttons(&control, &filter, start + 78, down).requested_gear == 1);
    capture_range_buttons(&control, &filter, start + 79, 0);
    capture_range_buttons(&control, &filter, start + 87, 0);
    capture_range_buttons(&control, &filter, start + 88, up | down);
    const RbmU340eOutput conflict = capture_range_buttons(&control, &filter, start + 96, up | down);
    assert(conflict.conflicting_buttons && !conflict.requested_gear);
    assert(!capture_range_buttons(&control, &filter, start + 97, od).overdrive_pressed);
    const RbmU340eOutput overdrive = capture_range_buttons(&control, &filter, start + 105, od);
    assert(overdrive.overdrive_pressed && !overdrive.overdrive_enabled);
    assert(!capture_range_buttons(&control, &filter, start + 106, od).overdrive_pressed);
}

static void check_button_recovery(void)
{
    const RbmU340ePolicy policy = {
        .manual_selectors = 1u << RBM_U340E_SELECTOR_D,
        .initial_mode = RBM_U340E_TIPTRONIC,
    };
    Lfj8RangeControl control;
    Lfj8ButtonFilter filter;
    const uint8_t up = RBM_U340E_BUTTON_UP;
    const uint8_t down = RBM_U340E_BUTTON_DOWN;

    assert(lfj8_range_control_init(&control, &policy, 50));
    assert(lfj8_button_filter_init(&filter, 8, 30));
    capture_range_buttons(&control, &filter, 1, 0);
    capture_range_buttons(&control, &filter, 9, 0);
    capture_range_buttons(&control, &filter, 10, up);

    Lfj8ButtonReading rejected = {.captured_us = 10, .pressed = down, .valid = 1};
    assert(!step_range_buttons(&control, &filter, 18, &rejected).requested_gear);
    rejected.captured_us = 8;
    assert(!step_range_buttons(&control, &filter, 19, &rejected).requested_gear);
    rejected.captured_us = 21;
    assert(!step_range_buttons(&control, &filter, 20, &rejected).requested_gear);
    assert(capture_range_buttons(&control, &filter, 21, up).requested_gear == 3);

    const Lfj8ButtonReading lost = {.captured_us = 22, .valid = 0};
    step_range_buttons(&control, &filter, 22, &lost);
    capture_range_buttons(&control, &filter, 23, down);
    assert(!capture_range_buttons(&control, &filter, 31, down).requested_gear);
    capture_range_buttons(&control, &filter, 32, 0);
    capture_range_buttons(&control, &filter, 40, 0);
    capture_range_buttons(&control, &filter, 41, down);
    assert(capture_range_buttons(&control, &filter, 49, down).requested_gear == 1);

    /* A duplicate cannot refresh the lifetime. At the boundary a held value
     * starts recovery even if the first capture after the gap is fresh. */
    rejected = (Lfj8ButtonReading){.captured_us = 49, .pressed = down, .valid = 1};
    step_range_buttons(&control, &filter, 78, &rejected);
    capture_range_buttons(&control, &filter, 79, up);
    assert(!capture_range_buttons(&control, &filter, 87, up).requested_gear);
    capture_range_buttons(&control, &filter, 88, 0);
    capture_range_buttons(&control, &filter, 96, 0);
    capture_range_buttons(&control, &filter, 97, up);
    assert(capture_range_buttons(&control, &filter, 105, up).requested_gear == 3);

    capture_range_buttons(&control, &filter, 106, 0x80);
    capture_range_buttons(&control, &filter, 107, down);
    assert(!capture_range_buttons(&control, &filter, 115, down).requested_gear);
}

static void check_button_loss_bad_timestamp(void)
{
    const RbmU340ePolicy policy = {
        .manual_selectors = 1u << RBM_U340E_SELECTOR_D,
        .initial_mode = RBM_U340E_TIPTRONIC, .initial_overdrive_enabled = 1,
    };
    const uint32_t last = UINT32_MAX;
    const uint32_t start = last - 10u;
    const uint8_t up = RBM_U340E_BUTTON_UP;
    const struct {
        uint32_t captured_us;
        uint32_t expected_watermark;
    } timestamps[] = {
        {last, last},             /* Duplicate. */
        {last - 1u, last},        /* Out of order. */
        {last - 30u, last},       /* Expired. */
        {last + 2u, last},        /* Future. */
        {last + 1u, last + 1u},   /* Fresh, immediately after rollover. */
    };
    const Lfj8ButtonReading faults[] = {
        {.valid = 0, .pressed = up},
        {.valid = 1, .pressed = 0x80u},
        {.valid = 2, .pressed = up},
    };

    for (unsigned fault = 0; fault < sizeof faults / sizeof faults[0]; ++fault) {
        for (unsigned i = 0; i < sizeof timestamps / sizeof timestamps[0]; ++i) {
            Lfj8RangeControl control;
            Lfj8ButtonFilter filter;
            assert(lfj8_range_control_init(&control, &policy, 50));
            assert(lfj8_button_filter_init(&filter, 8, 30));
            capture_range_buttons(&control, &filter, start, 0);
            capture_range_buttons(&control, &filter, start + 8u, 0);
            capture_range_buttons(&control, &filter, start + 9u, 0);
            assert(!capture_range_buttons(&control, &filter, last, up).requested_gear);
            assert(control.selector == RBM_U340E_SELECTOR_D && filter.armed);

            Lfj8ButtonReading loss = faults[fault];
            loss.captured_us = timestamps[i].captured_us;
            assert(!step_range_buttons(&control, &filter, last + 1u, &loss).requested_gear);
            assert(filter.last_sample_us == timestamps[i].expected_watermark);
            assert(!capture_range_buttons(&control, &filter, last + 2u, up).requested_gear);
            assert(!capture_range_buttons(&control, &filter, last + 10u, up).requested_gear);
            assert(!filter.armed && !control.controller.buttons_seen);

            capture_range_buttons(&control, &filter, last + 11u, 0);
            assert(!filter.armed);
            capture_range_buttons(&control, &filter, last + 19u, 0);
            assert(filter.armed);
            assert(!capture_range_buttons(&control, &filter, last + 20u, up).requested_gear);
            const RbmU340eOutput recovered = capture_range_buttons(&control, &filter, last + 28u, up);
            assert(recovered.requested_gear == 3 && recovered.overdrive_enabled &&
                   recovered.mode == RBM_U340E_TIPTRONIC);
        }
    }
}

static void reject_range_inputs(const Lfj8H03RangeInputs *inputs, const Lfj8H03RangeAgeLimits *limits,
                                uint32_t generation, uint32_t now_us)
{
    Lfj8H03RangeSnapshot snapshot = {.oldest_us = 42, .range_5722 = 15, .inhibit_5250 = 4};
    assert(!lfj8_h03_range_snapshot(inputs, limits, generation, now_us, &snapshot));
    assert(snapshot.oldest_us == 0 && snapshot.range_5722 == 0 && snapshot.inhibit_5250 == 0);
}

static void check_independent_range_inputs(void)
{
    const uint32_t now_us = 2;
    const uint32_t generation = 0; /* First generation after rollover. */
    const Lfj8H03RangeAgeLimits limits = {.range_5722_us = {3, 4, 5, 6}, .inhibit_5250_2_us = 9};
    Lfj8H03RangeInputs inputs = {
        .inhibit_5250_2 = {.captured_us = now_us - 8u, .generation = generation, .valid = 1},
    };
    for (unsigned bit = 0; bit < 4u; ++bit) {
        inputs.range_5722[bit] = (Lfj8H03RangeBit){
            .captured_us = now_us - 2u - bit, .generation = generation, .valid = 1,
        };
    }

    Lfj8H03RangeSnapshot snapshot;
    for (unsigned mask = 0; mask < 32u; ++mask) {
        for (unsigned bit = 0; bit < 4u; ++bit) {
            inputs.range_5722[bit].asserted = (uint8_t)((mask >> bit) & 1u);
        }
        inputs.inhibit_5250_2.asserted = (uint8_t)(mask >> 4);
        assert(lfj8_h03_range_snapshot(&inputs, &limits, generation, now_us, &snapshot));
        assert(snapshot.range_5722 == (mask & 15u) && snapshot.inhibit_5250 == ((mask >> 4) << 2));
        assert(snapshot.oldest_us == inputs.inhibit_5250_2.captured_us);
    }

    const Lfj8H03RangeInputs valid = inputs;
    for (unsigned bit = 0; bit < 4u; ++bit) {
        inputs = valid;
        inputs.range_5722[bit].valid = 0;
        reject_range_inputs(&inputs, &limits, generation, now_us);
        inputs = valid;
        inputs.range_5722[bit].generation = UINT32_MAX;
        reject_range_inputs(&inputs, &limits, generation, now_us);
        inputs = valid;
        inputs.range_5722[bit].captured_us = now_us - limits.range_5722_us[bit];
        reject_range_inputs(&inputs, &limits, generation, now_us);
    }
    inputs = valid;
    inputs.inhibit_5250_2.generation = UINT32_MAX;
    reject_range_inputs(&inputs, &limits, generation, now_us);
    inputs = valid;
    inputs.inhibit_5250_2.captured_us = now_us - limits.inhibit_5250_2_us;
    reject_range_inputs(&inputs, &limits, generation, now_us);
    inputs = valid;
    inputs.inhibit_5250_2.valid = 2;
    reject_range_inputs(&inputs, &limits, generation, now_us);

    inputs = valid;
    inputs.range_5722[0].captured_us = now_us + 1u;
    reject_range_inputs(&inputs, &limits, generation, now_us);
    inputs = valid;
    inputs.range_5722[0].asserted = 2;
    reject_range_inputs(&inputs, &limits, generation, now_us);
    Lfj8H03RangeAgeLimits bad_limits = limits;
    bad_limits.range_5722_us[1] = 0;
    reject_range_inputs(&valid, &bad_limits, generation, now_us);
    bad_limits = limits;
    bad_limits.inhibit_5250_2_us = UINT32_C(0x80000000);
    reject_range_inputs(&valid, &bad_limits, generation, now_us);
    reject_range_inputs(NULL, &limits, generation, now_us);
    reject_range_inputs(&valid, NULL, generation, now_us);
    assert(!lfj8_h03_range_snapshot(&valid, &limits, generation, now_us, NULL));

    inputs = valid;
    inputs.inhibit_5250_2.captured_us = now_us;
    assert(lfj8_h03_range_snapshot(&inputs, &limits, generation, now_us, &snapshot));
    assert(snapshot.oldest_us == inputs.range_5722[3].captured_us);
}

int main(int argc, char **argv)
{
    verify_lfj8_selector_adc();
    check_selector_clock();
    check_selector_fault();
    check_button_debounce();
    check_button_recovery();
    check_button_loss_bad_timestamp();
    check_independent_range_inputs();
    assert(argc == 1 || argc == 3);
    uint8_t rpm_frame[8] = {0x12, 0xc0, 0xff, 0xff, 0x00, 0xff, 0x00, 0x00};
    uint8_t coolant_frame[8] = {0xb4, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff};
    if (argc == 3) {
        parse_payload(argv[1], rpm_frame);
        parse_payload(argv[2], coolant_frame);
    }
    Ta2005CheryInputs engine_receiver;
    Ta2005CherySnapshot engine_inputs;
    const uint32_t tick = 0;
    ta2005_chery_inputs_reset(&engine_receiver);
    assert(ta2005_chery_inputs_receive(&engine_receiver, 0x0fa, 8, rpm_frame, &tick));
    assert(ta2005_chery_inputs_receive(&engine_receiver, 0x278, 8, coolant_frame, &tick));
    assert(ta2005_chery_inputs_snapshot(&engine_receiver, &tick, 5, &engine_inputs) ==
           (TA2005_CHERY_SPEED | TA2005_CHERY_COOLANT));
    assert(engine_inputs.speed_fad8 == 9600 && engine_inputs.coolant_f9e9 == 137);
    assert(engine_inputs.model.f9d8 == rpm_frame[2] && engine_inputs.model.f9e8 == rpm_frame[3] &&
           engine_inputs.model.f914 == rpm_frame[5]);
    CheryDtcState dtc;
    CheryModelMonitor model;
    Ta2005EngineQualifier engine_qualifier;
    RbmU340eQualifiedEngineFeed feed;
    const Ta2005EngineQualificationContext context = {
        .fallback_fa7b = UINT8_MAX, .coolant_can_enabled = 1, .coherent = 1,
    };
    ta2005_engine_qualifier_init(&engine_qualifier);
    assert(ta2005_engine_qualifier_task2(&engine_qualifier, &engine_inputs, &context, &feed)
           == TA2005_ENGINE_EVALUATED);
    assert(feed.coherent == 1 && feed.fa62 == 9600 && feed.f9b8 == 137);
    const CheryModelContext model_context = {
        .engine_speed_fa62 = feed.fa62, .engine_flags_e026 = feed.e026,
    };
    chery_dtc_init(&dtc);
    chery_model_monitor_init(&model);
    chery_model_monitor_task2(&model, &dtc, &engine_inputs, &model_context);
    assert(model.now_code == (rpm_frame[2] == UINT8_MAX ? 50u : rpm_frame[2]));
    assert(model.limit_code == (rpm_frame[5] == UINT8_MAX ? 50u : rpm_frame[5]));

    const RbmU340ePolicy policy = {
        .manual_selectors = 1u << RBM_U340E_SELECTOR_D,
        .overdrive_limit_modes = RBM_U340E_OVERDRIVE_TIPTRONIC,
        .initial_mode = RBM_U340E_AUTO,
        .initial_overdrive_enabled = 1,
    };
    RbmU340eController controller;
    assert(rbm_u340e_init(&controller, &policy));
    RbmU340eInput input = {
        .selector = RBM_U340E_SELECTOR_R,
        .buttons_valid = 1,
        .actual_gear = 2,
        .allowed_gears = 0x0F,
    };
    assert(sample_buttons(&controller, &input, 0).relay_mask == lfj8_relay_mask('R'));
    assert(lfj8_relay_mask('R') == 3);
    input.selector = RBM_U340E_SELECTOR_L;
    assert(sample_buttons(&controller, &input, 0).relay_mask == lfj8_relay_mask('L'));
    assert(lfj8_relay_mask('L') == 2);
    input.selector = RBM_U340E_SELECTOR_D;
    assert(sample_buttons(&controller, &input, 0).relay_mask == lfj8_relay_mask('D'));
    assert(lfj8_relay_mask('D') == 0);

    assert(sample_buttons(&controller, &input, RBM_U340E_BUTTON_MODE).mode == RBM_U340E_TIPTRONIC);
    assert(sample_buttons(&controller, &input, RBM_U340E_BUTTON_MODE).mode == RBM_U340E_TIPTRONIC);
    assert(sample_buttons(&controller, &input, RBM_U340E_BUTTON_UP).requested_gear == 3);
    assert(sample_buttons(&controller, &input, RBM_U340E_BUTTON_UP).requested_gear == 0);
    assert(sample_buttons(&controller, &input, RBM_U340E_BUTTON_DOWN).requested_gear == 1);
    input.actual_gear = 3;
    assert(sample_buttons(&controller, &input, RBM_U340E_BUTTON_OVERDRIVE).overdrive_pressed);
    assert(!sample_buttons(&controller, &input, RBM_U340E_BUTTON_UP).requested_gear);
    assert(sample_buttons(&controller, &input, RBM_U340E_BUTTON_MODE).mode == RBM_U340E_AUTO);

    const uint16_t raw = lfj8_vss_raw_1ae(11000, 1, 100000, 2000000, 1, 1, LFJ8_VSS_VALID);
    assert(raw == 1440);
    const Lfj8Chery1ae fields = {
        .byte1 = 0xFF,
        .byte4 = 0xFF,
        .flag_e026_0 = 1,
    };
    uint8_t speed_frame[8];
    uint8_t atf_frame[8];
    assert(lfj8_pack_1ae(speed_frame, &fields, raw) == 0);
    lfj8_pack_300(atf_frame, 0, 0, 0, 84, 1);

    const PanelPulseConfig panel_config = {
        .timer_hz = 1000000,
        .minimum_pulses_per_km = 5000,
        .maximum_pulses_per_km = 7000,
        .high_permille = 500,
        .period_field_bits = 32,
        .period_encoding = PANEL_PERIOD_TICKS,
        .width_encoding = PANEL_WIDTH_HIGH_TICKS,
    };
    PanelPulse panel;
    assert(panel_pulse_init(&panel, &panel_config));
    const unsigned int speed_q7 = (raw / 25u) * 32u;
    const PanelOutput pulse = panel_pulse_plan(&panel, (uint16_t)(speed_q7 * 100u / 128u), true);
    assert(pulse.status == PANEL_OUTPUT_ACTIVE);
    assert(pulse.period_field == 42105);
    assert(pulse.width_field == 21053);

    printf("{\"speed_raw\":%u,\"0x1AE\":\"", (unsigned int)raw);
    print_payload(speed_frame);
    printf("\",\"0x300\":\"");
    print_payload(atf_frame);
    printf("\",\"panel_input_speed_q7\":%u,\"panel_period_ticks_1mhz\":%lu,"
           "\"tc_rx_rpm_q3\":%u,\"tc_rx_coolant_plus_50\":%u,"
           "\"tc_rx_model_codes\":[%u,%u,%u],"
           "\"tc_qualified_model_codes\":[%u,%u],"
           "\"selector_adc_events\":\"PASS\",\"selector_timeout\":\"PASS\"}\n",
           speed_q7, (unsigned long)pulse.period_field,
           (unsigned int)engine_inputs.speed_fad8, (unsigned int)engine_inputs.coolant_f9e9,
           (unsigned int)engine_inputs.model.f9d8, (unsigned int)engine_inputs.model.f9e8,
           (unsigned int)engine_inputs.model.f914,
           (unsigned int)model.now_code, (unsigned int)model.limit_code);
    return 0;
}
