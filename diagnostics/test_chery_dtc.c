#include "chery_dtc.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>

static const CheryDtcSession authorized = {0x90u, 0x4Au};
static const uint8_t read_all[] = {0x17u, 0xFFu, 0x00u};
static const uint8_t clear_all[] = {0x14u, 0xFFu, 0x00u};
static const uint8_t empty_report[] = {0x57u, 0x00u};

static void expect_reply(
    CheryDtcState *state,
    CheryDtcSession session,
    const uint8_t *request,
    size_t request_length,
    const uint8_t *expected,
    size_t expected_length
)
{
    uint8_t response[CHERY_DTC_MAX_REPLY_BYTES];
    memset(response, 0xA5, sizeof(response));
    size_t length = 0;
    assert(chery_dtc_respond(
        state, session, request, request_length, response, sizeof(response), &length
    ) == CHERY_DTC_REPLIED);
    assert(length == expected_length);
    assert(memcmp(response, expected, length) == 0);
    for (size_t index = length; index < sizeof(response); ++index) {
        assert(response[index] == 0xA5u);
    }
}

static void test_fault_history_clear_and_recurrence(void)
{
    CheryDtcState state;
    chery_dtc_init(&state);
    expect_reply(&state, authorized, read_all, sizeof(read_all), empty_report, sizeof(empty_report));

    assert(chery_dtc_set_current(&state, 0x04u, true));
    expect_reply(&state, authorized, read_all, sizeof(read_all), empty_report, sizeof(empty_report));
    assert(chery_dtc_store_snapshot(&state, 4, 0x04u));

    const uint8_t current_report[] = {0x57u, 1u, 0x07u, 0x10u, 0x74u};
    expect_reply(&state, authorized, read_all, sizeof(read_all), current_report, sizeof(current_report));
    assert(chery_dtc_set_current(&state, 0x04u, false));
    const uint8_t stored_report[] = {0x57u, 1u, 0x07u, 0x10u, 0x54u};
    const uint8_t read_group_zero[] = {0x17u, 0x00u, 0x00u};
    expect_reply(
        &state, authorized, read_group_zero, sizeof(read_group_zero), stored_report, sizeof(stored_report)
    );

    assert(chery_dtc_set_current(&state, 0x04u, true));
    const uint8_t positive_clear[] = {0x54u, 0xFFu, 0x00u};
    expect_reply(&state, authorized, clear_all, sizeof(clear_all), positive_clear, sizeof(positive_clear));
    expect_reply(&state, authorized, read_all, sizeof(read_all), empty_report, sizeof(empty_report));
    for (size_t cell = 0; cell < CHERY_DTC_BITMAP_BYTES; ++cell) {
        assert(state.history[cell] == 0u);
        assert(state.current[cell] == 0u);
    }
    for (size_t slot = 0; slot < CHERY_DTC_SNAPSHOT_COUNT; ++slot) {
        assert(state.snapshot_index[slot] == UINT8_MAX);
    }

    assert(chery_dtc_set_current(&state, 0x04u, true));
    expect_reply(&state, authorized, read_all, sizeof(read_all), empty_report, sizeof(empty_report));
    assert(chery_dtc_store_snapshot(&state, 0, 0x04u));
    expect_reply(&state, authorized, read_all, sizeof(read_all), current_report, sizeof(current_report));
}

static void test_snapshot_count_order_and_matching(void)
{
    CheryDtcState state;
    chery_dtc_init(&state);
    assert(chery_dtc_store_snapshot(&state, 0, 0x54u));
    assert(chery_dtc_store_snapshot(&state, 1, 0x32u));
    assert(chery_dtc_store_snapshot(&state, 2, 0x2Eu));
    assert(chery_dtc_store_snapshot(&state, 3, 0x2Fu));
    assert(chery_dtc_store_snapshot(&state, 4, 0x04u));
    assert(chery_dtc_set_current(&state, 0x2Eu, true));
    assert(chery_dtc_set_current(&state, 0x54u, true));
    const uint8_t five_records[] = {
        0x57u, 5u,
        0x07u, 0x10u, 0x54u,
        0x27u, 0x53u, 0x63u,
        0x19u, 0x28u, 0x43u,
        0x06u, 0x03u, 0x40u,
        0x02u, 0x18u, 0x60u
    };
    expect_reply(&state, authorized, read_all, sizeof(read_all), five_records, sizeof(five_records));

    assert(chery_dtc_store_snapshot(&state, 4, 0x32u));
    const uint8_t four_records[] = {
        0x57u, 4u, 0x27u, 0x53u, 0x63u, 0x19u, 0x28u, 0x43u,
        0x06u, 0x03u, 0x40u, 0x02u, 0x18u, 0x60u
    };
    expect_reply(&state, authorized, read_all, sizeof(read_all), four_records, sizeof(four_records));
    assert(!chery_dtc_store_snapshot(&state, CHERY_DTC_SNAPSHOT_COUNT, 0x04u));
    assert(!chery_dtc_store_snapshot(&state, 0, CHERY_DTC_INDEX_COUNT));
    assert(!chery_dtc_set_current(&state, UINT8_MAX, true));
}

static void test_dispatch_and_transactional_clear(void)
{
    CheryDtcState state;
    chery_dtc_init(&state);
    assert(chery_dtc_store_snapshot(&state, 0, 0x2Eu));
    uint8_t response[CHERY_DTC_MAX_REPLY_BYTES] = {0xA5u};
    size_t length = 0;

    const CheryDtcSession disallowed = {0x90u, 0x01u};
    const uint8_t denied_reply[] = {0x7Fu, 0x14u, 0x80u};
    expect_reply(&state, disallowed, clear_all, sizeof(clear_all), denied_reply, sizeof(denied_reply));

    const uint8_t invalid_group[] = {0x14u, 0xFFu, 0xFFu};
    const uint8_t parameter_error[] = {0x7Fu, 0x14u, 0x12u};
    expect_reply(&state, authorized, invalid_group, sizeof(invalid_group), parameter_error, 3);
    expect_reply(&state, authorized, clear_all, 2, parameter_error, 3);

    const uint8_t invalid_read[] = {0x17u, 0xFFu, 0x01u};
    const uint8_t read_error[] = {0x7Fu, 0x17u, 0x12u};
    expect_reply(&state, authorized, invalid_read, sizeof(invalid_read), read_error, 3);

    const uint8_t delegated_group[] = {0x14u, 0xFFu, 0x01u};
    assert(chery_dtc_respond(
        &state, authorized, delegated_group, sizeof(delegated_group), response, sizeof(response), &length
    ) == CHERY_DTC_UNHANDLED);
    assert(length == 0);
    const CheryDtcSession legacy = {0x01u, 0x10u};
    assert(chery_dtc_respond(
        &state, legacy, read_all, sizeof(read_all), response, sizeof(response), &length
    ) == CHERY_DTC_UNHANDLED);

    assert(chery_dtc_respond(
        &state, authorized, clear_all, sizeof(clear_all), response, 2, &length
    ) == CHERY_DTC_SHORT_BUFFER);
    assert(length == 3 && response[0] == 0xA5u);
    assert(chery_dtc_respond(
        &state, authorized, clear_all, sizeof(clear_all), NULL, 0, &length
    ) == CHERY_DTC_SHORT_BUFFER);
    assert(length == 3);
    const uint8_t inherited[] = {0x57u, 1u, 0x27u, 0x53u, 0x43u};
    expect_reply(&state, authorized, read_all, sizeof(read_all), inherited, sizeof(inherited));

    memcpy(response, clear_all, sizeof(clear_all));
    assert(chery_dtc_respond(
        &state, authorized, response, sizeof(clear_all), response, sizeof(response), &length
    ) == CHERY_DTC_REPLIED);
    assert(length == 3 && response[0] == 0x54u && response[1] == 0xFFu && response[2] == 0x00u);
    expect_reply(&state, authorized, read_all, sizeof(read_all), empty_report, sizeof(empty_report));
}

int main(void)
{
    test_fault_history_clear_and_recurrence();
    test_snapshot_count_order_and_matching();
    test_dispatch_and_transactional_clear();
    puts("Chery DTC read, clear and recurrence: passed");
    return 0;
}
