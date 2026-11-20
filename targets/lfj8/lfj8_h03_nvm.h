#ifndef RBM_LFJ8_H03_NVM_H
#define RBM_LFJ8_H03_NVM_H

#include "chery_dtc_journal.h"

enum { LFJ8_H03_NVM_BLOCK_COUNT = 13 };

typedef struct {
    uint32_t first;
    uint32_t end;
} Lfj8H03NvmBlock;

/* M32176F4 erase geometry. The result describes size and alignment only. */
bool lfj8_h03_nvm_block(unsigned number, Lfj8H03NvmBlock *block);

typedef struct {
    void *context;
    uint8_t blocks[2]; /* Two distinct, exclusively reserved erase blocks. */
    bool (*read)(void *context, uint32_t address, uint8_t *data, size_t size);
    bool (*allow_write)(void *context, unsigned block);
    bool (*erase)(void *context, uint32_t last_even_address);
    bool (*program)(void *context, uint32_t even_address, uint16_t big_endian_halfword);
} Lfj8H03Nvm;

typedef enum {
    LFJ8_H03_NVM_EMPTY = CHERY_DTC_JOURNAL_EMPTY,
    LFJ8_H03_NVM_SLOT_0 = CHERY_DTC_JOURNAL_SLOT_0,
    LFJ8_H03_NVM_SLOT_1 = CHERY_DTC_JOURNAL_SLOT_1,
    LFJ8_H03_NVM_CORRUPT = CHERY_DTC_JOURNAL_CORRUPT,
    LFJ8_H03_NVM_READ_FAILED,
    LFJ8_H03_NVM_INVALID,
} Lfj8H03NvmResult;

/* The startup owner restores before serving DTC or running its monitors.
 * Only history and snapshot indices are restored. Empty, invalid,
 * corrupt or unreadable storage initializes an empty DTC state.
 *
 * The owner provides independently qualified block ownership and
 * serializes flash, DTC and service operations. Reads must return the
 * physical array or fail, including in Virtual Flash and E/W modes.
 * Successful erases and halfword writes must already be durable.
 * The callbacks own busy/error handling, the write-mode transition
 * and the electrical/idle conditions throughout the transaction. */
Lfj8H03NvmResult lfj8_h03_nvm_restore_dtc(const Lfj8H03Nvm *nvm, CheryDtcState *state);

/* Save only on a history change. Use commit_empty_dtc for an authorized
 * clear. Retry after an uncertain operation by reading both blocks again,
 * once the device can safely return array data. Corrupt or unreadable
 * storage refuses further writes. With only a retired record left, its
 * verified generation orders the next publication in the other block.
 * An ambiguous or damaged retired record cannot authorize a write. */
bool lfj8_h03_nvm_save_dtc(const Lfj8H03Nvm *nvm, const CheryDtcState *state);

/* CheryDtcClearStore callback. context is the same configured Lfj8H03Nvm.
 * Verify the empty record before retiring its peer. A retired record cannot
 * be restored if the replacement disappears. Verify the retirement before
 * allowing the caller to publish a positive reply. Retrying a partial
 * retirement can erase the peer when the write owner permits it. */
bool lfj8_h03_nvm_commit_empty_dtc(void *context);

#endif
