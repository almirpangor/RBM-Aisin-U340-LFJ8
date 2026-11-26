#include "chery_dtc_journal.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef uint8_t Record[CHERY_DTC_JOURNAL_RECORD_BYTES];

static void commit(Record record, const CheryDtcState *state, uint32_t generation)
{
    assert(chery_dtc_journal_encode(state, generation, record));
    record[CHERY_DTC_JOURNAL_BODY_BYTES] = CHERY_DTC_JOURNAL_COMMITTED;
}

static void expect_empty(const CheryDtcState *state)
{
    CheryDtcState empty;
    chery_dtc_init(&empty);
    assert(memcmp(state->history, empty.history, sizeof(empty.history)) == 0);
    assert(memcmp(state->current, empty.current, sizeof(empty.current)) == 0);
    assert(memcmp(state->snapshot_index, empty.snapshot_index, sizeof(empty.snapshot_index)) == 0);
    assert(!state->clear_pending);
}

typedef struct {
    const uint8_t *old_record;
    uint8_t *target;
    size_t prefix;
    bool publish;
    unsigned calls;
} ClearBackend;

static bool store_empty(void *context)
{
    ClearBackend *backend = context;
    uint8_t body[CHERY_DTC_JOURNAL_BODY_BYTES];
    CheryDtcState empty;
    chery_dtc_init(&empty);
    assert(chery_dtc_journal_encode(&empty, 0u, body));
    ++backend->calls;
    memcpy(backend->target, body, backend->prefix);
    if (!backend->publish) {
        return false;
    }
    assert(backend->prefix == sizeof body);
    backend->target[sizeof body] = CHERY_DTC_JOURNAL_COMMITTED;
    CheryDtcState verified;
    uint32_t generation = UINT32_MAX;
    assert(chery_dtc_journal_restore(backend->old_record, backend->target, &verified, &generation)
           == CHERY_DTC_JOURNAL_SLOT_1 && generation == 0u);
    expect_empty(&verified);
    return true;
}

static void test_clear_reply_after_publication(void)
{
    Record old_record, target;
    CheryDtcState active, restored;
    chery_dtc_init(&active);
    assert(chery_dtc_raise_c0(&active, 95, false));
    commit(old_record, &active, UINT32_MAX);
    const CheryDtcState before = active;
    ClearBackend backend = {.old_record = old_record, .target = target};
    const CheryDtcClearStore store = {.commit_empty = store_empty, .context = &backend};
    const CheryDtcSession session = {0x80u, 0x02u};
    const uint8_t request[] = {0x14u, 0xffu, 0x00u};
    const uint8_t sentinel[] = {0x5au, 0x5au, 0x5au};
    uint8_t reply[sizeof sentinel];
    memcpy(reply, sentinel, sizeof reply);
    size_t length = 0;
    assert(chery_dtc_respond_with_store(&active, session, request, sizeof request, reply,
                                       sizeof reply - 1u, &length, &store) == CHERY_DTC_SHORT_BUFFER);
    assert(length == 3u && backend.calls == 0 && memcmp(reply, sentinel, sizeof reply) == 0);

    for (size_t prefix = 0; prefix <= CHERY_DTC_JOURNAL_BODY_BYTES; ++prefix) {
        memset(target, CHERY_DTC_JOURNAL_UNCOMMITTED, sizeof target);
        backend.prefix = prefix;
        assert(chery_dtc_respond_with_store(&active, session, request, sizeof request, reply,
                                           sizeof reply, &length, &store) == CHERY_DTC_STORAGE_FAILURE);
        assert(length == 0 && memcmp(reply, sentinel, sizeof reply) == 0);
        assert(memcmp(&active, &before, sizeof active) == 0);
        uint32_t generation = 0;
        assert(chery_dtc_journal_restore(old_record, target, &restored, &generation)
               == CHERY_DTC_JOURNAL_SLOT_0);
        assert(generation == UINT32_MAX && restored.snapshot_index[0] == 95);
    }

    backend.publish = true;
    assert(chery_dtc_respond_with_store(&active, session, request, sizeof request, reply,
                                       sizeof reply, &length, &store) == CHERY_DTC_REPLIED);
    const uint8_t positive[] = {0x54u, 0xffu, 0x00u};
    assert(length == sizeof positive && memcmp(reply, positive, sizeof positive) == 0);
    assert(active.clear_pending && backend.calls == CHERY_DTC_JOURNAL_BODY_BYTES + 2u);
    uint32_t generation = UINT32_MAX;
    assert(chery_dtc_journal_restore(old_record, target, &restored, &generation) == CHERY_DTC_JOURNAL_SLOT_1);
    assert(generation == 0u);
    expect_empty(&restored);
}

int main(void)
{
    test_clear_reply_after_publication();
    Record old_record, clear_record, interrupted;
    CheryDtcState active, restored;
    uint32_t generation = 42;
    memset(old_record, 0xFF, sizeof(old_record));
    memset(clear_record, 0xFF, sizeof(clear_record));
    assert(chery_dtc_journal_restore(old_record, clear_record, &restored, &generation)
           == CHERY_DTC_JOURNAL_EMPTY);
    assert(generation == 42);
    expect_empty(&restored);

    chery_dtc_init(&active);
    assert(chery_dtc_raise_c0(&active, 95, false));
    active.history[1] = 0x80u; /* History without a visible snapshot. */
    active.clear_pending = true;
    commit(old_record, &active, UINT32_MAX);
    assert(chery_dtc_journal_restore(old_record, clear_record, &restored, &generation)
           == CHERY_DTC_JOURNAL_SLOT_0);
    assert(generation == UINT32_MAX);
    assert(restored.snapshot_index[0] == 95);
    assert(memcmp(restored.history, active.history, sizeof(active.history)) == 0);
    assert(restored.current[11] == 0 && !restored.clear_pending);

    const uint8_t request[] = {0x14, 0xFF, 0x00};
    uint8_t reply[3];
    size_t length;
    assert(chery_dtc_respond(&active, (CheryDtcSession){0x80, 0x02}, request, sizeof(request),
                             reply, sizeof(reply), &length) == CHERY_DTC_REPLIED);
    assert(length == 3 && reply[0] == 0x54 && active.clear_pending);
    commit(clear_record, &active, 0);

    for (size_t prefix = 0; prefix <= CHERY_DTC_JOURNAL_BODY_BYTES; ++prefix) {
        memset(interrupted, 0xFF, sizeof(interrupted));
        memcpy(interrupted, clear_record, prefix);
        assert(chery_dtc_journal_restore(old_record, interrupted, &restored, &generation)
               == CHERY_DTC_JOURNAL_SLOT_0);
        assert(generation == UINT32_MAX && restored.snapshot_index[0] == 95);

        /* Reuse the inactive slot after durable clear. Interrupted writes there
         * must retain the clear even if their payload resembles old history. */
        memset(interrupted, 0xFF, sizeof(interrupted));
        memcpy(interrupted, old_record, prefix);
        assert(chery_dtc_journal_restore(interrupted, clear_record, &restored, &generation)
               == CHERY_DTC_JOURNAL_SLOT_1);
        assert(generation == 0);
        expect_empty(&restored);
    }

    assert(chery_dtc_journal_restore(old_record, clear_record, &restored, &generation)
           == CHERY_DTC_JOURNAL_SLOT_1);
    assert(generation == 0);
    expect_empty(&restored);
    assert(chery_dtc_journal_restore(clear_record, old_record, &restored, &generation)
           == CHERY_DTC_JOURNAL_SLOT_0);
    expect_empty(&restored);

    for (size_t byte = 0; byte < sizeof(clear_record); ++byte) {
        for (unsigned bit = 0; bit < 8; ++bit) {
            memcpy(interrupted, clear_record, sizeof(interrupted));
            interrupted[byte] ^= (uint8_t)(1u << bit);
            assert(chery_dtc_journal_restore(old_record, interrupted, &restored, &generation)
                   == CHERY_DTC_JOURNAL_CORRUPT);
            expect_empty(&restored);
        }
    }
    commit(clear_record, &active, UINT32_MAX);
    assert(chery_dtc_journal_restore(old_record, clear_record, &restored, &generation)
           == CHERY_DTC_JOURNAL_CORRUPT);
    commit(clear_record, &active, 1);
    assert(chery_dtc_journal_restore(old_record, clear_record, &restored, &generation)
           == CHERY_DTC_JOURNAL_CORRUPT);
    active.snapshot_index[0] = CHERY_DTC_INDEX_COUNT;
    assert(!chery_dtc_journal_encode(&active, 1, clear_record));
    active.snapshot_index[0] = 95;
    assert(!chery_dtc_journal_encode(&active, 1, clear_record));

    puts("DTC journal: restore, wrap, clear, 30 interrupted prefixes and 240 bit faults PASS");
    puts("DTC journal: 30 unconfirmed clears withheld reply, one durable clear survived restart PASS");
    return 0;
}
