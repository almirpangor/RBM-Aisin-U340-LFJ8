#include "lfj8_h03_nvm.h"

#include <string.h>

enum {
    /* The portable body is 29 bytes. Pad to a halfword and dedicate an
     * entire fresh halfword to publication. No halfword is written twice. */
    MARKER_OFFSET = (CHERY_DTC_JOURNAL_BODY_BYTES + 1) & ~1,
    SLOT_BYTES = MARKER_OFFSET + 2,
};

_Static_assert(CHERY_DTC_JOURNAL_BODY_BYTES == 29, "H03 slot layout requires the v1 DTC body");

static const uint32_t block_edges[LFJ8_H03_NVM_BLOCK_COUNT + 1] = {
    0x000000u, 0x002000u, 0x003000u, 0x004000u, 0x006000u, 0x008000u, 0x010000u,
    0x020000u, 0x030000u, 0x040000u, 0x050000u, 0x060000u, 0x070000u, 0x080000u,
};

bool lfj8_h03_nvm_block(unsigned number, Lfj8H03NvmBlock *block)
{
    if (!block || number >= LFJ8_H03_NVM_BLOCK_COUNT) {
        return false;
    }
    *block = (Lfj8H03NvmBlock){block_edges[number], block_edges[number + 1u]};
    return true;
}

static bool valid_layout(const Lfj8H03Nvm *nvm, Lfj8H03NvmBlock blocks[2])
{
    return nvm && nvm->read && nvm->blocks[0] != nvm->blocks[1] &&
        lfj8_h03_nvm_block(nvm->blocks[0], &blocks[0]) &&
        lfj8_h03_nvm_block(nvm->blocks[1], &blocks[1]);
}

static void decode_marker(uint8_t slot[SLOT_BYTES])
{
    uint8_t marker = 1u; /* Neither valid portable marker. */
    if (slot[MARKER_OFFSET] == UINT8_MAX && slot[MARKER_OFFSET + 1u] == UINT8_MAX) {
        marker = CHERY_DTC_JOURNAL_UNCOMMITTED;
    } else if (slot[MARKER_OFFSET] == 0u && slot[MARKER_OFFSET + 1u] == 0u &&
               slot[CHERY_DTC_JOURNAL_BODY_BYTES] == UINT8_MAX) {
        marker = CHERY_DTC_JOURNAL_COMMITTED;
    }
    slot[CHERY_DTC_JOURNAL_BODY_BYTES] = marker;
}

static Lfj8H03NvmResult load(const Lfj8H03Nvm *nvm, const Lfj8H03NvmBlock blocks[2],
                            uint8_t slots[2][SLOT_BYTES], CheryDtcState *state, uint32_t *generation)
{
    for (unsigned slot = 0; slot < 2u; ++slot) {
        if (!nvm->read(nvm->context, blocks[slot].first, slots[slot], SLOT_BYTES)) {
            chery_dtc_init(state);
            return LFJ8_H03_NVM_READ_FAILED;
        }
        decode_marker(slots[slot]);
    }
    return (Lfj8H03NvmResult)chery_dtc_journal_restore(slots[0], slots[1], state, generation);
}

Lfj8H03NvmResult lfj8_h03_nvm_restore_dtc(const Lfj8H03Nvm *nvm, CheryDtcState *state)
{
    Lfj8H03NvmBlock blocks[2];
    if (!state) {
        return LFJ8_H03_NVM_INVALID;
    }
    if (!valid_layout(nvm, blocks)) {
        chery_dtc_init(state);
        return LFJ8_H03_NVM_INVALID;
    }
    uint8_t slots[2][SLOT_BYTES];
    uint32_t generation;
    return load(nvm, blocks, slots, state, &generation);
}

static bool prepare(const Lfj8H03Nvm *nvm, const Lfj8H03NvmBlock *block,
                    const uint8_t body[SLOT_BYTES], uint8_t verify[SLOT_BYTES])
{
    if (!nvm->erase(nvm->context, block->end - 2u) ||
        !nvm->read(nvm->context, block->first, verify, SLOT_BYTES)) {
        return false;
    }
    for (size_t i = 0; i < SLOT_BYTES; ++i) {
        if (verify[i] != UINT8_MAX) {
            return false;
        }
    }
    for (unsigned i = 0; i < MARKER_OFFSET; i += 2u) {
        const uint16_t value = (uint16_t)((uint16_t)body[i] << 8 | body[i + 1u]);
        if (value != UINT16_MAX && !nvm->program(nvm->context, block->first + i, value)) {
            return false;
        }
    }
    return nvm->read(nvm->context, block->first, verify, SLOT_BYTES) &&
        memcmp(body, verify, SLOT_BYTES) == 0;
}

bool lfj8_h03_nvm_save_dtc(const Lfj8H03Nvm *nvm, const CheryDtcState *state)
{
    Lfj8H03NvmBlock blocks[2];
    if (!state || !valid_layout(nvm, blocks) || !nvm->allow_write || !nvm->erase || !nvm->program) {
        return false;
    }

    CheryDtcState previous;
    uint8_t slots[2][SLOT_BYTES];
    uint32_t generation = 0u;
    const Lfj8H03NvmResult result = load(nvm, blocks, slots, &previous, &generation);
    if (result > LFJ8_H03_NVM_SLOT_1) {
        return false;
    }
    if (result != LFJ8_H03_NVM_EMPTY &&
        memcmp(previous.history, state->history, sizeof state->history) == 0 &&
        memcmp(previous.snapshot_index, state->snapshot_index, sizeof state->snapshot_index) == 0) {
        return true;
    }

    const unsigned target = result == LFJ8_H03_NVM_SLOT_0 ? 1u : 0u;
    const Lfj8H03NvmBlock *block = &blocks[target];
    uint8_t body[SLOT_BYTES];
    memset(body, UINT8_MAX, sizeof body);
    if (!chery_dtc_journal_encode(state, generation + 1u, body) ||
        !nvm->allow_write(nvm->context, nvm->blocks[target]) ||
        !prepare(nvm, block, body, slots[target]) ||
        !nvm->program(nvm->context, block->first + MARKER_OFFSET, 0u)) {
        return false;
    }
    body[MARKER_OFFSET] = 0u;
    body[MARKER_OFFSET + 1u] = 0u;
    return nvm->read(nvm->context, block->first, slots[target], SLOT_BYTES) &&
        memcmp(body, slots[target], SLOT_BYTES) == 0;
}

bool lfj8_h03_nvm_commit_empty_dtc(void *context)
{
    CheryDtcState empty;
    chery_dtc_init(&empty);
    return lfj8_h03_nvm_save_dtc(context, &empty);
}
