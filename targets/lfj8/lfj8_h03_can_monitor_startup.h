#ifndef RBM_LFJ8_H03_CAN_MONITOR_STARTUP_H
#define RBM_LFJ8_H03_CAN_MONITOR_STARTUP_H

#include "lfj8_h03_monitor_quiesce.h"

/* The constants, code and all callees must be visible in the current Flash
 * map. The target binding holds command authority withdrawn until the
 * protection and CAN generation are confirmed. */
extern const Lfj8H03MonitorIo rbm_h03_can_monitor_io;

/* Cold entry only, with interrupts masked and both controllers in reset.
 * Return 1 after initializing the shared owner, or 0 if its RAM is unowned. */
int rbm_h03_can_monitor_cold_owner_init_locked(void);

/* Runtime-only, called with interrupts masked before any reconfiguration.
 * Withdraw the shared CAN generation's grant and invoke the confirmed
 * output inhibit. Never called by the cold entry before RAM ownership. */
void rbm_h03_can_monitor_revoke_locked(void);

/* Runtime permit only, after both controllers pass release readback.
 * Publish a setup generation without granting RX/TX. The foreground owner
 * admits it after the OEM tail and the hardware drain check. */
void rbm_h03_can_monitor_publish_setup_locked(void);

int rbm_h03_can_monitor_rearm(void);
int rbm_h03_can_monitor_runtime_rearm(void);
int rbm_h03_can_monitor_prepare_recovery(void);

#endif
