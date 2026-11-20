#include "chery_dtc_link.h"
#include "chery_model_monitor.h"

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

typedef struct {
    const CheryDtcLink *link;
    const CheryDtcState *dtc;
    const CheryDtcState *before;
    const CheryDtcLinkTx *outgoing;
    uint32_t token;
    unsigned calls;
    bool durable;
} ClearProbe;

static bool commit_probe(void *context)
{
    ClearProbe *probe = context;
    assert(probe->link->phase == CHERY_DTC_LINK_IDLE && probe->link->reply.count == 0u);
    assert(probe->link->tx_token == probe->token && probe->outgoing->token == probe->token);
    assert(memcmp(probe->dtc, probe->before, sizeof(*probe->dtc)) == 0);
    ++probe->calls;
    return probe->durable;
}

static void test_durable_clear_order(void)
{
    CheryDtcLink link;
    CheryDtcState dtc;
    CheryDtcLinkTx tx = {0};
    chery_dtc_link_init(&link);
    load_five_records(&dtc);
    const CheryDtcState before = dtc;
    ClearProbe probe = {.link = &link, .dtc = &dtc, .before = &before, .outgoing = &tx};
    const CheryDtcClearStore store = {.commit_empty = commit_probe, .context = &probe};

    assert(chery_dtc_link_receive_with_store(&link, &dtc, &clear_request, 0u, &tx, &store)
           == CHERY_DTC_LINK_FRAME_READY);
    const uint8_t denied[8] = {0x03, 0x7f, 0x14, 0x80};
    expect_frame(&tx, denied);
    assert(probe.calls == 0 && memcmp(&dtc, &before, sizeof dtc) == 0);
    assert(chery_dtc_link_confirm_tx(&link, tx.token, 1u, &tx) == CHERY_DTC_LINK_COMPLETE);

    assert(chery_dtc_link_receive_with_store(&link, &dtc, &open_session, 2u, &tx, &store)
           == CHERY_DTC_LINK_FRAME_READY);
    assert(chery_dtc_link_receive_with_store(&link, &dtc, &clear_request, 3u, &tx, &store)
           == CHERY_DTC_LINK_IGNORED);
    assert(probe.calls == 0);
    assert(chery_dtc_link_confirm_tx(&link, tx.token, 4u, &tx) == CHERY_DTC_LINK_COMPLETE);
    probe.token = tx.token;

    const CheryDtcClearStore unavailable = {0};
    assert(chery_dtc_link_receive_with_store(&link, &dtc, &clear_request, 5u, &tx, &unavailable)
           == CHERY_DTC_LINK_STORAGE_FAILURE);
    assert(chery_dtc_link_receive_with_store(&link, &dtc, &clear_request, 6u, &tx, &store)
           == CHERY_DTC_LINK_STORAGE_FAILURE);
    assert(probe.calls == 1 && link.tx_token == probe.token && tx.token == probe.token);
    assert(link.phase == CHERY_DTC_LINK_IDLE && link.reply.count == 0u);
    assert(memcmp(&dtc, &before, sizeof dtc) == 0);
    const uint8_t opened[8] = {0x02, 0x50, 0x86};
    expect_frame(&tx, opened);

    probe.durable = true;
    assert(chery_dtc_link_receive_with_store(&link, &dtc, &clear_request, 7u, &tx, &store)
           == CHERY_DTC_LINK_FRAME_READY);
    const uint8_t cleared[8] = {0x03, 0x54, 0xff, 0x00};
    expect_frame(&tx, cleared);
    assert(probe.calls == 2 && tx.token == probe.token + 1u && dtc.clear_pending);
    assert(chery_dtc_link_confirm_tx(&link, tx.token, 8u, &tx) == CHERY_DTC_LINK_COMPLETE);
    assert(chery_dtc_link_receive_with_store(&link, &dtc, &read_request, 9u, &tx, &store)
           == CHERY_DTC_LINK_FRAME_READY);
    const uint8_t empty[8] = {0x02, 0x57, 0x00};
    expect_frame(&tx, empty);
    assert(probe.calls == 2);
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

static void count_to_last_session_step(CheryDtcLink *link)
{
    for (unsigned event = 1; event < CHERY_DTC_LINK_SESSION_STEPS; ++event) {
        assert(!chery_dtc_link_session_step(link));
        assert(link->session.permission_bits == 0x08);
    }
}

static void test_session_timer_reload_and_expiry(void)
{
    CheryDtcLink link;
    CheryDtcState dtc;
    CheryDtcLinkTx tx;
    chery_dtc_link_init(&link);
    chery_dtc_init(&dtc);
    assert(!chery_dtc_link_session_step(NULL) && !chery_dtc_link_session_step(&link));
    assert(chery_dtc_store_snapshot(&dtc, 0, 4));
    open_authorized(&link, &dtc, 0);
    assert(!chery_dtc_link_expire(&link, 2000)); /* Idle transport uses no session steps. */
    count_to_last_session_step(&link);

    CheryDtcCanFrame unsupported = {
        .id = CHERY_DTC_CAN_REQUEST_ID, .length = 2, .data = {1, 0x99},
    };
    assert(chery_dtc_link_receive(&link, &dtc, &unsupported, 2001, &tx) == CHERY_DTC_LINK_IGNORED);
    count_to_last_session_step(&link); /* The unsupported SID reached the dispatcher. */
    unsupported.id = 0x733;
    assert(chery_dtc_link_receive(&link, &dtc, &unsupported, 2002, &tx) == CHERY_DTC_LINK_IGNORED);
    unsupported.id = CHERY_DTC_CAN_REQUEST_ID;
    unsupported.data[0] = 2; /* Declared payload exceeds DLC. */
    assert(chery_dtc_link_receive(&link, &dtc, &unsupported, 2003, &tx) == CHERY_DTC_LINK_IGNORED);
    assert(chery_dtc_link_session_step(&link) && !chery_dtc_link_session_step(&link));
    assert(link.session.mode_bits == 0x9f && link.session.permission_bits == 0x11);

    const CheryDtcCanFrame clear = {
        .id = CHERY_DTC_CAN_REQUEST_ID, .length = 4, .data = {3, 0x14, 0xff, 0},
    };
    assert(chery_dtc_link_receive(&link, &dtc, &clear, 2004, &tx) == CHERY_DTC_LINK_FRAME_READY);
    expect_frame(&tx, (const uint8_t[8]){3, 0x7f, 0x14, 0x80});
    assert(dtc.snapshot_index[0] == 4);
}

static void test_session_timer_discards_segmented_reply(void)
{
    CheryDtcLink link;
    CheryDtcState dtc;
    CheryDtcLinkTx tx;
    chery_dtc_link_init(&link);
    chery_dtc_init(&dtc);
    load_five_records(&dtc);
    open_authorized(&link, &dtc, 0);
    const CheryDtcCanFrame read = {
        .id = CHERY_DTC_CAN_REQUEST_ID, .length = 4, .data = {3, 0x17, 0xff, 0},
    };
    assert(chery_dtc_link_receive(&link, &dtc, &read, 2, &tx) == CHERY_DTC_LINK_FRAME_READY);
    const uint32_t first_frame = tx.token;
    assert(chery_dtc_link_confirm_tx(&link, first_frame, 3, &tx) == CHERY_DTC_LINK_WAITING);
    count_to_last_session_step(&link);
    assert(chery_dtc_link_session_step(&link));
    const CheryDtcCanFrame fc = {
        .id = CHERY_DTC_CAN_REQUEST_ID, .length = 3, .data = {0x30, 0, 0},
    };
    assert(chery_dtc_link_receive(&link, &dtc, &fc, 4, &tx) == CHERY_DTC_LINK_IGNORED);
    assert(chery_dtc_link_confirm_tx(&link, first_frame, 5, &tx) == CHERY_DTC_LINK_IGNORED);
    assert(link.phase == CHERY_DTC_LINK_IDLE && link.session.mode_bits == 0x9f);
}

static void expect_model_records(CheryDtcLink *link, CheryDtcState *dtc, uint32_t tick,
                                 uint8_t limit_status, uint8_t now_status)
{
    CheryDtcLinkTx tx;
    const uint8_t first[8] = {0x10, 0x08, 0x57, 2, 0xd1, 0x2b, limit_status, 0xd1};
    const uint8_t last[8] = {0x21, 0x20, now_status};
    assert(chery_dtc_link_receive(link, dtc, &read_request, tick, &tx) == CHERY_DTC_LINK_FRAME_READY);
    expect_frame(&tx, first);
    assert(chery_dtc_link_confirm_tx(link, tx.token, tick + 1, &tx) == CHERY_DTC_LINK_WAITING);
    assert(chery_dtc_link_receive(link, dtc, &flow_control, tick + 2, &tx) == CHERY_DTC_LINK_FRAME_READY);
    expect_frame(&tx, last);
    assert(chery_dtc_link_confirm_tx(link, tx.token, tick + 3, &tx) == CHERY_DTC_LINK_COMPLETE);
}

static void sample_model_message(CheryModelMonitor *monitor, CheryDtcState *dtc, Ta2005CheryInputs *receiver,
                                 const CheryModelContext *context, uint32_t tick, const uint8_t payload[8])
{
    Ta2005CherySnapshot snapshot;
    if (payload != NULL) {
        assert(ta2005_chery_inputs_receive(receiver, 0x0fa, 8, payload, &tick));
    }
    unsigned available = ta2005_chery_inputs_snapshot(receiver, &tick, 5, &snapshot);
    assert(available == (payload != NULL ? TA2005_CHERY_SPEED : 0));
    chery_model_monitor_task2(monitor, dtc, &snapshot, context);
}

static void test_model_field_loss_and_recovery(void)
{
    CheryDtcLink link;
    CheryDtcState dtc;
    CheryDtcLinkTx tx;
    CheryModelMonitor monitor;
    const CheryModelContext context = {0};
    Ta2005CheryInputs receiver;
    uint8_t payload[8] = {0x12, 0xc0, 95, 0xff, 0, 35, 0, 0};
    uint32_t tick = 0;
    chery_dtc_link_init(&link);
    chery_dtc_init(&dtc);
    chery_model_monitor_init(&monitor);
    open_authorized(&link, &dtc, tick);
    ta2005_chery_inputs_reset(&receiver);
    sample_model_message(&monitor, &dtc, &receiver, &context, tick, payload);
    assert(monitor.now_code == 95 && monitor.limit_code == 35);

    tick = 5;
    for (unsigned i = 0; i < 101; ++i) {
        sample_model_message(&monitor, &dtc, &receiver, &context, tick++, NULL);
    }
    assert(dtc.current[2] == 0 && dtc.history[2] == 0 && monitor.limit_pending);
    sample_model_message(&monitor, &dtc, &receiver, &context, tick++, NULL);
    assert(monitor.now_failed && !monitor.limit_pending && dtc.current[2] == 5);
    assert(monitor.now_code == 95 && monitor.limit_code == 35);
    expect_model_records(&link, &dtc, 120, 0x6f, 0x6f);

    payload[2] = 88;
    payload[5] = UINT8_MAX;
    for (unsigned i = 0; i < 251; ++i) {
        sample_model_message(&monitor, &dtc, &receiver, &context, tick++, payload);
    }
    assert(monitor.now_failed && monitor.now_code == 95 && dtc.current[2] == 5);
    sample_model_message(&monitor, &dtc, &receiver, &context, tick++, payload);
    assert(!monitor.now_failed && monitor.now_code == 88);
    expect_model_records(&link, &dtc, 380, 0x6f, 0x4f);
    payload[5] = 24;
    for (unsigned i = 0; i < 252; ++i) {
        sample_model_message(&monitor, &dtc, &receiver, &context, tick++, payload);
    }
    assert(monitor.limit_code == 24 && dtc.current[2] == 0);
    expect_model_records(&link, &dtc, 640, 0x4f, 0x4f);
    assert(chery_dtc_link_receive(&link, &dtc, &clear_request, 645, &tx) == CHERY_DTC_LINK_FRAME_READY);
    const uint8_t cleared[8] = {0x03, 0x54, 0xff, 0x00};
    expect_frame(&tx, cleared);
    assert(chery_dtc_link_confirm_tx(&link, tx.token, 646, &tx) == CHERY_DTC_LINK_COMPLETE);
    assert(chery_dtc_link_receive(&link, &dtc, &read_request, 647, &tx) == CHERY_DTC_LINK_FRAME_READY);
    const uint8_t empty[8] = {0x02, 0x57, 0};
    expect_frame(&tx, empty);
    assert(chery_dtc_link_confirm_tx(&link, tx.token, 648, &tx) == CHERY_DTC_LINK_COMPLETE);
}

int main(void)
{
    test_durable_clear_order();
    test_cold_permission_and_session_end();
    test_flow_control_and_continuations();
    test_out_of_profile_flow_control();
    test_timeouts_and_wrap();
    test_session_timer_reload_and_expiry();
    test_session_timer_discards_segmented_reply();
    test_model_field_loss_and_recovery();
    puts("Chery C0 diagnostic link and independent model-field loss and recovery: passed");
    puts("Chery C0 durable clear: storage before TX, no acknowledgement on failure, retry passed.");
    return 0;
}
