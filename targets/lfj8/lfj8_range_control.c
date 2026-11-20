#include "lfj8_range_control.h"

#define HALF_CLOCK UINT32_C(0x80000000)

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
