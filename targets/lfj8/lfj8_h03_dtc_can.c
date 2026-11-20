#include "lfj8_h03_dtc_can.h"

enum { EMPTY, QUEUED, SUBMITTED, DRAINING, LEASE_LOST };

bool lfj8_h03_dtc_can_decode_basic(Lfj8H03DtcReceive *received, const uint8_t slot[16],
                                  uint8_t control, bool extended, uint32_t generation)
{
    /* RR | TRFIN. Reject active access, ML, RA (received remote frame)
     * and unexpected mode bits. Read the raw ID with the OEM 1F3F mask. */
    if (received == NULL || slot == NULL || control != 0x41u || extended ||
        (slot[0] & 0x1fu) != (CHERY_DTC_CAN_REQUEST_ID >> 6) ||
        (slot[1] & 0x3fu) != (CHERY_DTC_CAN_REQUEST_ID & 0x3fu)) {
        return false;
    }
    const uint8_t length = slot[5] & 0x0fu;
    if (length == 0u || length > CHERY_DTC_CAN_FRAME_BYTES) {
        return false;
    }
    received->frame.id = CHERY_DTC_CAN_REQUEST_ID;
    received->frame.length = length;
    received->frame.extended = false;
    received->frame.remote = false;
    received->frame.fd = false;
    for (uint8_t i = 0; i < CHERY_DTC_CAN_FRAME_BYTES; ++i) {
        received->frame.data[i] = i < length ? slot[6u + i] : 0u;
    }
    received->generation = generation;
    received->can_timestamp = (uint16_t)(((uint16_t)slot[14] << 8) | slot[15]);
    return true;
}

bool lfj8_h03_dtc_can_init(Lfj8H03DtcCan *state, uint16_t max_receive_age_bits)
{
    if (state == NULL || max_receive_age_bits == 0u || max_receive_age_bits >= 0x8000u) {
        return false;
    }
    chery_dtc_link_init(&state->link);
    state->generation = 0;
    state->session_clock_tick = 0;
    state->max_receive_age_bits = max_receive_age_bits;
    state->first_frame_finished_at = 0;
    state->submission = EMPTY;
    state->session_clock_seen = false;
    return true;
}

static void discard_submission(Lfj8H03DtcCan *state)
{
    if (state->submission == SUBMITTED) {
        state->submission = DRAINING;
    } else if (state->submission == QUEUED) {
        state->submission = EMPTY;
    }
}

static void stop_session(Lfj8H03DtcCan *state)
{
    chery_dtc_link_end_session(&state->link);
    discard_submission(state);
}

bool lfj8_h03_dtc_can_session_step(Lfj8H03DtcCan *state)
{
    if (!state || !chery_dtc_link_session_step(&state->link)) {
        return false;
    }
    discard_submission(state);
    return true;
}

bool lfj8_h03_dtc_can_service_session(Lfj8H03DtcCan *state, uint32_t generation, uint32_t tick)
{
    enum { SESSION_FIRST_RELEASE = 0x40, SESSION_PERIOD = 128 };
    const uint32_t previous = state->session_clock_tick;
    state->session_clock_tick = tick;
    if (!state->session_clock_seen || state->generation != generation) {
        state->session_clock_seen = true;
        return false;
    }
    if (tick - previous >= UINT32_C(0x80000000)) {
        stop_session(state);
        return true;
    }
    const bool released =
        (tick - SESSION_FIRST_RELEASE) / SESSION_PERIOD !=
        (previous - SESSION_FIRST_RELEASE) / SESSION_PERIOD;
    return released && lfj8_h03_dtc_can_session_step(state);
}

static Lfj8H03DtcSlotUse lose_ownership(Lfj8H03DtcCan *state)
{
    stop_session(state);
    if (state->submission == DRAINING) {
        /* Only a new generation proves the previous TX was reset or drained. */
        state->submission = LEASE_LOST;
    }
    return LFJ8_H03_DTC_NO_OWNERSHIP;
}

static void queue_next(Lfj8H03DtcCan *state, CheryDtcLinkResult result)
{
    if (result == CHERY_DTC_LINK_FRAME_READY) {
        state->submission = QUEUED;
    }
}

static bool receive_current(const Lfj8H03DtcCan *state, const Lfj8H03DtcReceive *received,
                            uint16_t now)
{
    if (received == NULL || received->generation != state->generation ||
        (uint16_t)(now - received->can_timestamp) >= state->max_receive_age_bits) {
        return false;
    }
    if (state->link.phase != CHERY_DTC_LINK_AWAITING_FLOW_CONTROL) {
        return true;
    }
    const uint16_t since_ff = (uint16_t)(received->can_timestamp - state->first_frame_finished_at);
    return since_ff != 0u && since_ff < 0x8000u;
}

Lfj8H03DtcSlotUse lfj8_h03_dtc_can_poll(Lfj8H03DtcCan *state, CheryDtcState *dtc,
                                       const Lfj8RegisterIo *io, uint8_t owns_slot13,
                                       uint32_t generation, uint32_t tick,
                                       const Lfj8H03DtcReceive *received)
{
    if (state->generation != generation) {
        stop_session(state);
        state->generation = generation;
        state->submission = EMPTY;
    }
    uint16_t now;
    if (owns_slot13 != 1u || state->submission == LEASE_LOST ||
        !lfj8_h03_can0_read_timestamp(io, &now)) {
        return lose_ownership(state);
    }

    if (chery_dtc_link_expire(&state->link, tick)) {
        stop_session(state);
    }

    CheryDtcLinkTx outgoing;
    if (state->submission >= SUBMITTED) {
        uint16_t finished_at;
        const Lfj8CanTxStatus status =
            lfj8_h03_can0_diag_status(io, state->submission == DRAINING, &finished_at);
        if (status == LFJ8_CAN_TX_UNAVAILABLE) {
            return lose_ownership(state);
        }
        if (status == LFJ8_CAN_TX_PENDING) {
            return LFJ8_H03_DTC_SLOT_RESERVED;
        }
        if (status == LFJ8_CAN_TX_FINISHED && state->submission == SUBMITTED) {
            state->submission = EMPTY;
            const CheryDtcLinkResult result =
                chery_dtc_link_confirm_tx(&state->link, state->link.tx_token, tick, &outgoing);
            if (result == CHERY_DTC_LINK_WAITING) {
                state->first_frame_finished_at = finished_at;
            }
            queue_next(state, result);
        } else {
            stop_session(state);
            state->submission = EMPTY;
        }
    }

    if (state->submission == EMPTY && receive_current(state, received, now)) {
        queue_next(state, chery_dtc_link_receive(&state->link, dtc, &received->frame, tick, &outgoing));
    }
    if (state->submission != QUEUED) {
        return LFJ8_H03_DTC_SLOT_FREE;
    }

    const size_t index = state->link.next_frame - 1u;
    const Lfj8CanResult sent = lfj8_h03_can0_diag_submit(io, state->link.reply.frames[index].data);
    if (sent == LFJ8_CAN_SUBMITTED) {
        state->submission = SUBMITTED;
    } else if (sent != LFJ8_CAN_SLOT_BUSY) {
        return lose_ownership(state);
    }
    return LFJ8_H03_DTC_SLOT_RESERVED;
}
