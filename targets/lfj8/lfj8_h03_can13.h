#ifndef RBM_LFJ8_H03_CAN13_H
#define RBM_LFJ8_H03_CAN13_H

#include "lfj8_chery_tx.h"
#include "lfj8_h03_dtc_can.h"
#include "lfj8_h03_torque_can.h"

typedef struct {
    Lfj8H03TorqueCan torque;
    Lfj8H03DtcCan diagnostic;
    Lfj8CheryTx status;
    uint32_t generation;
    uint32_t status_started_us;
    uint8_t status_in_flight;
    uint8_t counter_before_status;
    bool status_during_reduction;
    bool lease_seen;
    bool lease_lost;
    bool initialized;
} Lfj8H03Can13;

typedef struct {
    uint32_t period_1ae_us;
    uint32_t period_300_us;
    uint16_t torque_receive_age_bits;
    uint16_t diagnostic_receive_age_bits;
    uint16_t max_poll_gap_us;
    uint8_t bit_time_us;
} Lfj8H03Can13Config;

typedef struct {
    uint32_t generation;
    uint32_t now_us;
    uint32_t diagnostic_tick;
    uint8_t owns_slot13;
    uint8_t status_due; /* LFJ8_DUE_* releases from a qualified external schedule. */
    const Lfj8TorqueInput *torque;
    const Lfj8TorqueCalibration *torque_calibration;
    CheryDtcState *dtc;
    const Lfj8H03DtcReceive *received;
    volatile Lfj8RawVss *vss;
    const Lfj8VehicleCalibration *vehicle;
    const Lfj8CheryTxInputs *status;
} Lfj8H03Can13Input;

typedef struct {
    bool available;
    bool diagnostic_consumed;
    uint8_t status_submitted; /* LFJ8_DUE_1AE or LFJ8_DUE_300 on admission. */
} Lfj8H03Can13Result;

bool lfj8_h03_can13_init(Lfj8H03Can13 *broker, const Lfj8H03Can13Config *config,
                         uint32_t now_us);

/* One foreground owner polls within max_poll_gap_us. Grant only after the
 * OEM TX paths have yielded and the individual IRQ has been masked.
 * Serialize with CAN reinitialization, DTC state and all slot13 writers.
 * Change generation on reset/reinitialization or after a verified drain.
 * An observed loss of a live grant requires a new generation, even if no
 * transmission was pending. Availability alone only describes the lease.
 *
 * Set dtc to the live DTC state. BasicCAN input is the head of the caller's
 * RX queue. Remove the head when diagnostic_consumed is set. Drop captures
 * before half a timestamp wrap even if the broker is busy. Torque input
 * and the status inputs are optional, with one owner of their data.
 * Status needs qualified frame operands in status. Missing vehicle
 * calibration or S51 input produces unavailable speed in 0x1AE. 0x300
 * does not depend on either speed input. */
Lfj8H03Can13Result lfj8_h03_can13_poll(Lfj8H03Can13 *broker, const Lfj8RegisterIo *io,
                                      const Lfj8H03Can13Input *input);

#endif
