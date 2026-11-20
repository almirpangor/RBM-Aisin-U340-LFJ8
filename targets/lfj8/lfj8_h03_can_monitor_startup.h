#ifndef RBM_LFJ8_H03_CAN_MONITOR_STARTUP_H
#define RBM_LFJ8_H03_CAN_MONITOR_STARTUP_H

#include "lfj8_h03_monitor_quiesce.h"

/* The constants, code and all callees must be visible in the current Flash
 * map. The target binding holds command authority withdrawn until the
 * protection and CAN generation are confirmed. */
extern const Lfj8H03MonitorIo rbm_h03_can_monitor_io;

/* Runtime-only, called with interrupts masked before any reconfiguration.
 * Withdraw the shared CAN generation's grant and invoke the confirmed
 * output inhibit. Never called by the cold entry before RAM ownership. */
void rbm_h03_can_monitor_revoke_locked(void);

int rbm_h03_can_monitor_rearm(void);
int rbm_h03_can_monitor_runtime_rearm(void);
int rbm_h03_can_monitor_prepare_recovery(void);

#endif
