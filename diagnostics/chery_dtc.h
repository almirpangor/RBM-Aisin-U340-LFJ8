#ifndef RBM_CHERY_DTC_H
#define RBM_CHERY_DTC_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

enum {
    CHERY_DTC_INDEX_COUNT = 96,
    CHERY_DTC_BITMAP_BYTES = CHERY_DTC_INDEX_COUNT / 8,
    CHERY_DTC_SNAPSHOT_COUNT = 5,
    CHERY_DTC_MAX_REPLY_BYTES = 2 + 3 * CHERY_DTC_SNAPSHOT_COUNT
};

typedef struct {
    uint8_t history[CHERY_DTC_BITMAP_BYTES];
    uint8_t current[CHERY_DTC_BITMAP_BYTES];
    uint8_t snapshot_index[CHERY_DTC_SNAPSHOT_COUNT];
    /* Set on accepted 14 FF 00. The single monitor owner consumes this
     * event and resets the debouncers before running another sample. */
    bool clear_pending;
} CheryDtcState;

typedef struct {
    uint8_t mode_bits;
    uint8_t permission_bits;
} CheryDtcSession;

typedef struct {
    /* Return true only after the empty history is durably published and
     * verified. Run under the serialized diagnostic owner and leave live
     * DTC state untouched. Resolve uncertain writes before later saves. */
    bool (*commit_empty)(void *context);
    void *context;
} CheryDtcClearStore;

typedef enum {
    CHERY_DTC_REPLIED,
    CHERY_DTC_UNHANDLED,
    CHERY_DTC_SHORT_BUFFER,
    CHERY_DTC_INVALID_ARGUMENT,
    CHERY_DTC_STORAGE_FAILURE
} CheryDtcResult;

void chery_dtc_init(CheryDtcState *state);
bool chery_dtc_set_current(CheryDtcState *state, uint8_t index, bool current);
bool chery_dtc_store_snapshot(CheryDtcState *state, size_t slot, uint8_t index);
/* Update the fields visible to service 0x17 on a C0 monitor transition.
 * On the first occurrence take the first free snapshot slot. An occupied
 * list is retained; the history bit can exist without a visible slot. */
bool chery_dtc_raise_c0(CheryDtcState *state, uint8_t index, bool inhibit_history);

/* Request and response contain application bytes starting with the SID.
 * The caller owns transport, synchronization and monitor qualification. */
CheryDtcResult chery_dtc_respond(
    CheryDtcState *state,
    CheryDtcSession session,
    const uint8_t *request,
    size_t request_length,
    uint8_t *response,
    size_t response_capacity,
    size_t *response_length
);

/* For an authorized clear, commit before changing RAM or exposing a reply.
 * A configured store without a successful commit yields STORAGE_FAILURE
 * and zero response length. NULL selects the existing RAM-only behavior. */
CheryDtcResult chery_dtc_respond_with_store(
    CheryDtcState *state,
    CheryDtcSession session,
    const uint8_t *request,
    size_t request_length,
    uint8_t *response,
    size_t response_capacity,
    size_t *response_length,
    const CheryDtcClearStore *store
);

#endif
