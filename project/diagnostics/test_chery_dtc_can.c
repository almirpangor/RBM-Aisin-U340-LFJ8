#include "chery_dtc_can.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>

static const CheryDtcSession session = {0x90u, 0x08u};
static const CheryDtcCanFrame read_request = {
    .id = 0x732u, .length = 8u, .data = {0x03u, 0x17u, 0xFFu, 0x00u}
};
static const CheryDtcCanFrame clear_request = {
    .id = 0x732u, .length = 8u, .data = {0x03u, 0x14u, 0xFFu, 0x00u}
};

static void expect_frame(const CheryDtcCanFrame *frame, const uint8_t expected[8])
{
    assert(frame->id == 0x722u && frame->length == 8u);
    assert(!frame->extended && !frame->remote && !frame->fd);
    assert(memcmp(frame->data, expected, 8) == 0);
}

static void test_single_frames(void)
{
    CheryDtcState state;
    CheryDtcCanReply reply;
    chery_dtc_init(&state);
    assert(chery_dtc_store_snapshot(&state, 0, 4));
    assert(chery_dtc_set_current(&state, 4, true));
    assert(chery_dtc_can_format_reply(&state, session, &read_request, &reply) == CHERY_DTC_REPLIED);
    assert(reply.count == 1);
    const uint8_t read_answer[8] = {0x05u, 0x57u, 0x01u, 0x07u, 0x10u, 0x74u};
    expect_frame(&reply.frames[0], read_answer);

    const CheryDtcSession denied = {0x90u, 0x01u};
    assert(chery_dtc_can_format_reply(&state, denied, &clear_request, &reply) == CHERY_DTC_REPLIED);
    const uint8_t refusal[8] = {0x03u, 0x7Fu, 0x14u, 0x80u};
    expect_frame(&reply.frames[0], refusal);
    assert(chery_dtc_can_format_reply(&state, session, &read_request, &reply) == CHERY_DTC_REPLIED);
    expect_frame(&reply.frames[0], read_answer);

    assert(chery_dtc_can_format_reply(&state, session, &clear_request, &reply) == CHERY_DTC_REPLIED);
    const uint8_t clear_answer[8] = {0x03u, 0x54u, 0xFFu, 0x00u};
    expect_frame(&reply.frames[0], clear_answer);
    assert(chery_dtc_can_format_reply(&state, session, &read_request, &reply) == CHERY_DTC_REPLIED);
    const uint8_t cleared[8] = {0x02u, 0x57u, 0x00u};
    expect_frame(&reply.frames[0], cleared);
}

static void test_segmented_reply(void)
{
    CheryDtcState state;
    CheryDtcCanReply reply;
    chery_dtc_init(&state);
    assert(chery_dtc_store_snapshot(&state, 0, 0x54u));
    assert(chery_dtc_store_snapshot(&state, 1, 0x32u));
    assert(chery_dtc_store_snapshot(&state, 2, 0x2Eu));
    assert(chery_dtc_store_snapshot(&state, 3, 0x2Fu));
    assert(chery_dtc_store_snapshot(&state, 4, 0x04u));
    assert(chery_dtc_set_current(&state, 0x2Eu, true));
    assert(chery_dtc_set_current(&state, 0x54u, true));

    assert(chery_dtc_can_format_reply(&state, session, &read_request, &reply) == CHERY_DTC_REPLIED);
    assert(reply.count == 3);
    const uint8_t first[8] = {0x10u, 0x11u, 0x57u, 0x05u, 0x07u, 0x10u, 0x54u, 0x27u};
    const uint8_t next[8] = {0x21u, 0x53u, 0x63u, 0x19u, 0x28u, 0x43u, 0x06u, 0x03u};
    const uint8_t last[8] = {0x22u, 0x40u, 0x02u, 0x18u, 0x60u};
    expect_frame(&reply.frames[0], first);
    expect_frame(&reply.frames[1], next);
    expect_frame(&reply.frames[2], last);
}

static void test_nonmatching_transport(void)
{
    CheryDtcState state;
    CheryDtcCanReply reply;
    chery_dtc_init(&state);
    assert(chery_dtc_store_snapshot(&state, 0, 4));
    const CheryDtcState before = state;
    CheryDtcCanFrame frame = clear_request;
    frame.id = 0x7E1u;
    assert(chery_dtc_can_format_reply(&state, session, &frame, &reply) == CHERY_DTC_UNHANDLED);
    assert(reply.count == 0);

    frame = clear_request;
    frame.length = 3;
    assert(chery_dtc_can_format_reply(&state, session, &frame, &reply) == CHERY_DTC_UNHANDLED);
    frame = clear_request;
    frame.fd = true;
    assert(chery_dtc_can_format_reply(&state, session, &frame, &reply) == CHERY_DTC_UNHANDLED);
    frame = clear_request;
    frame.data[0] = 0x30u;
    assert(chery_dtc_can_format_reply(&state, session, &frame, &reply) == CHERY_DTC_UNHANDLED);
    assert(memcmp(&state, &before, sizeof(state)) == 0);
}

int main(void)
{
    test_single_frames();
    test_segmented_reply();
    test_nonmatching_transport();
    puts("Chery C0 diagnostic CAN frame fixtures: passed");
    return 0;
}
