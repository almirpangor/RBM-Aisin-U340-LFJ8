#include "chery_dtc_link.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>

static const CheryDtcCanFrame open_session = {
    .id = 0x732u, .length = 8u, .data = {0x02u, 0x10u, 0x86u}
};
static const CheryDtcCanFrame read_request = {
    .id = 0x732u, .length = 8u, .data = {0x03u, 0x17u, 0xFFu, 0x00u}
};
static const CheryDtcCanFrame clear_request = {
    .id = 0x732u, .length = 8u, .data = {0x03u, 0x14u, 0xFFu, 0x00u}
};
static const CheryDtcCanFrame flow_control = {
    .id = 0x732u, .length = 3u, .data = {0x30u, 0x00u, 0x00u}
};

static void expect_frame(const CheryDtcLinkTx *tx, const uint8_t data[8])
{
    assert(tx->frame.id == 0x722u && tx->frame.length == 8u);
    assert(!tx->frame.extended && !tx->frame.remote && !tx->frame.fd);
    assert(memcmp(tx->frame.data, data, 8) == 0);
}

static void open_authorized(CheryDtcLink *link, CheryDtcState *dtc, uint32_t tick)
{
    CheryDtcLinkTx tx;
    assert(chery_dtc_link_receive(link, dtc, &open_session, tick, &tx)
           == CHERY_DTC_LINK_FRAME_READY);
    const uint8_t expected[8] = {0x02u, 0x50u, 0x86u};
    expect_frame(&tx, expected);
    assert(link->session.mode_bits == 0x90u && link->session.permission_bits == 0x08u);
    assert(chery_dtc_link_confirm_tx(link, tx.token, tick + 1u, &tx)
           == CHERY_DTC_LINK_COMPLETE);
}

static void load_five_records(CheryDtcState *dtc)
{
    chery_dtc_init(dtc);
    assert(chery_dtc_store_snapshot(dtc, 0, 0x54u));
    assert(chery_dtc_store_snapshot(dtc, 1, 0x32u));
    assert(chery_dtc_store_snapshot(dtc, 2, 0x2Eu));
    assert(chery_dtc_store_snapshot(dtc, 3, 0x2Fu));
    assert(chery_dtc_store_snapshot(dtc, 4, 0x04u));
    assert(chery_dtc_set_current(dtc, 0x2Eu, true));
    assert(chery_dtc_set_current(dtc, 0x54u, true));
}

static void test_cold_permission_and_session_end(void)
{
    CheryDtcLink link;
    CheryDtcState dtc;
    CheryDtcLinkTx tx;
    chery_dtc_link_init(&link);
    chery_dtc_init(&dtc);
    assert(link.session.mode_bits == 0x9Fu && link.session.permission_bits == 0x11u);
    assert(chery_dtc_store_snapshot(&dtc, 0, 4));

    assert(chery_dtc_link_receive(&link, &dtc, &clear_request, 3u, &tx)
           == CHERY_DTC_LINK_FRAME_READY);
    const uint8_t denied[8] = {0x03u, 0x7Fu, 0x14u, 0x80u};
    expect_frame(&tx, denied);
    assert(dtc.snapshot_index[0] == 4 && link.session.permission_bits == 0x01u);
    assert(chery_dtc_link_confirm_tx(&link, tx.token, 4u, &tx)
           == CHERY_DTC_LINK_COMPLETE);

    open_authorized(&link, &dtc, 5u);
    assert(chery_dtc_link_receive(&link, &dtc, &read_request, 7u, &tx)
           == CHERY_DTC_LINK_FRAME_READY);
    const uint8_t stored[8] = {0x05u, 0x57u, 0x01u, 0x07u, 0x10u, 0x54u};
    expect_frame(&tx, stored);
    assert(chery_dtc_link_confirm_tx(&link, tx.token, 8u, &tx)
           == CHERY_DTC_LINK_COMPLETE);
    assert(chery_dtc_link_receive(&link, &dtc, &clear_request, 9u, &tx)
           == CHERY_DTC_LINK_FRAME_READY);
    const uint8_t cleared[8] = {0x03u, 0x54u, 0xFFu, 0x00u};
    expect_frame(&tx, cleared);
    assert(dtc.snapshot_index[0] == UINT8_MAX);
    const uint32_t old_token = tx.token;
    chery_dtc_link_end_session(&link);
    assert(link.phase == CHERY_DTC_LINK_IDLE && link.session.mode_bits == 0x9Fu);
    assert(chery_dtc_link_confirm_tx(&link, old_token, 10u, &tx)
           == CHERY_DTC_LINK_IGNORED);
}

static void test_flow_control_and_continuations(void)
{
    CheryDtcLink link;
    CheryDtcState dtc;
    CheryDtcLinkTx tx;
    chery_dtc_link_init(&link);
    load_five_records(&dtc);
    open_authorized(&link, &dtc, 0u);
    assert(chery_dtc_link_receive(&link, &dtc, &read_request, 2u, &tx)
           == CHERY_DTC_LINK_FRAME_READY);
    const uint8_t first[8] = {0x10u, 0x11u, 0x57u, 0x05u, 0x07u, 0x10u, 0x54u, 0x27u};
    expect_frame(&tx, first);
    const uint32_t first_token = tx.token;
    assert(chery_dtc_link_receive(&link, &dtc, &flow_control, 3u, &tx)
           == CHERY_DTC_LINK_IGNORED);
    assert(chery_dtc_link_confirm_tx(&link, first_token, 4u, &tx)
           == CHERY_DTC_LINK_WAITING);
    assert(link.phase == CHERY_DTC_LINK_AWAITING_FLOW_CONTROL);

    CheryDtcCanFrame wrong_id = flow_control;
    wrong_id.id = 0x7E1u;
    assert(chery_dtc_link_receive(&link, &dtc, &wrong_id, 5u, &tx)
           == CHERY_DTC_LINK_IGNORED);
    assert(chery_dtc_link_receive(&link, &dtc, &clear_request, 6u, &tx)
           == CHERY_DTC_LINK_IGNORED);
    assert(chery_dtc_link_receive(&link, &dtc, &flow_control, 7u, &tx)
           == CHERY_DTC_LINK_FRAME_READY);
    const uint8_t cf1[8] = {0x21u, 0x53u, 0x63u, 0x19u, 0x28u, 0x43u, 0x06u, 0x03u};
    expect_frame(&tx, cf1);
    assert(chery_dtc_link_confirm_tx(&link, first_token, 8u, &tx)
           == CHERY_DTC_LINK_IGNORED);
    const uint32_t cf1_token = tx.token;
    assert(chery_dtc_link_confirm_tx(&link, cf1_token, 9u, &tx)
           == CHERY_DTC_LINK_FRAME_READY);
    const uint8_t cf2[8] = {0x22u, 0x40u, 0x02u, 0x18u, 0x60u};
    expect_frame(&tx, cf2);
    assert(chery_dtc_link_confirm_tx(&link, tx.token, 10u, &tx)
           == CHERY_DTC_LINK_COMPLETE);
    assert(link.phase == CHERY_DTC_LINK_IDLE);
}

static void test_out_of_profile_flow_control(void)
{
    CheryDtcLink link;
    CheryDtcState dtc;
    CheryDtcLinkTx tx;
    const CheryDtcCanFrame unsupported[] = {
        {.id = 0x732u, .length = 3u, .data = {0x31u}},
        {.id = 0x732u, .length = 3u, .data = {0x32u}},
        {.id = 0x732u, .length = 3u, .data = {0x30u, 0x01u}},
        {.id = 0x732u, .length = 3u, .data = {0x30u, 0x00u, 0x05u}},
        {.id = 0x732u, .length = 2u, .data = {0x30u}}
    };
    chery_dtc_link_init(&link);
    load_five_records(&dtc);
    open_authorized(&link, &dtc, 0u);

    for (size_t i = 0; i < sizeof(unsupported) / sizeof(unsupported[0]); ++i) {
        const uint32_t tick = 10u + 10u * (uint32_t)i;
        assert(chery_dtc_link_receive(&link, &dtc, &read_request, tick, &tx)
               == CHERY_DTC_LINK_FRAME_READY);
        assert(chery_dtc_link_confirm_tx(&link, tx.token, tick + 1u, &tx)
               == CHERY_DTC_LINK_WAITING);
        assert(chery_dtc_link_receive(&link, &dtc, &unsupported[i], tick + 2u, &tx)
               == CHERY_DTC_LINK_ABORTED);
        assert(link.phase == CHERY_DTC_LINK_IDLE && link.session.permission_bits == 0x08u);
    }
}

static void test_timeouts_and_wrap(void)
{
    CheryDtcLink link;
    CheryDtcState dtc;
    CheryDtcLinkTx tx;
    chery_dtc_link_init(&link);
    load_five_records(&dtc);
    const uint32_t start = UINT32_MAX - 80u;
    open_authorized(&link, &dtc, start - 2u);
    assert(chery_dtc_link_receive(&link, &dtc, &read_request, start, &tx)
           == CHERY_DTC_LINK_FRAME_READY);
    const uint32_t stale_token = tx.token;
    assert(!chery_dtc_link_expire(&link, start + CHERY_DTC_LINK_TX_CONFIRM_TICKS - 1u));
    assert(chery_dtc_link_expire(&link, start + CHERY_DTC_LINK_TX_CONFIRM_TICKS));

    const uint32_t retry = start + CHERY_DTC_LINK_TX_CONFIRM_TICKS + 1u;
    assert(chery_dtc_link_receive(&link, &dtc, &read_request, retry, &tx)
           == CHERY_DTC_LINK_FRAME_READY);
    assert(chery_dtc_link_confirm_tx(&link, stale_token, retry, &tx)
           == CHERY_DTC_LINK_IGNORED);
    assert(chery_dtc_link_confirm_tx(&link, tx.token, retry + 1u, &tx)
           == CHERY_DTC_LINK_WAITING);
    assert(!chery_dtc_link_expire(&link, retry + CHERY_DTC_LINK_FLOW_CONTROL_TICKS));
    assert(chery_dtc_link_receive(
        &link, &dtc, &flow_control, retry + 1u + CHERY_DTC_LINK_FLOW_CONTROL_TICKS, &tx
    ) == CHERY_DTC_LINK_ABORTED);
    assert(link.phase == CHERY_DTC_LINK_IDLE && link.session.permission_bits == 0x08u);
}

int main(void)
{
    test_cold_permission_and_session_end();
    test_flow_control_and_continuations();
    test_out_of_profile_flow_control();
    test_timeouts_and_wrap();
    puts("Chery C0 diagnostic link: passed");
    return 0;
}
