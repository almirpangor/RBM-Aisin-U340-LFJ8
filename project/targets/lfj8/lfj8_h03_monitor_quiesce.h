#ifndef RBM_LFJ8_H03_MONITOR_QUIESCE_H
#define RBM_LFJ8_H03_MONITOR_QUIESCE_H

#include "lfj8_donor_io.h"

typedef struct {
    const Lfj8RegisterIo *io;
    void (*write16)(void *context, uint32_t address, uint16_t value);
    void (*write32)(void *context, uint32_t address, uint32_t value);
} Lfj8H03MonitorIo;

/* Configure both pairs of BasicCAN slots while both CAN modules are in
 * reset, with slots stopped and standard frame type already selected.
 * The caller holds the IRQ lock. Keep both modules in reset on failure. */
int lfj8_h03_monitor_configure_filters_locked(const Lfj8RegisterIo *io);

/* The CAN owner must retain the filters and prevent OEM recovery or queued
 * frame replay from reopening the monitor. Withdraw authority before
 * releasing ownership. */
int lfj8_h03_monitor_filters_locked(const Lfj8RegisterIo *io);

/* Enter from serialized foreground with outputs inhibited and with this
 * routine, its callees and the return path visible in the current map.
 * Confirm both CAN filters and empty BasicCAN receive slots under the IRQ
 * lock before discarding pending work. A failed readback leaves the caller
 * disarmed. This function does not qualify RAM placement or hardware. */
int lfj8_h03_monitor_quiesce(const Lfj8H03MonitorIo *monitor);

/* Recheck with the same owner lock. Admitted diagnostic traffic can set
 * TRFIN after handoff. The owner still excludes unfiltered replay. */
int lfj8_h03_monitor_isolated_locked(const Lfj8RegisterIo *io);

#endif
