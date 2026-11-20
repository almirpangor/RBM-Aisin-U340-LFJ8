#include "lfj8_h03_input_binding.h"

int lfj8_h03_input_propose(const Lfj8H03InputBinding *binding, const Lfj8H03InputSources *sources,
                           Lfj8H03InputProposal *out)
{
    if (!out) {
        return 0;
    }
    *out = (Lfj8H03InputProposal){0};
    if (!binding || !binding->adc || !binding->control || !binding->button_filter ||
        !binding->control->max_age_us || !binding->button_filter->max_age_us ||
        !binding->io || !binding->io->enter || !binding->io->leave) {
        return 0;
    }

    Lfj8RangeControl *control = binding->control;
    Lfj8ButtonFilter *buttons = binding->button_filter;
    if (!sources) {
        lfj8_range_control_disarm_buttons(control, buttons);
        return 0;
    }
    const uint32_t now = sources->now_us;
    const Lfj8SelectorAdcReading reading = lfj8_selector_adc_take(binding->adc, binding->io);
    lfj8_range_control_sample_selector(control, reading, now);
    const Lfj8H03CycleInput *cycle = sources->cycle;
    Lfj8H03RangeSnapshot range;
    if (control->selector == RBM_U340E_SELECTOR_UNKNOWN || !cycle || !sources->driver ||
        cycle->qualified != 1 || cycle->engine.coherent != 1 ||
        now - cycle->command_at >= UINT32_C(0x80000000) ||
        !lfj8_h03_range_snapshot(sources->range, binding->range_limits, sources->generation, now, &range)) {
        lfj8_range_control_disarm_buttons(control, buttons);
        return 0;
    }

    const Lfj8SelectorAdcReading idle = {.event = LFJ8_SELECTOR_ADC_NONE};
    if (!lfj8_range_control_step_with_buttons(control, idle, buttons, sources->buttons,
                                              now, sources->driver, &out->driver) || !buttons->armed) {
        out->driver = (RbmU340eOutput){0};
        return 0;
    }
    /* The H03 application does not route the deferred auxiliary relays. */
    out->driver.relay_mask = 0;

    out->cycle = *cycle;
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
