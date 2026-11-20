#ifndef RBM_TA2005_CHERY_INPUTS_H
#define RBM_TA2005_CHERY_INPUTS_H

#include <stdint.h>

typedef struct {
    uint32_t speed_received_at;
    uint32_t coolant_received_at;
    uint16_t speed_fad8;
    uint8_t coolant_f9e9;
    uint8_t received;
} Ta2005CheryInputs;

typedef struct {
    uint16_t speed_fad8;
    uint8_t coolant_f9e9;
    uint8_t usable;
} Ta2005CherySnapshot;

enum { TA2005_CHERY_SPEED = 1, TA2005_CHERY_COOLANT = 2 };

/* Call from one owner, or serialize receive, snapshot and reset. Timestamps
 * come from the same monotonic clock at frame reception, before queuing.
 * Reset on bus-off or clock reinitialization. The snapshot supplies raw
 * receiver operands for input qualification; it grants no output permit. */
void ta2005_chery_inputs_reset(Ta2005CheryInputs *state);
unsigned ta2005_chery_inputs_receive(Ta2005CheryInputs *state, uint16_t id,
                                   uint16_t standard_data_dlc, const uint8_t *payload,
                                   const uint32_t *received_at);
unsigned ta2005_chery_inputs_snapshot(const Ta2005CheryInputs *state, const uint32_t *now,
                                    uint16_t maximum_age, Ta2005CherySnapshot *out);

#endif
