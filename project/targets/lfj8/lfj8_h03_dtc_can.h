#ifndef RBM_LFJ8_H03_DTC_CAN_H
#define RBM_LFJ8_H03_DTC_CAN_H

#include "chery_dtc_link.h"
#include "lfj8_donor_io.h"

typedef struct {
    CheryDtcCanFrame frame;
    uint32_t generation;
    uint16_t can_timestamp;
} Lfj8H03DtcReceive;

typedef struct {
    CheryDtcLink link;
    uint32_t generation;
    uint32_t session_clock_tick;
    uint16_t max_receive_age_bits;
    uint16_t first_frame_finished_at;
    uint8_t submission;
    bool session_clock_seen;
    bool require_durable_clear; /* Set by the native binding. */
} Lfj8H03DtcCan;

typedef enum {
    LFJ8_H03_DTC_SLOT_FREE,
    LFJ8_H03_DTC_SLOT_RESERVED,
    LFJ8_H03_DTC_NO_OWNERSHIP,
} Lfj8H03DtcSlotUse;

/* H03 CAN0 timestamp increments once per bus bit. Set the RX age budget
 * below half a wrap. Reinitialize only after CAN reset or a drained slot. */
bool lfj8_h03_dtc_can_init(Lfj8H03DtcCan *state, uint16_t max_receive_age_bits);

/* One consumed session scheduler event, serialized with poll and CAN
 * reinitialization. Deliver due expiry before the next request. On expiry
 * poll drains an outstanding submission with the normal TX13 lease rules. */
bool lfj8_h03_dtc_can_session_step(Lfj8H03DtcCan *state);

/* Called once per CAN foreground turn, before dispatching RX. Low T6 tick
 * bits represent the donor scheduler phase. Task 12 is due at 40/C0 hex.
 * Several releases between polls coalesce into one. True requests an RX
 * flush after session expiry or a discontinuity in the same CAN generation. */
bool lfj8_h03_dtc_can_service_session(Lfj8H03DtcCan *state, uint32_t generation, uint32_t tick);

/* Decode a coherent 16-byte copy of BasicCAN slot 14/15. Supply the
 * control byte captured before clearing TRFIN and the slot's EXTID bit.
 * The dispatcher validates that the slot stayed stable during the copy. */
bool lfj8_h03_dtc_can_decode_basic(Lfj8H03DtcReceive *received, const uint8_t slot[16],
                                  uint8_t control, bool extended, uint32_t generation);

/* Single foreground CAN owner, serialized with DTC state, other senders
 * and CAN reinitialization. The ownership grant covers the OEM TX paths
 * and IRQ callback, which must not reuse slot 13 behind the active token.
 * Keep other senders out of slot 13 while this returns RESERVED.
 * Losing the grant during a submission requires a new CAN generation
 * before this client can transmit again.
 *
 * Pass a coherent frame captured by the RX dispatcher, with the true
 * length, frame flags and CAN0 timestamp. The RX queue delivers or drops
 * captures before half a timestamp wrap. A null receive just advances TX.
 * Advance generation only after the hardware slot is reset or drained.
 * The timestamps of the link itself use monotonically advancing T6 ticks. */
Lfj8H03DtcSlotUse lfj8_h03_dtc_can_poll(Lfj8H03DtcCan *state, CheryDtcState *dtc,
                                       const Lfj8RegisterIo *io, uint8_t owns_slot13,
                                       uint32_t generation, uint32_t tick,
                                       const Lfj8H03DtcReceive *received);

#endif
