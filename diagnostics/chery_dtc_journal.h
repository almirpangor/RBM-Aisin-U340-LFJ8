#ifndef RBM_CHERY_DTC_JOURNAL_H
#define RBM_CHERY_DTC_JOURNAL_H

#include "chery_dtc.h"

enum {
    CHERY_DTC_JOURNAL_BODY_BYTES = 29,
    CHERY_DTC_JOURNAL_RECORD_BYTES = CHERY_DTC_JOURNAL_BODY_BYTES + 1,
    CHERY_DTC_JOURNAL_UNCOMMITTED = 0xFF,
    CHERY_DTC_JOURNAL_COMMITTED = 0x00
};

typedef enum {
    CHERY_DTC_JOURNAL_EMPTY,
    CHERY_DTC_JOURNAL_SLOT_0,
    CHERY_DTC_JOURNAL_SLOT_1,
    CHERY_DTC_JOURNAL_CORRUPT
} CheryDtcJournalResult;

/* Prepare the body for an erased inactive slot. Publish the marker separately
 * after the body is durable. Generations advance by one modulo 2^32. */
bool chery_dtc_journal_encode(const CheryDtcState *state, uint32_t generation,
                              uint8_t body[CHERY_DTC_JOURNAL_BODY_BYTES]);

/* Restore at startup. EMPTY and CORRUPT both initialize empty RAM state.
 * generation is updated only when a slot is selected. All pointers must
 * refer to valid, non-overlapping objects. */
CheryDtcJournalResult chery_dtc_journal_restore(
    const uint8_t slot0[CHERY_DTC_JOURNAL_RECORD_BYTES],
    const uint8_t slot1[CHERY_DTC_JOURNAL_RECORD_BYTES],
    CheryDtcState *state, uint32_t *generation);

#endif
