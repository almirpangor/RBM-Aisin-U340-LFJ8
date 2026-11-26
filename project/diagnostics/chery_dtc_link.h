#ifndef RBM_CHERY_DTC_LINK_H
#define RBM_CHERY_DTC_LINK_H

#include "chery_dtc_can.h"

enum {
    CHERY_DTC_LINK_TX_CONFIRM_TICKS = 180,
    CHERY_DTC_LINK_FLOW_CONTROL_TICKS = 200,
    CHERY_DTC_LINK_SESSION_STEPS = 9
};

typedef enum {
    CHERY_DTC_LINK_IGNORED,
    CHERY_DTC_LINK_FRAME_READY,
    CHERY_DTC_LINK_WAITING,
    CHERY_DTC_LINK_COMPLETE,
    CHERY_DTC_LINK_ABORTED,
    CHERY_DTC_LINK_INVALID_ARGUMENT,
    CHERY_DTC_LINK_STORAGE_FAILURE
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
    uint8_t session_steps_left;
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
/* Call once per consumed TA2005 task 12 event, before dispatching the next
 * request when it expires. This clock is separate from the T6 transport
 * deadlines. True means the application session has ended and any pending
 * reply must be abandoned. The caller owns hardware TX abort/drain. */
static inline bool chery_dtc_link_session_step(CheryDtcLink *link)
{
    if (link == NULL || link->session_steps_left == 0) {
        return false;
    }
    --link->session_steps_left;
    if (link->session_steps_left != 0) {
        return false;
    }
    chery_dtc_link_end_session(link);
    return true;
}

/* Check the current TX or Flow Control deadline without consuming it. */
bool chery_dtc_link_timeout_due(const CheryDtcLink *link, uint32_t tick);
bool chery_dtc_link_expire(CheryDtcLink *link, uint32_t tick);
CheryDtcLinkResult chery_dtc_link_receive(
    CheryDtcLink *link,
    CheryDtcState *dtc,
    const CheryDtcCanFrame *received,
    uint32_t tick,
    CheryDtcLinkTx *outgoing
);
/* A configured store is called only for an authorized clear. If it fails,
 * the link stays idle and leaves outgoing and the confirmation token alone. */
CheryDtcLinkResult chery_dtc_link_receive_with_store(
    CheryDtcLink *link,
    CheryDtcState *dtc,
    const CheryDtcCanFrame *received,
    uint32_t tick,
    CheryDtcLinkTx *outgoing,
    const CheryDtcClearStore *store
);
CheryDtcLinkResult chery_dtc_link_confirm_tx(
    CheryDtcLink *link,
    uint32_t token,
    uint32_t tick,
    CheryDtcLinkTx *outgoing
);

#endif
