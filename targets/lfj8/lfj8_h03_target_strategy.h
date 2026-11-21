#ifndef RBM_LFJ8_H03_TARGET_STRATEGY_H
#define RBM_LFJ8_H03_TARGET_STRATEGY_H

#include "lfj8_h03_cycle.h"

typedef struct {
    const Lfj8H03ActuatorCalibration *actuators;
    Lfj8H03OemOutputState oem;
    Lfj8H03OperatingPoint operating; /* ATF tenths of a degree C and supply millivolts. */
} Lfj8H03StrategySnapshot;

/* The output profile owns FAST and supplies a coherent, current hardware
 * snapshot for the consumed H03 release. Called under the takeover's native
 * lock with owned RAM. Return 1 only after qualifying provenance, validity,
 * phase alignment with MAIN/FAST, the actual output path and calibration.
 * Set out->oem.current only for that qualified snapshot. No output writes,
 * wait or reentry. On any unavailable input, return 0. */
int rbm_h03_target_strategy_snapshot(void *context, uint32_t phase_sequence,
                                     Lfj8H03StrategySnapshot *out);

/* Absolute alias of the existing communication/fast_output field. */
extern Lfj8H03FastOutput rbm_h03_fast_output;

#endif
