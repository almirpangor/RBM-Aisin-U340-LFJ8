#include "lfj8_h03_nvm.h"

#include <string.h>

enum {
    /* The portable body is 29 bytes. Pad to a halfword and dedicate an
     * entire fresh halfword to publication. No halfword is written twice. */
    MARKER_OFFSET = (CHERY_DTC_JOURNAL_BODY_BYTES + 1) & ~1,
    RETIRED_OFFSET = MARKER_OFFSET + 2,
    SLOT_BYTES = RETIRED_OFFSET + 2,
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

static bool erased_halfword(const uint8_t *value)
{
    return value[0] == UINT8_MAX && value[1] == UINT8_MAX;
}

static bool programmed_zero(const uint8_t *value)
{
    return value[0] == 0u && value[1] == 0u;
}

static void decode_marker(uint8_t slot[SLOT_BYTES])
{
    uint8_t marker = 1u; /* Neither valid portable marker. */
    /* Treat any partial retirement as ineligible. The clear operation still
     * requires a fully verified retirement before it can acknowledge. */
    if (!erased_halfword(slot + RETIRED_OFFSET) || erased_halfword(slot + MARKER_OFFSET)) {
        marker = CHERY_DTC_JOURNAL_UNCOMMITTED;
    } else if (programmed_zero(slot + MARKER_OFFSET) &&
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

static bool erase_slot(const Lfj8H03Nvm *nvm, const Lfj8H03NvmBlock *block, uint8_t slot[SLOT_BYTES])
{
    if (!nvm->erase(nvm->context, block->end - 2u) ||
        !nvm->read(nvm->context, block->first, slot, SLOT_BYTES)) {
        return false;
    }
    for (size_t i = 0; i < SLOT_BYTES; ++i) {
        if (slot[i] != UINT8_MAX) {
            return false;
        }
    }
    return true;
}

static bool publish_record(const Lfj8H03Nvm *nvm, const Lfj8H03NvmBlock *block,
                           uint8_t body[SLOT_BYTES], uint8_t verify[SLOT_BYTES])
{
    if (!erase_slot(nvm, block, verify)) {
        return false;
    }
    for (unsigned i = 0; i < MARKER_OFFSET; i += 2u) {
        const uint16_t value = (uint16_t)((uint16_t)body[i] << 8 | body[i + 1u]);
        if (value != UINT16_MAX && !nvm->program(nvm->context, block->first + i, value)) {
            return false;
        }
    }
    if (!nvm->read(nvm->context, block->first, verify, SLOT_BYTES) ||
        memcmp(body, verify, SLOT_BYTES) != 0 ||
        !nvm->program(nvm->context, block->first + MARKER_OFFSET, 0u)) {
        return false;
    }
    body[MARKER_OFFSET] = 0u;
    body[MARKER_OFFSET + 1u] = 0u;
    return nvm->read(nvm->context, block->first, verify, SLOT_BYTES) &&
           memcmp(body, verify, SLOT_BYTES) == 0;
}

static bool retire_record(const Lfj8H03Nvm *nvm, unsigned block_number,
                          const Lfj8H03NvmBlock *block, uint8_t slot[SLOT_BYTES])
{
    if (erased_halfword(slot + MARKER_OFFSET) || programmed_zero(slot + RETIRED_OFFSET)) {
        return true;
    }
    if (!nvm->allow_write(nvm->context, block_number)) {
        return false;
    }
    if (!erased_halfword(slot + RETIRED_OFFSET)) {
        /* Do not program a partially written halfword again. The replacement
         * record has already been checked, so this block can be erased. */
        return erase_slot(nvm, block, slot);
    }
    return nvm->program(nvm->context, block->first + RETIRED_OFFSET, 0u) &&
           nvm->read(nvm->context, block->first, slot, SLOT_BYTES) &&
           programmed_zero(slot + RETIRED_OFFSET);
}

static bool save_dtc(const Lfj8H03Nvm *nvm, const CheryDtcState *state, bool retire_previous)
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
    const bool unchanged = result != LFJ8_H03_NVM_EMPTY &&
        memcmp(previous.history, state->history, sizeof state->history) == 0 &&
        memcmp(previous.snapshot_index, state->snapshot_index, sizeof state->snapshot_index) == 0;
    unsigned active = result == LFJ8_H03_NVM_SLOT_1 ? 1u : 0u;
    if (!unchanged) {
        active = result == LFJ8_H03_NVM_SLOT_0 ? 1u : 0u;
        uint8_t body[SLOT_BYTES];
        memset(body, UINT8_MAX, sizeof body);
        if (!chery_dtc_journal_encode(state, generation + 1u, body) ||
            !nvm->allow_write(nvm->context, nvm->blocks[active]) ||
            !publish_record(nvm, &blocks[active], body, slots[active])) {
            return false;
        }
    }

    const unsigned peer = 1u - active;
    return !retire_previous || retire_record(nvm, nvm->blocks[peer], &blocks[peer], slots[peer]);
}

bool lfj8_h03_nvm_save_dtc(const Lfj8H03Nvm *nvm, const CheryDtcState *state)
{
    return save_dtc(nvm, state, false);
}

bool lfj8_h03_nvm_commit_empty_dtc(void *context)
{
    CheryDtcState empty;
    chery_dtc_init(&empty);
    return save_dtc(context, &empty, true);
}
