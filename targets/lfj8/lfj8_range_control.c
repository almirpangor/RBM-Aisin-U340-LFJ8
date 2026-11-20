#include "lfj8_range_control.h"

#define HALF_CLOCK UINT32_C(0x80000000)
#define BUTTON_MASK (RBM_U340E_BUTTON_MODE | RBM_U340E_BUTTON_UP | \
                     RBM_U340E_BUTTON_DOWN | RBM_U340E_BUTTON_OVERDRIVE)

static int valid_range_bit(const Lfj8H03RangeBit *sample, uint32_t generation,
                           uint32_t age_us, uint32_t max_age_us)
{
    return sample->generation == generation && sample->valid == 1u &&
        sample->asserted <= 1u && max_age_us < HALF_CLOCK && age_us < max_age_us;
}

int lfj8_h03_range_snapshot(const Lfj8H03RangeInputs *inputs, const Lfj8H03RangeAgeLimits *limits,
                            uint32_t generation, uint32_t now_us, Lfj8H03RangeSnapshot *out)
{
    if (!out) {
        return 0;
    }
    *out = (Lfj8H03RangeSnapshot){0};
    if (!inputs || !limits) {
        return 0;
    }

    const Lfj8H03RangeBit *inhibit = &inputs->inhibit_5250_2;
    uint32_t oldest_age_us = now_us - inhibit->captured_us;
    if (!valid_range_bit(inhibit, generation, oldest_age_us, limits->inhibit_5250_2_us)) {
        return 0;
    }

    uint8_t range = 0;
    for (unsigned bit = 0; bit < 4u; ++bit) {
        const Lfj8H03RangeBit *sample = &inputs->range_5722[bit];
        const uint32_t age_us = now_us - sample->captured_us;
        if (!valid_range_bit(sample, generation, age_us, limits->range_5722_us[bit])) {
            return 0;
        }
        range |= (uint8_t)(sample->asserted << bit);
        if (age_us > oldest_age_us) {
            oldest_age_us = age_us;
        }
    }
    *out = (Lfj8H03RangeSnapshot){
        .oldest_us = now_us - oldest_age_us,
        .range_5722 = range,
        .inhibit_5250 = (uint8_t)(inhibit->asserted << 2),
    };
    return 1;
}

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

void lfj8_range_control_sample_selector(Lfj8RangeControl *control, Lfj8SelectorAdcReading reading,
                                        uint32_t now_us)
{
    if (reading.event == LFJ8_SELECTOR_ADC_CLOCK_LOST) {
        control->sampled = 0;
        control->selector = rbm_u340e_selector_sample(&control->filter, UINT16_MAX);
        return;
    }
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
    lfj8_range_control_sample_selector(control, reading, now_us);
    if (reading.event == LFJ8_SELECTOR_ADC_CLOCK_LOST) {
        control->controller.buttons_seen = 0;
        *output = (RbmU340eOutput){0};
        return 0;
    }
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

void lfj8_range_control_disarm_buttons(Lfj8RangeControl *control, Lfj8ButtonFilter *filter)
{
    disarm_buttons(filter);
    control->controller.buttons_seen = 0;
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
