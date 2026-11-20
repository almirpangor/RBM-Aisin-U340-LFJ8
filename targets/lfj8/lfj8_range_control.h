#ifndef RBM_LFJ8_RANGE_CONTROL_H
#define RBM_LFJ8_RANGE_CONTROL_H

#include "lfj8_selector_adc.h"
#include "rbm_u340e.h"

typedef struct {
    RbmU340eController controller;
    RbmU340eSelectorInput filter;
    uint32_t max_age_us;
    uint32_t last_sample_us;
    uint8_t sampled;
    uint8_t selector;
} Lfj8RangeControl;

typedef struct {
    uint32_t captured_us;
    uint8_t pressed; /* Active-high RBM_U340E_BUTTON_* bits after board mapping. */
    uint8_t valid; /* Exactly 1 for a fresh, coherent snapshot. */
} Lfj8ButtonReading;

typedef struct {
    uint32_t debounce_us;
    uint32_t max_age_us;
    uint32_t last_sample_us;
    uint32_t candidate_since_us;
    uint8_t sampled;
    uint8_t candidate_valid;
    uint8_t candidate;
    uint8_t stable;
    uint8_t armed;
} Lfj8ButtonFilter;

/* Use the target scheduler's measured sample period to configure max_age_us. */
int lfj8_range_control_init(Lfj8RangeControl *control, const RbmU340ePolicy *policy,
                            uint32_t max_age_us);

/* Poll after taking the mailbox event, using the same wrapping counter as
 * the ADC producer. Reinitialize on a counter reset.
 * The step supplies logical output proposals. */
int lfj8_range_control_step(Lfj8RangeControl *control, Lfj8SelectorAdcReading reading,
                            uint32_t now_us,
                            const RbmU340eInput *input, RbmU340eOutput *output);

/* Configure both intervals in microseconds from measured input timing. Each
 * interval must be nonzero and shorter than half the wrapping clock period. */
int lfj8_button_filter_init(Lfj8ButtonFilter *filter, uint32_t debounce_us, uint32_t max_age_us);

/* Use after initializing both states, in place of lfj8_range_control_step.
 * Pass each coherent capture once, NULL when idle, and valid=0 on known loss
 * or overrun. Unmapped channels must remain released. All times use the ADC
 * clock. Reinitialize both states after a clock reset. This path supplies
 * selector, stable_buttons and buttons_valid to the existing controller. */
int lfj8_range_control_step_with_buttons(Lfj8RangeControl *control, Lfj8SelectorAdcReading selector,
    Lfj8ButtonFilter *filter, const Lfj8ButtonReading *buttons, uint32_t now_us,
    const RbmU340eInput *input, RbmU340eOutput *output);

#endif
