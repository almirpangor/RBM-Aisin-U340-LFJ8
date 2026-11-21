#ifndef RBM_LFJ8_H03_INPUT_BINDING_H
#define RBM_LFJ8_H03_INPUT_BINDING_H

#include "lfj8_h03_cycle.h"
#include "lfj8_h03_button_capture.h"
#include "lfj8_h03_sensor_feed.h"

typedef struct {
    volatile Lfj8SelectorAdc *adc;
    Lfj8RangeControl *control;
    Lfj8ButtonFilter *button_filter;
    const Lfj8RegisterIo *io;
    const Lfj8H03RangeAgeLimits *range_limits;
    /* Optional immutable map for P1DATA stored with AN2. With this map,
     * sources.buttons must be NULL and every mapped button uses P1. */
    const Lfj8H03ButtonMap *p1_button_map;
    /* Maximum qualified time from admission to completed shift, in us. */
    uint32_t manual_max_age_us;
    /* Immutable windows validated on startup. NULL keeps legacy callers. */
    const RbmU340eSelectorProfile *selector_profile;
} Lfj8H03InputBinding;

typedef struct {
    RbmU340ePolicy policy;
    uint32_t selector_max_age_us;
    uint32_t button_debounce_us;
    uint32_t button_max_age_us;
} Lfj8H03InputStartup;

/* Prepare the selector and button owners while their lifecycle gate is closed.
 * The caller owns the RAM and resets the ADC mailbox on the same epoch. */
int lfj8_h03_input_startup(const Lfj8H03InputBinding *binding, const Lfj8H03InputStartup *startup);

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

typedef struct {
    const Lfj8H03InputBinding *binding;
    Lfj8H03InputProposal *proposal;
    void *platform;
    int (*ram_owned)(void *platform); /* Called under binding->io. */
    /* Supply qualified non-engine cycle data, load and coherent driver/range
     * pointers valid through the capture. Set load.now_us in the sensor epoch.
     * Foreground capture owns selector/buttons; leave sources->buttons NULL. */
    int (*read)(void *platform, const Lfj8H03SensorSnapshot *sensors, uint32_t due_at,
                Lfj8H03CycleInput *input, Lfj8H03CycleLoad *load, Lfj8H03InputSources *sources);
} Lfj8H03ToyotaInputCapture;

/* Set Lfj8H03ToyotaSource.capture to this function and its platform pointer to
 * the immutable capture context. Use disjoint cycle and proposal workspace.
 * The application attaches its engine qualifier after take_toyota and
 * reinitializes range control, buttons and capture epoch on each startup.
 * Supply a qualified manual age in (0, 2^31). */
int lfj8_h03_input_capture_toyota(void *context, const Lfj8H03SensorSnapshot *sensors,
                                  uint32_t due_at, Lfj8H03CycleInput *input,
                                  Lfj8H03CycleLoad *load);

#endif
