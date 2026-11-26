#include "chery_dtc_journal.h"

#include <string.h>

enum {
    GENERATION_OFFSET = 4,
    HISTORY_OFFSET = GENERATION_OFFSET + 4,
    SNAPSHOT_OFFSET = HISTORY_OFFSET + CHERY_DTC_BITMAP_BYTES,
    CRC_OFFSET = SNAPSHOT_OFFSET + CHERY_DTC_SNAPSHOT_COUNT,
    MARKER_OFFSET = CRC_OFFSET + 4
};

_Static_assert((int)MARKER_OFFSET == (int)CHERY_DTC_JOURNAL_BODY_BYTES,
               "DTC journal format size changed");

static const uint8_t header[] = {'D', 'T', 'C', 1};

static void write_le32(uint8_t *out, uint32_t value)
{
    for (unsigned i = 0; i < 4; ++i) {
        out[i] = (uint8_t)(value >> (8u * i));
    }
}

static uint32_t read_le32(const uint8_t *in)
{
    uint32_t value = 0;
    for (unsigned i = 0; i < 4; ++i) {
        value |= (uint32_t)in[i] << (8u * i);
    }
    return value;
}

static uint32_t body_crc(const uint8_t *body)
{
    uint32_t crc = UINT32_MAX;
    for (size_t i = 0; i < CRC_OFFSET; ++i) {
        crc ^= body[i];
        for (unsigned bit = 0; bit < 8; ++bit) {
            uint32_t low_bit_mask = 0u - (crc & 1u);
            crc = (crc >> 1) ^ (UINT32_C(0xEDB88320) & low_bit_mask);
        }
    }
    return ~crc;
}

static bool snapshots_valid(const uint8_t *history, const uint8_t *snapshots)
{
    for (size_t i = 0; i < CHERY_DTC_SNAPSHOT_COUNT; ++i) {
        uint8_t index = snapshots[i];
        if (index == UINT8_MAX) {
            continue;
        }
        if (index >= CHERY_DTC_INDEX_COUNT ||
            (history[index / 8u] & (1u << (index % 8u))) == 0u) {
            return false;
        }
    }
    return true;
}

bool chery_dtc_journal_encode(const CheryDtcState *state, uint32_t generation,
                              uint8_t body[CHERY_DTC_JOURNAL_BODY_BYTES])
{
    if (!snapshots_valid(state->history, state->snapshot_index)) {
        return false;
    }
    memcpy(body, header, sizeof(header));
    write_le32(body + GENERATION_OFFSET, generation);
    memcpy(body + HISTORY_OFFSET, state->history, CHERY_DTC_BITMAP_BYTES);
    memcpy(body + SNAPSHOT_OFFSET, state->snapshot_index, CHERY_DTC_SNAPSHOT_COUNT);
    write_le32(body + CRC_OFFSET, body_crc(body));
    return true;
}

static bool committed_valid(const uint8_t *record)
{
    return record[MARKER_OFFSET] == CHERY_DTC_JOURNAL_COMMITTED &&
           memcmp(record, header, sizeof(header)) == 0 &&
           read_le32(record + CRC_OFFSET) == body_crc(record) &&
           snapshots_valid(record + HISTORY_OFFSET, record + SNAPSHOT_OFFSET);
}

CheryDtcJournalResult chery_dtc_journal_restore(
    const uint8_t slot0[CHERY_DTC_JOURNAL_RECORD_BYTES],
    const uint8_t slot1[CHERY_DTC_JOURNAL_RECORD_BYTES],
    CheryDtcState *state, uint32_t *generation)
{
    chery_dtc_init(state);
    bool present0 = slot0[MARKER_OFFSET] != CHERY_DTC_JOURNAL_UNCOMMITTED;
    bool present1 = slot1[MARKER_OFFSET] != CHERY_DTC_JOURNAL_UNCOMMITTED;
    if ((present0 && !committed_valid(slot0)) || (present1 && !committed_valid(slot1))) {
        /* Falling back could resurrect history from before a committed clear. */
        return CHERY_DTC_JOURNAL_CORRUPT;
    }
    if (!present0 && !present1) {
        return CHERY_DTC_JOURNAL_EMPTY;
    }

    bool select0 = present0;
    if (present0 && present1) {
        uint32_t gen0 = read_le32(slot0 + GENERATION_OFFSET);
        uint32_t gen1 = read_le32(slot1 + GENERATION_OFFSET);
        uint32_t difference = gen0 - gen1;
        if (difference != 1u && difference != UINT32_MAX) {
            return CHERY_DTC_JOURNAL_CORRUPT;
        }
        select0 = difference == 1u;
    }

    const uint8_t *selected = select0 ? slot0 : slot1;
    memcpy(state->history, selected + HISTORY_OFFSET, CHERY_DTC_BITMAP_BYTES);
    memcpy(state->snapshot_index, selected + SNAPSHOT_OFFSET, CHERY_DTC_SNAPSHOT_COUNT);
    *generation = read_le32(selected + GENERATION_OFFSET);
    return select0 ? CHERY_DTC_JOURNAL_SLOT_0 : CHERY_DTC_JOURNAL_SLOT_1;
}
