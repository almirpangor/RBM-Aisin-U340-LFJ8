#ifndef RBM_CHERY_ATF_CIRCUIT_H
#define RBM_CHERY_ATF_CIRCUIT_H

#include "chery_dtc.h"

typedef enum {
    CHERY_ATF_CIRCUIT_SKIPPED,
    CHERY_ATF_CIRCUIT_IN_RANGE,
    CHERY_ATF_CIRCUIT_OUT_OF_RANGE
} CheryAtfCircuitSample;

typedef struct {
    uint8_t count;
} CheryAtfCircuit;

/* Reset at startup and when the diagnostic owner handles an accepted clear. */
void chery_atf_circuit_reset(CheryAtfCircuit *monitor);

/* Call once per monitor opportunity under the DTC owner.
 * SKIPPED preserves the counter and status (for example, invalid reference).
 * The caller qualifies sample freshness, reference and sensor range. */
void chery_atf_circuit_step(CheryAtfCircuit *monitor, CheryDtcState *dtc,
                            CheryAtfCircuitSample sample, bool inhibit_history);

#endif
