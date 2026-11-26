#ifndef RBM_LFJ8_H03_TORQUE_CAN_H
#define RBM_LFJ8_H03_TORQUE_CAN_H

#include "lfj8_donor_io.h"
#include "lfj8_h03_torque.h"

typedef struct {
    Lfj8H03Torque request;
    uint32_t generation;
    uint32_t polled_at_us;
    uint32_t tick_changed_at_us;
    uint32_t completion_observed_at_us;
    uint16_t previous_tick;
    uint16_t completed_tick;
    uint16_t max_receive_age_bits;
    uint16_t max_poll_gap_us;
    uint8_t bit_time_us;
    bool clock_seen;
    bool need_drain;
    bool need_status_after_completion;
    bool lease_lost;
} Lfj8H03TorqueCan;

typedef enum {
    LFJ8_H03_TORQUE_CAN_RESERVED,
    LFJ8_H03_TORQUE_CAN_RELEASED,
    LFJ8_H03_TORQUE_CAN_UNAVAILABLE,
} Lfj8H03TorqueCanSlot;

/* bit_time_us comes from the configured and qualified bus bitrate. */
bool lfj8_h03_torque_can_init(Lfj8H03TorqueCan *adapter, uint16_t max_receive_age_bits,
                               uint16_t max_poll_gap_us, uint8_t bit_time_us);

/* The foreground CAN owner must exclude all stock slot13 writers and mask
 * the slot IRQ. Serialize every poll with controller reinitialization and
 * all other senders. While another transport needs to use slot13, pass
 * yield_slot13 until that transport has drained all its transmissions.
 * It may take the slot only after RELEASED. Advance generation only after
 * reset/reinitialization or after all in-flight work is drained. */
Lfj8H03TorqueCanSlot lfj8_h03_torque_can_poll(
    Lfj8H03TorqueCan *adapter, const Lfj8RegisterIo *io, uint8_t slot13_owned,
    bool yield_slot13, uint32_t generation, uint32_t now_us,
    const Lfj8TorqueInput *input, const Lfj8TorqueCalibration *cal);

#endif
