#ifndef RBM_LFJ8_H03_DTC_NATIVE_H
#define RBM_LFJ8_H03_DTC_NATIVE_H

#include "lfj8_h03_dtc_target.h"

/* Call only with exclusive ownership of the H03 communication RAM.
 * Before native setup or hooked IRQs can run on cold entry, unbind RX and
 * initialize h03_can_owner. Warm closure unbinds RX without resetting the
 * setup generation. Serialize lifecycle calls with the OEM foreground. */
void lfj8_h03_dtc_native_cold_init(void);
void lfj8_h03_dtc_native_unbind(void);

/* Bind the single IRQ target to the initialized CAN13 broker once the
 * application has qualified TML0. Supply objects from the typed RAM inventory.
 * The RX adapter, its read-only ops table, native clock/MMIO and RX callees
 * must be resident below application Flash along with the IRQ wrappers. */
bool lfj8_h03_dtc_native_bind(Lfj8H03DtcTarget *target, Lfj8H03Can13 *broker,
                              uint16_t max_clock_span_us);

/* Call in CAN foreground with the live DTC state and diagnostic T6 tick.
 * native_ready is supplied by the installed CAN setup/monitor and TX gate.
 * The entire turn is serialized with RX and clock changes by the native lock. */
Lfj8H03Can13Result lfj8_h03_dtc_native_poll(Lfj8H03DtcTarget *target,
                                          Lfj8H03Can13Input *input, bool native_ready);

#endif
