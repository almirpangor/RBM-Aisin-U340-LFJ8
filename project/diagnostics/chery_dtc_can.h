#ifndef RBM_CHERY_DTC_CAN_H
#define RBM_CHERY_DTC_CAN_H

#include "chery_dtc.h"

enum {
    CHERY_DTC_CAN_REQUEST_ID = 0x732,
    CHERY_DTC_CAN_REPLY_ID = 0x722,
    CHERY_DTC_CAN_FRAME_BYTES = 8,
    CHERY_DTC_CAN_MAX_REPLY_FRAMES = 3
};

typedef struct {
    uint16_t id;
    uint8_t length;
    bool extended;
    bool remote;
    bool fd;
    uint8_t data[CHERY_DTC_CAN_FRAME_BYTES];
} CheryDtcCanFrame;

typedef struct {
    size_t count;
    CheryDtcCanFrame frames[CHERY_DTC_CAN_MAX_REPLY_FRAMES];
} CheryDtcCanReply;

/* Builds frame bytes for an established S03 C0 session. Continuation frames
 * are templates. The transport owner must apply native Flow Control and pacing. */
CheryDtcResult chery_dtc_can_format_reply(
    CheryDtcState *state,
    CheryDtcSession session,
    const CheryDtcCanFrame *request,
    CheryDtcCanReply *reply
);

/* Like format_reply, with the optional durable-clear contract above.
 * Storage failure leaves reply->count at zero. */
CheryDtcResult chery_dtc_can_format_reply_with_store(
    CheryDtcState *state,
    CheryDtcSession session,
    const CheryDtcCanFrame *request,
    CheryDtcCanReply *reply,
    const CheryDtcClearStore *store
);

#endif
