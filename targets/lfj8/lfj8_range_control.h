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

/* Use the target scheduler's measured sample period to configure max_age_us. */
int lfj8_range_control_init(Lfj8RangeControl *control, const RbmU340ePolicy *policy,
                            uint32_t max_age_us);

/* Poll after taking the mailbox event, using the same wrapping counter as
 * the ADC producer. Reinitialize on a counter reset.
 * The step supplies logical output proposals. */
int lfj8_range_control_step(Lfj8RangeControl *control, Lfj8SelectorAdcReading reading,
                            uint32_t now_us,
                            const RbmU340eInput *input, RbmU340eOutput *output);

#endif
