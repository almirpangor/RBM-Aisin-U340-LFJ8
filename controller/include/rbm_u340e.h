#ifndef RBM_U340E_H
#define RBM_U340E_H

#include <stdint.h>

#include "factory_core.h"
#include "factory_correction.h"
#include "factory_outputs.h"

enum {
    RBM_U340E_AUTO = 0,
    RBM_U340E_TIPTRONIC = 1,
    RBM_U340E_OVERDRIVE_AUTO = 1u << RBM_U340E_AUTO,
    RBM_U340E_OVERDRIVE_TIPTRONIC = 1u << RBM_U340E_TIPTRONIC
};

enum {
    RBM_U340E_SELECTOR_UNKNOWN = 0,
    RBM_U340E_SELECTOR_P = 1,
    RBM_U340E_SELECTOR_R = 2,
    RBM_U340E_SELECTOR_N = 3,
    RBM_U340E_SELECTOR_D = 4,
    RBM_U340E_SELECTOR_2 = 5,
    RBM_U340E_SELECTOR_L = 6,
    RBM_U340E_FORWARD_SELECTORS = (1u << RBM_U340E_SELECTOR_D) |
        (1u << RBM_U340E_SELECTOR_2) | (1u << RBM_U340E_SELECTOR_L)
};

typedef struct {
    uint8_t candidate;
    uint8_t samples;
} RbmU340eSelectorInput;

/* Zero-initialize the state. Call once per scheduled ADC sample.
 * Input code is 0..1023 on the 5 V scale. Pass UINT16_MAX if the sample
 * is unavailable. Four consecutive samples in one window qualify a range. */
uint8_t rbm_u340e_selector_sample(RbmU340eSelectorInput *state, uint16_t adc);

enum {
    RBM_U340E_BUTTON_MODE = 1u << 0,
    RBM_U340E_BUTTON_UP = 1u << 1,
    RBM_U340E_BUTTON_DOWN = 1u << 2,
    RBM_U340E_BUTTON_OVERDRIVE = 1u << 3
};

enum {
    RBM_U340E_RELAY_REVERSE = 1u << 0,
    RBM_U340E_RELAY_AUXILIARY = 1u << 1,
    RBM_U340E_DONOR_CHANNEL_S1 = 0,
    RBM_U340E_DONOR_CHANNEL_S2 = 1,
    RBM_U340E_DONOR_CHANNEL_ST = 5
};

typedef struct {
    uint8_t manual_selectors; /* Bit n authorizes selector number n. */
    uint8_t overdrive_limit_modes; /* Modes in which OD Off removes fourth gear. */
    uint8_t initial_mode;
    uint8_t initial_overdrive_enabled;
} RbmU340ePolicy;

typedef struct {
    RbmU340ePolicy policy;
    uint8_t mode;
    uint8_t overdrive_enabled;
    uint8_t buttons_seen;
    uint8_t previous_buttons;
} RbmU340eController;

typedef struct {
    FactoryRequestState auto_request; /* Coherent Toyota raw snapshot. */
    uint8_t selector;
    uint8_t stable_buttons; /* Board-level debouncing precedes this call. */
    uint8_t buttons_valid;
    uint8_t actual_gear; /* 1..4, 0 if a forward gear is unconfirmed. */
    uint8_t allowed_gears; /* Bit (gear - 1), including all external limits. */
    uint8_t auto_request_valid;
    uint8_t shifting;
} RbmU340eInput;

typedef struct {
    FactoryRequestState auto_request; /* Caller can retain a successful step. */
    uint8_t mode;
    uint8_t overdrive_enabled;
    uint8_t overdrive_pressed;
    uint8_t conflicting_buttons;
    uint8_t relay_mask;
    uint8_t requested_gear; /* 0 means no qualified logical target. */
    uint8_t auto_request_valid;
} RbmU340eOutput;

/* Both calls return 1 on success. Init validates every policy field. Step
 * requires an initialized controller and returns a proposal in gear units.
 * If an input snapshot is absent or rejected, the next valid button sample
 * establishes the baseline, with the current mode and Overdrive retained. */
int rbm_u340e_init(RbmU340eController *controller, const RbmU340ePolicy *policy);
int rbm_u340e_step(RbmU340eController *controller, const RbmU340eInput *input,
    RbmU340eOutput *output);

typedef struct {
    FactoryDriverState driver[3]; /* Donor channels 0, 1 and 5. */
} RbmU340eOutputState;

typedef struct {
    FactoryShiftOutputState shift;
    FactorySTOutputState st;
    FactoryPressureCorrection slt;
    FactorySLTInputs slt_inputs;
    int8_t driver_status[3]; /* Signed donor status for channels 0, 1 and 5. */
    uint8_t qualified; /* All raw state fields and driver status are coherent. */
} RbmU340eHydraulicInput;

typedef struct {
    FactoryShiftOutputState shift;
    FactorySTOutputState st;
    FactoryPressureCorrection slt;
    FactorySLTResult slt_result; /* Donor raw units. */
    uint8_t write_count;
    FactoryDriverWrite writes[5]; /* Ordered, logical donor channel changes. */
} RbmU340eHydraulicOutput;

/* Initialize output state using a coherent donor driver snapshot. */
int rbm_u340e_outputs_init(RbmU340eOutputState *state,
    const FactoryDriverState snapshot[3]);

/* Compute logical commands for the caller's qualified hydraulic snapshot.
 * Caller owns donor task timing, state propagation and physical actuation.
 * Output is caller-owned scratch until return. On failure returns zero,
 * clears output and preserves driver state. */
int rbm_u340e_outputs_step(RbmU340eOutputState *state,
    const RbmU340eHydraulicInput *input, RbmU340eHydraulicOutput *output);

#endif
