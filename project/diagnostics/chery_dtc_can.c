#include "chery_dtc_can.h"

#include <string.h>

_Static_assert(
    CHERY_DTC_MAX_REPLY_BYTES <= 6 + 7 * (CHERY_DTC_CAN_MAX_REPLY_FRAMES - 1),
    "Diagnostic CAN reply array must hold the maximum segmented PDU"
);

static CheryDtcCanFrame *add_reply_frame(CheryDtcCanReply *reply)
{
    CheryDtcCanFrame *frame = &reply->frames[reply->count++];
    *frame = (CheryDtcCanFrame){
        .id = CHERY_DTC_CAN_REPLY_ID,
        .length = CHERY_DTC_CAN_FRAME_BYTES
    };
    return frame;
}

CheryDtcResult chery_dtc_can_format_reply_with_store(
    CheryDtcState *state,
    CheryDtcSession session,
    const CheryDtcCanFrame *request,
    CheryDtcCanReply *reply,
    const CheryDtcClearStore *store
)
{
    if (reply == NULL) {
        return CHERY_DTC_INVALID_ARGUMENT;
    }
    reply->count = 0;
    if (state == NULL || request == NULL) {
        return CHERY_DTC_INVALID_ARGUMENT;
    }
    if (request->id != CHERY_DTC_CAN_REQUEST_ID || request->extended ||
        request->remote || request->fd || request->length == 0 ||
        request->length > CHERY_DTC_CAN_FRAME_BYTES) {
        return CHERY_DTC_UNHANDLED;
    }

    uint8_t request_size = request->data[0];
    if (request_size == 0 || request_size > 7u || request_size >= request->length) {
        return CHERY_DTC_UNHANDLED;
    }

    uint8_t pdu[CHERY_DTC_MAX_REPLY_BYTES];
    size_t pdu_length;
    CheryDtcResult result = chery_dtc_respond_with_store(
        state, session, &request->data[1], request_size, pdu, sizeof(pdu), &pdu_length, store
    );
    if (result != CHERY_DTC_REPLIED) {
        return result;
    }

    CheryDtcCanFrame *frame = add_reply_frame(reply);
    if (pdu_length <= 7u) {
        frame->data[0] = (uint8_t)pdu_length;
        memcpy(&frame->data[1], pdu, pdu_length);
        return CHERY_DTC_REPLIED;
    }

    frame->data[0] = 0x10u;
    frame->data[1] = (uint8_t)pdu_length;
    memcpy(&frame->data[2], pdu, 6);
    size_t offset = 6;
    uint8_t sequence = 1;
    while (offset < pdu_length) {
        frame = add_reply_frame(reply);
        frame->data[0] = (uint8_t)(0x20u | sequence++);
        size_t remaining = pdu_length - offset;
        size_t bytes = remaining < 7u ? remaining : 7u;
        memcpy(&frame->data[1], &pdu[offset], bytes);
        offset += bytes;
    }
    return CHERY_DTC_REPLIED;
}

CheryDtcResult chery_dtc_can_format_reply(
    CheryDtcState *state,
    CheryDtcSession session,
    const CheryDtcCanFrame *request,
    CheryDtcCanReply *reply
)
{
    return chery_dtc_can_format_reply_with_store(state, session, request, reply, NULL);
}
