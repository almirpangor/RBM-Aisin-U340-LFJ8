#include "chery_dtc.h"

#include <string.h>

typedef struct {
    uint16_t code;
    uint8_t inactive_status;
} CheryDtcEntry;

/* EMS.bin file offsets 0xEBE2 and 0xECA2, ordered by internal index. */
static const CheryDtcEntry dtc_table[CHERY_DTC_INDEX_COUNT] = {
    {0x0000u, 0x40u}, {0x0851u, 0x55u}, {0x0730u, 0x40u}, {0x0641u, 0x52u},
    {0x0710u, 0x54u}, {0x0840u, 0x54u}, {0x0841u, 0x40u}, {0x0745u, 0x40u},
    {0x0814u, 0x43u}, {0x0814u, 0x41u}, {0x0615u, 0x43u}, {0x0615u, 0x41u},
    {0x0768u, 0x53u}, {0x0753u, 0x53u}, {0x0657u, 0x43u}, {0x0657u, 0x41u},
    {0xD12Bu, 0x4Fu}, {0xD122u, 0x4Fu}, {0xD120u, 0x4Fu}, {0xD12Bu, 0x46u},
    {0xD100u, 0x4Fu}, {0xD11Fu, 0x4Fu}, {0xD121u, 0x4Fu}, {0x2176u, 0x56u},
    {0xD123u, 0x4Fu}, {0xC155u, 0x40u}, {0xC100u, 0x40u}, {0xC121u, 0x40u},
    {0xC140u, 0x40u}, {0xD221u, 0x4Fu}, {0xD220u, 0x4Fu}, {0xC001u, 0x40u},
    {0x0753u, 0x41u}, {0x0758u, 0x41u}, {0x0763u, 0x41u}, {0x0768u, 0x41u},
    {0x0773u, 0x41u}, {0x2709u, 0x41u}, {0x2753u, 0x41u}, {0x1928u, 0x41u},
    {0x0753u, 0x43u}, {0x0758u, 0x43u}, {0x0763u, 0x43u}, {0x0768u, 0x43u},
    {0x0773u, 0x43u}, {0x2709u, 0x43u}, {0x2753u, 0x43u}, {0x1928u, 0x43u},
    {0x0605u, 0x40u}, {0x0604u, 0x40u}, {0x0603u, 0x40u}, {0x0706u, 0x46u},
    {0x0705u, 0x40u}, {0x0709u, 0x40u}, {0x0819u, 0x46u}, {0x0850u, 0x55u},
    {0x0740u, 0x40u}, {0x0795u, 0x43u}, {0x0795u, 0x41u}, {0x0894u, 0x40u},
    {0x0811u, 0x40u}, {0x0897u, 0x40u}, {0x0775u, 0x43u}, {0x0775u, 0x41u},
    {0x0741u, 0x49u}, {0x0819u, 0x42u}, {0xD215u, 0x46u}, {0xD215u, 0x4Fu},
    {0xD403u, 0x4Fu}, {0xD225u, 0x4Fu}, {0xD226u, 0x4Fu}, {0xD200u, 0x4Fu},
    {0x0720u, 0x46u}, {0x0715u, 0x47u}, {0x0720u, 0x47u}, {0x0715u, 0x50u},
    {0x0720u, 0x50u}, {0xD12Fu, 0x4Fu}, {0xD22Bu, 0x4Fu}, {0x0000u, 0x40u},
    {0x0000u, 0x40u}, {0x0000u, 0x40u}, {0xD126u, 0x4Fu}, {0x0741u, 0x40u},
    {0x0218u, 0x40u}, {0xD208u, 0x4Fu}, {0xD12Du, 0x4Fu}, {0xD12Cu, 0x4Fu},
    {0x0826u, 0x55u}, {0x0826u, 0x54u}, {0x0826u, 0x53u}, {0x0826u, 0x4Bu},
    {0x0000u, 0x40u}, {0x0000u, 0x40u}, {0x0000u, 0x40u}, {0x0000u, 0x40u},
};

static uint8_t index_mask(uint8_t index)
{
    return (uint8_t)(1u << (index % 8u));
}

void chery_dtc_init(CheryDtcState *state)
{
    memset(state, 0, sizeof(*state));
    memset(state->snapshot_index, UINT8_MAX, sizeof(state->snapshot_index));
}

bool chery_dtc_set_current(CheryDtcState *state, uint8_t index, bool current)
{
    if (state == NULL || index >= CHERY_DTC_INDEX_COUNT) {
        return false;
    }

    uint8_t *cell = &state->current[index / 8u];
    uint8_t mask = index_mask(index);
    *cell = current ? (uint8_t)(*cell | mask) : (uint8_t)(*cell & (uint8_t)~mask);
    return true;
}

bool chery_dtc_store_snapshot(CheryDtcState *state, size_t slot, uint8_t index)
{
    if (state == NULL || slot >= CHERY_DTC_SNAPSHOT_COUNT || index >= CHERY_DTC_INDEX_COUNT) {
        return false;
    }

    state->history[index / 8u] |= index_mask(index);
    state->snapshot_index[slot] = index;
    return true;
}

bool chery_dtc_raise_c0(CheryDtcState *state, uint8_t index, bool inhibit_history)
{
    if (state == NULL || index >= CHERY_DTC_INDEX_COUNT) {
        return false;
    }
    uint8_t cell = (uint8_t)(index / 8u);
    uint8_t mask = index_mask(index);
    if ((state->current[cell] & mask) != 0u) {
        return true;
    }
    state->current[cell] |= mask;
    if (inhibit_history || (state->history[cell] & mask) != 0u) {
        return true;
    }
    for (size_t slot = 0; slot < CHERY_DTC_SNAPSHOT_COUNT; ++slot) {
        if (state->snapshot_index[slot] == UINT8_MAX) {
            return chery_dtc_store_snapshot(state, slot, index);
        }
    }
    state->history[cell] |= mask;
    return true;
}

static size_t build_read_reply(
    const CheryDtcState *state,
    uint8_t reply[CHERY_DTC_MAX_REPLY_BYTES]
)
{
    uint8_t has_snapshot[CHERY_DTC_BITMAP_BYTES] = {0};
    for (size_t slot = 0; slot < CHERY_DTC_SNAPSHOT_COUNT; ++slot) {
        uint8_t index = state->snapshot_index[slot];
        if (index < CHERY_DTC_INDEX_COUNT) {
            has_snapshot[index / 8u] |= index_mask(index);
        }
    }

    uint8_t count = 0;
    size_t length = 2;
    reply[0] = 0x57u;
    for (uint8_t index = 0; index < CHERY_DTC_INDEX_COUNT; ++index) {
        uint8_t cell = (uint8_t)(index / 8u);
        uint8_t mask = index_mask(index);
        if ((state->history[cell] & has_snapshot[cell] & mask) == 0u) {
            continue;
        }

        CheryDtcEntry dtc = dtc_table[index];
        if ((state->current[cell] & mask) != 0u) {
            dtc.inactive_status |= 0x20u;
        }
        reply[length++] = (uint8_t)(dtc.code >> 8);
        reply[length++] = (uint8_t)dtc.code;
        reply[length++] = dtc.inactive_status;
        ++count;
    }
    reply[1] = count;
    return length;
}

CheryDtcResult chery_dtc_respond(
    CheryDtcState *state,
    CheryDtcSession session,
    const uint8_t *request,
    size_t request_length,
    uint8_t *response,
    size_t response_capacity,
    size_t *response_length
)
{
    if (response_length == NULL) {
        return CHERY_DTC_INVALID_ARGUMENT;
    }
    *response_length = 0;
    if (state == NULL || request == NULL || request_length == 0 ||
        (response == NULL && response_capacity != 0)) {
        return CHERY_DTC_INVALID_ARGUMENT;
    }

    uint8_t service = request[0];
    if ((session.mode_bits & 0x90u) == 0u || (service != 0x17u && service != 0x14u)) {
        return CHERY_DTC_UNHANDLED;
    }

    uint8_t reply[CHERY_DTC_MAX_REPLY_BYTES] = {0x7Fu, service, 0x12u};
    size_t length = 3;
    bool clear = false;
    if ((session.permission_bits & 0x4Au) == 0u) {
        reply[2] = 0x80u;
    } else if (request_length == 3) {
        uint16_t group = (uint16_t)(((uint16_t)request[1] << 8) | request[2]);
        if (service == 0x17u && (group == 0xFF00u || group == 0x0000u)) {
            length = build_read_reply(state, reply);
        } else if (service == 0x14u && group == 0xFF00u) {
            reply[0] = 0x54u;
            reply[1] = 0xFFu;
            reply[2] = 0x00u;
            clear = true;
        } else if (service == 0x14u && group >= 0xFF01u &&
                   group <= 0xFF07u && group != 0xFF06u) {
            return CHERY_DTC_UNHANDLED;
        }
    }

    *response_length = length;
    if (response_capacity < length) {
        return CHERY_DTC_SHORT_BUFFER;
    }
    if (clear) {
        chery_dtc_init(state);
        state->clear_pending = true;
    }
    memcpy(response, reply, length);
    return CHERY_DTC_REPLIED;
}
