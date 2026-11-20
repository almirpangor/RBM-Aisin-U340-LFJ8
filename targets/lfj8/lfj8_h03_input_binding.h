#ifndef RBM_LFJ8_H03_INPUT_BINDING_H
#define RBM_LFJ8_H03_INPUT_BINDING_H

#include "lfj8_h03_cycle.h"
#include "lfj8_h03_button_capture.h"

typedef struct {
    volatile Lfj8SelectorAdc *adc;
    Lfj8RangeControl *control;
    Lfj8ButtonFilter *button_filter;
    const Lfj8RegisterIo *io;
    const Lfj8H03RangeAgeLimits *range_limits;
    /* Optional immutable map for P1DATA stored with AN2. With this map,
     * sources.buttons must be NULL and every mapped button uses P1. */
    const Lfj8H03ButtonMap *p1_button_map;
} Lfj8H03InputBinding;

typedef struct {
    const Lfj8H03CycleInput *cycle; /* Qualified engine, event, GP and oldest upstream timestamp. */
    const RbmU340eInput *driver;   /* Gear observation, allowed mask, shift state, donor Auto. */
    const Lfj8H03RangeInputs *range;
    const Lfj8ButtonReading *buttons; /* Current-generation, normalized board capture or NULL. */
    uint32_t generation;
    uint32_t now_us;
} Lfj8H03InputSources;

typedef struct {
    Lfj8H03CycleInput cycle;
    RbmU340eOutput driver;
} Lfj8H03InputProposal;

/* Foreground owner supplies disjoint, coherent snapshots and uses the same
 * qualified wrapping clock for all captures and now_us. Reinitialize the
 * existing ADC, selector and button state on a new acquisition epoch.
 * Upstream qualification and command_at also cover the driver operands.
 * Invoke once per candidate step and consume the button capture once.
 * Failure clears the proposal. Use no cycle inputs or gear request on failure.
 * On success the gear request remains a logical proposal for the cycle owner. */
int lfj8_h03_input_propose(const Lfj8H03InputBinding *binding, const Lfj8H03InputSources *sources,
                           Lfj8H03InputProposal *out);

#endif
