#include "lfj8_range_control.h"

#define HALF_CLOCK UINT32_C(0x80000000)
#define BUTTON_MASK (RBM_U340E_BUTTON_MODE | RBM_U340E_BUTTON_UP | \
                     RBM_U340E_BUTTON_DOWN | RBM_U340E_BUTTON_OVERDRIVE)

int lfj8_range_control_init(Lfj8RangeControl *control, const RbmU340ePolicy *policy,
                            uint32_t max_age_us)
{
    if (!control || max_age_us == 0 || max_age_us >= HALF_CLOCK ||
        !rbm_u340e_init(&control->controller, policy)) {
        return 0;
    }
    control->filter = (RbmU340eSelectorInput){0};
    control->max_age_us = max_age_us;
    control->last_sample_us = 0;
    control->sampled = 0;
    control->selector = RBM_U340E_SELECTOR_UNKNOWN;
    return 1;
}

static void update_selector(Lfj8RangeControl *control, Lfj8SelectorAdcReading reading,
                            uint32_t now_us)
{
    if (control->sampled && now_us - control->last_sample_us >= control->max_age_us) {
        control->sampled = 0;
        control->selector = rbm_u340e_selector_sample(&control->filter, UINT16_MAX);
    }
    if (reading.event == LFJ8_SELECTOR_ADC_NONE ||
        now_us - reading.captured_us >= control->max_age_us) {
        return;
    }
    const uint32_t since_last = reading.captured_us - control->last_sample_us;
    if (control->sampled && (since_last == 0 || since_last >= HALF_CLOCK)) {
        return;
    }

    const uint16_t raw = reading.event == LFJ8_SELECTOR_ADC_VALUE ? reading.raw : UINT16_MAX;
    control->selector = rbm_u340e_selector_sample(&control->filter, raw);
    control->last_sample_us = reading.captured_us;
    control->sampled = 1;
}

int lfj8_range_control_step(Lfj8RangeControl *control, Lfj8SelectorAdcReading reading,
                            uint32_t now_us,
                            const RbmU340eInput *input, RbmU340eOutput *output)
{
    if (!output) {
        return 0;
    }
    if (!control || !control->max_age_us || !input) {
        *output = (RbmU340eOutput){0};
        return 0;
    }
    update_selector(control, reading, now_us);
    RbmU340eInput snapshot = *input;
    snapshot.selector = control->selector;
    return rbm_u340e_step(&control->controller, &snapshot, output);
}

int lfj8_button_filter_init(Lfj8ButtonFilter *filter, uint32_t debounce_us, uint32_t max_age_us)
{
    if (!filter || !debounce_us || debounce_us >= HALF_CLOCK ||
        !max_age_us || max_age_us >= HALF_CLOCK) {
        return 0;
    }
    *filter = (Lfj8ButtonFilter){.debounce_us = debounce_us, .max_age_us = max_age_us};
    return 1;
}

static void disarm_buttons(Lfj8ButtonFilter *filter)
{
    filter->candidate_valid = 0;
    filter->armed = 0;
    filter->stable = 0;
}

static void update_buttons(Lfj8ButtonFilter *filter, const Lfj8ButtonReading *reading,
                           uint32_t now_us)
{
    if (filter->sampled && now_us - filter->last_sample_us >= filter->max_age_us) {
        filter->sampled = 0;
        disarm_buttons(filter);
    }
    if (!reading || now_us - reading->captured_us >= filter->max_age_us) {
        return;
    }
    const uint32_t since_last = reading->captured_us - filter->last_sample_us;
    if (filter->sampled && (since_last == 0 || since_last >= HALF_CLOCK)) {
        return;
    }
    filter->last_sample_us = reading->captured_us;
    filter->sampled = 1;
    if (reading->valid != 1 || (reading->pressed & ~BUTTON_MASK)) {
        disarm_buttons(filter);
        return;
    }
    if (!filter->candidate_valid || reading->pressed != filter->candidate) {
        filter->candidate_since_us = reading->captured_us;
        filter->candidate_valid = 1;
        filter->candidate = reading->pressed;
        return;
    }
    if (reading->captured_us - filter->candidate_since_us >= filter->debounce_us) {
        /* A held input during startup or recovery cannot become an edge. */
        if (filter->armed || !filter->candidate) {
            filter->stable = filter->candidate;
            filter->armed = 1;
        }
    }
}

int lfj8_range_control_step_with_buttons(Lfj8RangeControl *control, Lfj8SelectorAdcReading selector,
    Lfj8ButtonFilter *filter, const Lfj8ButtonReading *buttons, uint32_t now_us,
    const RbmU340eInput *input, RbmU340eOutput *output)
{
    if (!output) {
        return 0;
    }
    if (!control || !control->max_age_us || !filter || !filter->max_age_us || !input) {
        *output = (RbmU340eOutput){0};
        return 0;
    }
    update_buttons(filter, buttons, now_us);
    RbmU340eInput snapshot = *input;
    snapshot.stable_buttons = filter->stable;
    snapshot.buttons_valid = filter->armed;
    if (!lfj8_range_control_step(control, selector, now_us, &snapshot, output)) {
        disarm_buttons(filter);
        return 0;
    }
    return 1;
}
