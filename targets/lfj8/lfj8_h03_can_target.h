#ifndef RBM_LFJ8_H03_CAN_TARGET_H
#define RBM_LFJ8_H03_CAN_TARGET_H

#include "lfj8_h03_dtc_target.h"

/* Use the target bound by lfj8_h03_dtc_native_bind after the application has
 * qualified TML0 and initialized the broker. Call only with RAM owned.
 * The application supplies the diagnostic T6 tick and confirms that the
 * native TX13 gate is installed. The guarded monitor supplies CAN readiness.
 * IRQ and foreground share the DTC target, CAN owner and TML0 clock. */
Lfj8H03Can13Result lfj8_h03_can_target_poll(Lfj8H03DtcTarget *target,
                                         Lfj8H03Can13Input *input, bool tx_gate_ready);

#endif
