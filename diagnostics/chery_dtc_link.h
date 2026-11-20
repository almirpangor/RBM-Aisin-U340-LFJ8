#ifndef RBM_CHERY_DTC_LINK_H
#define RBM_CHERY_DTC_LINK_H

#include "chery_dtc_can.h"

enum {
    CHERY_DTC_LINK_TX_CONFIRM_TICKS = 180,
    CHERY_DTC_LINK_FLOW_CONTROL_TICKS = 200
};

typedef enum {
    CHERY_DTC_LINK_IGNORED,
    CHERY_DTC_LINK_FRAME_READY,
    CHERY_DTC_LINK_WAITING,
    CHERY_DTC_LINK_COMPLETE,
    CHERY_DTC_LINK_ABORTED,
    CHERY_DTC_LINK_INVALID_ARGUMENT
} CheryDtcLinkResult;

typedef enum {
    CHERY_DTC_LINK_IDLE,
    CHERY_DTC_LINK_AWAITING_TX,
    CHERY_DTC_LINK_AWAITING_FLOW_CONTROL
} CheryDtcLinkPhase;

typedef struct {
    CheryDtcCanFrame frame;
    uint32_t token;
} CheryDtcLinkTx;

typedef struct {
    CheryDtcSession session;
    CheryDtcLinkPhase phase;
    CheryDtcCanReply reply;
    size_t next_frame;
    uint32_t phase_tick;
    uint32_t tx_token;
} CheryDtcLink;

/* All timestamps are monotonically advancing T6 ticks modulo 2^32.
 * FRAME_READY yields one frame and its unique confirmation token. */
void chery_dtc_link_init(CheryDtcLink *link);
void chery_dtc_link_end_session(CheryDtcLink *link);
bool chery_dtc_link_expire(CheryDtcLink *link, uint32_t tick);
CheryDtcLinkResult chery_dtc_link_receive(
    CheryDtcLink *link,
    CheryDtcState *dtc,
    const CheryDtcCanFrame *received,
    uint32_t tick,
    CheryDtcLinkTx *outgoing
);
CheryDtcLinkResult chery_dtc_link_confirm_tx(
    CheryDtcLink *link,
    uint32_t token,
    uint32_t tick,
    CheryDtcLinkTx *outgoing
);

#endif
