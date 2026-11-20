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

/* On every admitted H03 foreground pass, take one mailbox event and update
 * selector and button qualification without advancing the mode or consuming
 * controller edges. NULL selects the native P1 map when one is configured,
 * or means no fresh external capture otherwise. Return 1 while both inputs
 * are ready. The owner must withhold output while they are unqualified. */
int lfj8_h03_input_capture(const Lfj8H03InputBinding *binding, const Lfj8ButtonReading *buttons,
                          uint32_t now_us);

/* For one new Toyota event, use the latest qualified input state from capture.
 * No mailbox is read here. Supply disjoint, coherent objects and a common
 * qualified wrapping clock. Upstream qualification and command_at also cover
 * the driver operands. For native P1, keep sources->buttons NULL.
 * Failure clears the proposal; a gear request is logical until admitted by
 * the cycle owner. Reinitialize ADC, selector and buttons on a new epoch. */
int lfj8_h03_input_propose_captured(const Lfj8H03InputBinding *binding,
    const Lfj8H03InputSources *sources, Lfj8H03InputProposal *out);

/* Combined entry point for callers using a single foreground/Toyota step. */
int lfj8_h03_input_propose(const Lfj8H03InputBinding *binding, const Lfj8H03InputSources *sources,
                           Lfj8H03InputProposal *out);

#endif
