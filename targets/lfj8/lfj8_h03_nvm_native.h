#ifndef RBM_LFJ8_H03_NVM_NATIVE_H
#define RBM_LFJ8_H03_NVM_NATIVE_H

#include "factory_adaptation_store.h"
#include "lfj8_h03_nvm.h"

/* Cold-start reader for the internal M32176F4 array. The startup owner
 * provides two exclusively reserved erase blocks and owns the DTC RAM.
 * Call in normal executable Flash mode before starting DTC producers and
 * the service writer. The native IRQ lock covers both journal reads.
 *
 * Before and after each slot read, the array must be accessible and idle,
 * with no Flash error and with all FELBANK/FESBANK enables clear. A refused
 * read returns LFJ8_H03_NVM_READ_FAILED and clears the cold-start DTC state.
 * There are no erase or program operations. */
Lfj8H03NvmResult lfj8_h03_nvm_native_restore_dtc(const uint8_t blocks[2], CheryDtcState *state);

/* Read the two raw UFL1 records at the starts of distinct, exclusively
 * reserved adaptation erase blocks. Qualification and ownership of these
 * blocks belong to the application profile. The native lock covers both
 * reads, and false means both destination snapshots must be discarded. */
bool lfj8_h03_nvm_native_read_adaptation(const uint8_t blocks[2],
    uint8_t slots[2][FACTORY_ADAPT_RECORD_BYTES]);

enum {
    LFJ8_H03_NVM_BENCH_NO_ASSIGNED_MEDIA = 1,
    LFJ8_H03_NVM_BENCH_SAMPLE_BYTES = 32,
};

typedef struct {
    uint8_t persistence_status;
    uint8_t fmod;
    uint8_t fstat;
    uint8_t fcnt1;
    uint16_t felbank0;
    uint16_t felbank1;
    uint16_t fesbank0;
    uint16_t fesbank1;
} Lfj8H03NvmBenchStatus;

typedef enum {
    LFJ8_H03_NVM_INSPECT_OK,
    LFJ8_H03_NVM_INSPECT_INVALID,
    LFJ8_H03_NVM_INSPECT_UNAVAILABLE,
} Lfj8H03NvmInspectResult;

/* Native readout for the no-media bench profile. Call only with executable
 * Flash visible and from an owned application context. The status samples
 * the controller registers. It does not test whether the array is writable. */
bool lfj8_h03_nvm_native_bench_status(Lfj8H03NvmBenchStatus *out);

/* Inspect one 32-byte chunk inside the named erase block while parked.
 * The chunk index is zero-based from the block start. On success the
 * result counts halfwords other than 0xFFFF. On failure out is untouched.
 * A zero count says nothing about ownership or permission to erase. */
Lfj8H03NvmInspectResult lfj8_h03_nvm_native_bench_inspect(
    unsigned block, uint16_t chunk_index, uint8_t *non_erased_halfwords);

#endif
