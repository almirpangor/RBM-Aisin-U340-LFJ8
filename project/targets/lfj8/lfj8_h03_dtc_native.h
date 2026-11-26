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
 * must be resident below application Flash along with the IRQ wrappers.
 * Binding requires durable diagnostic clears. Until persistent storage is
 * connected, a valid clear is consumed without changing DTC or sending ACK. */
bool lfj8_h03_dtc_native_bind(Lfj8H03DtcTarget *target, Lfj8H03Can13 *broker,
                              uint16_t max_clock_span_us);

/* Call in CAN foreground with the live DTC state and diagnostic T6 tick.
 * native_ready is supplied by the installed CAN setup/monitor and TX gate.
 * The entire turn is serialized with RX and clock changes by the native lock. */
Lfj8H03Can13Result lfj8_h03_dtc_native_poll(Lfj8H03DtcTarget *target,
                                          Lfj8H03Can13Input *input, bool native_ready);

typedef struct {
    uint32_t period_us_numerator;
    uint32_t period_us_denominator;
    uint32_t max_sample_gap_us;
} Lfj8H03DtcT6Config;

/* Validate timing bounds without starting or sampling TML0. */
bool lfj8_h03_dtc_t6_config_valid(const Lfj8H03DtcT6Config *config);

typedef struct {
    Lfj8H03DtcT6Config config;
    uint32_t sampled_us;
    uint32_t tick;
    uint32_t remainder;
    bool active;
    uint8_t status_phase;
} Lfj8H03DtcT6Clock;

/* The application owns this foreground-only state. Supply the verified T6
 * period as a fraction of a microsecond, at least 1 us, and a measured upper
 * bound on consecutive sampling gaps, less than half a TML0 wrap. The low
 * bits of initial_tick determine the donor task phase at the first sample.
 * Start after TML0 qualification and before admitting CAN. Rephase only
 * with CAN admission closed. With status_from_t6, initial_tick also sets the
 * S03 status phase modulo 12. Use a broker with its local status periods
 * disabled. On a timer reconfiguration run the normal
 * unbind/clock qualification/startup path before reusing this state. */
bool lfj8_h03_dtc_native_start_t6(Lfj8H03DtcT6Clock *clock,
                                  const Lfj8H03DtcT6Config *config, uint32_t initial_tick,
                                  bool status_from_t6);

/* Use in place of native_poll when the application supplies T6 from TML0.
 * Advances the wrapping T6 tick and writes it to input->diagnostic_tick.
 * Loss of qualified time or an excessive sample gap disables the source
 * and withdraws CAN admission. A stopped source must be started explicitly.
 * An unavailable turn still runs the broker's ordinary revocation path. */
Lfj8H03Can13Result lfj8_h03_dtc_native_poll_t6(Lfj8H03DtcTarget *target,
                                             Lfj8H03Can13Input *input, bool native_ready,
                                             Lfj8H03DtcT6Clock *clock);

#endif
