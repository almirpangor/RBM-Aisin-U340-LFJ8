#include "chery_dtc_link.h"

static void discard_reply(CheryDtcLink *link)
{
    link->phase = CHERY_DTC_LINK_IDLE;
    link->reply.count = 0;
    link->next_frame = 0;
}

void chery_dtc_link_init(CheryDtcLink *link)
{
    if (link != NULL) {
        *link = (CheryDtcLink){0};
        chery_dtc_link_end_session(link);
    }
}

void chery_dtc_link_end_session(CheryDtcLink *link)
{
    if (link != NULL) {
        discard_reply(link);
        link->session = (CheryDtcSession){0x9Fu, 0x11u};
        link->session_steps_left = 0;
    }
}

bool chery_dtc_link_timeout_due(const CheryDtcLink *link, uint32_t tick)
{
    if (link == NULL || link->phase == CHERY_DTC_LINK_IDLE) {
        return false;
    }

    const uint32_t limit = link->phase == CHERY_DTC_LINK_AWAITING_TX
        ? CHERY_DTC_LINK_TX_CONFIRM_TICKS
        : CHERY_DTC_LINK_FLOW_CONTROL_TICKS;
    return (uint32_t)(tick - link->phase_tick) >= limit;
}

bool chery_dtc_link_expire(CheryDtcLink *link, uint32_t tick)
{
    if (!chery_dtc_link_timeout_due(link, tick)) {
        return false;
    }

    discard_reply(link);
    return true;
}

static CheryDtcLinkResult take_next_frame(
    CheryDtcLink *link,
    uint32_t tick,
    CheryDtcLinkTx *outgoing
)
{
    outgoing->frame = link->reply.frames[link->next_frame++];
    outgoing->token = ++link->tx_token;
    link->phase = CHERY_DTC_LINK_AWAITING_TX;
    link->phase_tick = tick;
    return CHERY_DTC_LINK_FRAME_READY;
}

static bool is_classic_request(const CheryDtcCanFrame *frame)
{
    return frame->id == CHERY_DTC_CAN_REQUEST_ID && !frame->extended &&
           !frame->remote && !frame->fd && frame->length > 0 &&
           frame->length <= CHERY_DTC_CAN_FRAME_BYTES;
}

static CheryDtcLinkResult receive_flow_control(
    CheryDtcLink *link,
    const CheryDtcCanFrame *frame,
    uint32_t tick,
    CheryDtcLinkTx *outgoing
)
{
    if ((frame->data[0] & 0xF0u) != 0x30u) {
        return CHERY_DTC_LINK_IGNORED;
    }
    if (frame->length < 3 || frame->data[0] != 0x30u ||
        frame->data[1] != 0u || frame->data[2] != 0u) {
        discard_reply(link);
        return CHERY_DTC_LINK_ABORTED;
    }

    return take_next_frame(link, tick, outgoing);
}

CheryDtcLinkResult chery_dtc_link_receive_with_store(
    CheryDtcLink *link,
    CheryDtcState *dtc,
    const CheryDtcCanFrame *received,
    uint32_t tick,
    CheryDtcLinkTx *outgoing,
    const CheryDtcClearStore *store
)
{
    if (link == NULL || dtc == NULL || received == NULL || outgoing == NULL) {
        return CHERY_DTC_LINK_INVALID_ARGUMENT;
    }
    if (chery_dtc_link_expire(link, tick)) {
        return CHERY_DTC_LINK_ABORTED;
    }
    if (!is_classic_request(received)) {
        return CHERY_DTC_LINK_IGNORED;
    }
    if (link->phase == CHERY_DTC_LINK_AWAITING_FLOW_CONTROL) {
        return receive_flow_control(link, received, tick, outgoing);
    }
    if (link->phase != CHERY_DTC_LINK_IDLE) {
        return CHERY_DTC_LINK_IGNORED;
    }

    uint8_t length = received->data[0];
    if (length == 0u || length > 7u || length >= received->length) {
        return CHERY_DTC_LINK_IGNORED;
    }

    if (link->session.mode_bits == 0x9Fu) {
        link->session = (CheryDtcSession){0x90u, 0x01u};
    }
    /* S03 reloads F9F1 at the dispatcher tail even on a negative result. */
    link->session_steps_left = CHERY_DTC_LINK_SESSION_STEPS;

    if (length == 2u && received->data[1] == 0x10u && received->data[2] == 0x86u) {
        link->session.permission_bits = 0x08u;
        link->reply.count = 1;
        link->reply.frames[0] = (CheryDtcCanFrame){
            .id = CHERY_DTC_CAN_REPLY_ID,
            .length = CHERY_DTC_CAN_FRAME_BYTES,
            .data = {0x02u, 0x50u, 0x86u}
        };
    } else {
        const CheryDtcResult result = chery_dtc_can_format_reply_with_store(
            dtc, link->session, received, &link->reply, store
        );
        if (result == CHERY_DTC_STORAGE_FAILURE) {
            return CHERY_DTC_LINK_STORAGE_FAILURE;
        }
        if (result != CHERY_DTC_REPLIED) {
            return CHERY_DTC_LINK_IGNORED;
        }
    }

    return take_next_frame(link, tick, outgoing);
}

CheryDtcLinkResult chery_dtc_link_receive(
    CheryDtcLink *link,
    CheryDtcState *dtc,
    const CheryDtcCanFrame *received,
    uint32_t tick,
    CheryDtcLinkTx *outgoing
)
{
    return chery_dtc_link_receive_with_store(link, dtc, received, tick, outgoing, NULL);
}

CheryDtcLinkResult chery_dtc_link_confirm_tx(
    CheryDtcLink *link,
    uint32_t token,
    uint32_t tick,
    CheryDtcLinkTx *outgoing
)
{
    if (link == NULL || outgoing == NULL) {
        return CHERY_DTC_LINK_INVALID_ARGUMENT;
    }
    if (chery_dtc_link_expire(link, tick)) {
        return CHERY_DTC_LINK_ABORTED;
    }
    if (link->phase != CHERY_DTC_LINK_AWAITING_TX || token != link->tx_token) {
        return CHERY_DTC_LINK_IGNORED;
    }
    if (link->next_frame == link->reply.count) {
        discard_reply(link);
        return CHERY_DTC_LINK_COMPLETE;
    }
    if (link->next_frame == 1u) {
        link->phase = CHERY_DTC_LINK_AWAITING_FLOW_CONTROL;
        link->phase_tick = tick;
        return CHERY_DTC_LINK_WAITING;
    }

    return take_next_frame(link, tick, outgoing);
}
