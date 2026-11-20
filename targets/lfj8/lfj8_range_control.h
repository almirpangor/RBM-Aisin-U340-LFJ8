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
    uint32_t generation;
    uint8_t asserted; /* Normalized to the polarity of the Toyota operand. */
    uint8_t valid;    /* Exactly 1 after source-specific qualification. */
} Lfj8H03RangeBit;

typedef struct {
    Lfj8H03RangeBit range_5722[4]; /* One independently qualified input per bit. */
    Lfj8H03RangeBit inhibit_5250_2; /* Independently qualified engine input. */
} Lfj8H03RangeInputs;

typedef struct {
    uint32_t range_5722_us[4];
    uint32_t inhibit_5250_2_us;
} Lfj8H03RangeAgeLimits;

typedef struct {
    uint32_t oldest_us; /* Oldest capture used to produce the two operands. */
    uint8_t range_5722;
    uint8_t inhibit_5250;
} Lfj8H03RangeSnapshot;

/* Assemble the range operands from a coherent caller-owned copy. The channels
 * have their own verified producers independent of the selector decoder.
 * Use the same wrapping clock and acquisition generation for all inputs.
 * Restart acquisition with a new generation on clock reset or a gap of at
 * least half the clock range. Age limits are positive, exclusive and below
 * half the clock range. Failure clears out. The caller also qualifies the
 * selector and the remaining operands before publishing a cycle snapshot.
 */
int lfj8_h03_range_snapshot(const Lfj8H03RangeInputs *inputs, const Lfj8H03RangeAgeLimits *limits,
                            uint32_t generation, uint32_t now_us, Lfj8H03RangeSnapshot *out);

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

/* Update only the ADC state of an initialized control, without button edges
 * or a gear proposal. A reported fault invalidates the range regardless of
 * its timestamp. Only fresh, ordered events advance the capture watermark. */
void lfj8_range_control_sample_selector(Lfj8RangeControl *control, Lfj8SelectorAdcReading reading,
                                        uint32_t now_us);

/* Poll after taking the mailbox event, using the same wrapping counter as
 * the ADC producer. Reinitialize on a counter reset.
 * The step supplies logical output proposals. */
int lfj8_range_control_step(Lfj8RangeControl *control, Lfj8SelectorAdcReading reading,
                            uint32_t now_us,
                            const RbmU340eInput *input, RbmU340eOutput *output);

/* Configure both intervals in microseconds from measured input timing. Each
 * interval must be nonzero and shorter than half the wrapping clock period. */
int lfj8_button_filter_init(Lfj8ButtonFilter *filter, uint32_t debounce_us, uint32_t max_age_us);

/* Inhibit driver changes until new captures establish a released baseline.
 * Retains the current mode, OD state and button capture watermark. */
void lfj8_range_control_disarm_buttons(Lfj8RangeControl *control, Lfj8ButtonFilter *filter);

/* Use after initializing both states, in place of lfj8_range_control_step.
 * Pass each coherent capture once, NULL when idle, and valid=0 on known loss
 * or overrun. An explicit fault or malformed reading disarms the buttons
 * even without a usable capture time. Only fresh, ordered captures advance
 * the timestamp. Unmapped channels must remain released. All times use the ADC
 * clock. Reinitialize both states after a clock reset. This path supplies
 * selector, stable_buttons and buttons_valid to the existing controller. */
int lfj8_range_control_step_with_buttons(Lfj8RangeControl *control, Lfj8SelectorAdcReading selector,
    Lfj8ButtonFilter *filter, const Lfj8ButtonReading *buttons, uint32_t now_us,
    const RbmU340eInput *input, RbmU340eOutput *output);

#endif
