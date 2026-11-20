#include "lfj8_h03_input_binding.h"

static int valid_binding(const Lfj8H03InputBinding *binding)
{
    return binding && binding->adc && binding->control && binding->button_filter &&
        binding->control->max_age_us && binding->button_filter->max_age_us &&
        binding->io && binding->io->enter && binding->io->leave;
}

static int captures_ready(const Lfj8H03InputBinding *binding, uint32_t now_us)
{
    const Lfj8RangeControl *control = binding->control;
    const Lfj8ButtonFilter *buttons = binding->button_filter;
    return control->selector != RBM_U340E_SELECTOR_UNKNOWN && buttons->armed &&
        now_us - control->last_sample_us < control->max_age_us &&
        now_us - buttons->last_sample_us < buttons->max_age_us;
}

int lfj8_h03_input_capture(const Lfj8H03InputBinding *binding, const Lfj8ButtonReading *buttons,
                          uint32_t now_us)
{
    if (!valid_binding(binding)) {
        return 0;
    }

    Lfj8RangeControl *control = binding->control;
    Lfj8ButtonFilter *filter = binding->button_filter;
    const Lfj8SelectorAdcReading reading = lfj8_selector_adc_take(binding->adc, binding->io);
    lfj8_range_control_sample_selector(control, reading, now_us);
    if (control->selector == RBM_U340E_SELECTOR_UNKNOWN) {
        lfj8_range_control_disarm_buttons(control, filter);
        return 0;
    }

    Lfj8ButtonReading from_adc;
    if (binding->p1_button_map) {
        if (buttons || (reading.event != LFJ8_SELECTOR_ADC_NONE &&
            !lfj8_h03_button_decode_p1(binding->p1_button_map, &reading, &from_adc))) {
            lfj8_range_control_disarm_buttons(control, filter);
            return 0;
        }
        if (reading.event != LFJ8_SELECTOR_ADC_NONE) {
            buttons = &from_adc;
        }
    }
    lfj8_range_control_sample_buttons(control, filter, buttons, now_us);
    return captures_ready(binding, now_us);
}

int lfj8_h03_input_propose_captured(const Lfj8H03InputBinding *binding,
    const Lfj8H03InputSources *sources, Lfj8H03InputProposal *out)
{
    if (!out) {
        return 0;
    }
    *out = (Lfj8H03InputProposal){0};
    if (!valid_binding(binding)) {
        return 0;
    }

    Lfj8RangeControl *control = binding->control;
    Lfj8ButtonFilter *buttons = binding->button_filter;
    Lfj8H03RangeSnapshot range;
    if (!sources || !sources->cycle || !sources->driver ||
        (binding->p1_button_map && sources->buttons) ||
        sources->cycle->qualified != 1 || sources->cycle->engine.coherent != 1 ||
        sources->now_us - sources->cycle->command_at >= UINT32_C(0x80000000) ||
        !lfj8_h03_range_snapshot(sources->range, binding->range_limits, sources->generation,
                                 sources->now_us, &range)) {
        lfj8_range_control_disarm_buttons(control, buttons);
        return 0;
    }

    const uint32_t now = sources->now_us;
    if (!captures_ready(binding, now)) {
        if (buttons->armed) {
            lfj8_range_control_disarm_buttons(control, buttons);
        }
        return 0;
    }
    const Lfj8SelectorAdcReading idle = {.event = LFJ8_SELECTOR_ADC_NONE};
    if (!lfj8_range_control_step_with_buttons(control, idle, buttons, NULL,
                                              now, sources->driver, &out->driver)) {
        out->driver = (RbmU340eOutput){0};
        return 0;
    }
    /* The H03 application does not route the deferred auxiliary relays. */
    out->driver.relay_mask = 0;

    out->cycle = *sources->cycle;
    out->cycle.selector = control->selector;
    out->cycle.range_5722 = range.range_5722;
    out->cycle.inhibit_5250 = range.inhibit_5250;
    const uint32_t captures[] = {control->last_sample_us, buttons->last_sample_us, range.oldest_us};
    for (unsigned i = 0; i < sizeof captures / sizeof captures[0]; ++i) {
        if (now - captures[i] > now - out->cycle.command_at) {
            out->cycle.command_at = captures[i];
        }
    }
    return 1;
}

int lfj8_h03_input_propose(const Lfj8H03InputBinding *binding, const Lfj8H03InputSources *sources,
                           Lfj8H03InputProposal *out)
{
    if (out && sources) {
        lfj8_h03_input_capture(binding, sources->buttons, sources->now_us);
    }
    return lfj8_h03_input_propose_captured(binding, sources, out);
}
