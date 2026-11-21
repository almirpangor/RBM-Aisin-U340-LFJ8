#ifndef RBM_LFJ8_H03_TARGET_PLATFORM_H
#define RBM_LFJ8_H03_TARGET_PLATFORM_H

#include "lfj8_h03_toyota_source.h"

/* The final RAM map binds this single foreground-owned release state.
 * Only the startup/foreground platform may access it. The live memory owner
 * must cover its entire extent before either callback accesses it. */
extern Lfj8H03ToyotaRelease rbm_h03_toyota_release_state;

/* In addition to the application settings, the qualified profile defines:
 *
 * RBM_H03_PROFILE_TOYOTA_PERIOD_TICKS and
 * RBM_H03_PROFILE_TOYOTA_MAX_LATENESS_TICKS: integer constants in
 * continuous H03 TML0 ticks, consistent with the application watchdog.
 *
 * RBM_H03_PROFILE_INITIALIZE_INPUTS: int (void *context).
 * Reset the single owners of the board input producers for cold/warm startup
 * with the app gate closed and outputs inhibited. Also initialize or restore
 * the one shared DTC state. Called in serialized foreground outside the IRQ
 * lock. Return 1 only on successful preparation.
 *
 * RBM_H03_PROFILE_CAN_SERVICE_CONFIG names an immutable qualified
 * Lfj8H03TargetServiceConfig. After inputs are prepared and RAM and clock
 * are rechecked under the lock, the platform prepares CAN before returning
 * success. Live IRQ/TX admission follows on the first qualified phase.
 *
 * RBM_H03_PROFILE_CAPTURE_TOYOTA names a function:
 * int (void *context, const Lfj8H03SensorSnapshot *sensors, uint32_t due_at,
 *      Lfj8H03CycleInput *input, Lfj8H03CycleLoad *load).
 * Acquire the qualified load/driver operands using the supplied snapshot.
 * Preserve producer timestamps and load lifetime; the release owner assigns
 * the event number, and the application supplies its shared CAN engine feed.
 * Return 1 only when the complete required input set is usable. */

#endif
