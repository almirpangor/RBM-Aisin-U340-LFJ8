#include "lfj8_h03_dtc_can.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>

enum {
    CAN0_CNT = 0x801000,
    CAN0_STAT = 0x801002,
    CAN0_EXTID = 0x801004,
    CAN0_TIMESTAMP = 0x801008,
    CAN0_MODE = 0x801018,
    CAN0_MSC13 = 0x80105d,
    CAN0_SLOT13 = 0x8011d0,
    OEM_CAN_STATE = 0x806ae6,
};

typedef struct {
    uint8_t slot[16];
    uint8_t control;
    uint8_t mode;
    uint8_t oem_state;
    uint16_t cnt;
    uint16_t stat;
    uint16_t extid;
    uint16_t now;
    unsigned requests;
    unsigned aborts;
    unsigned writes;
    unsigned critical;
} CanShadow;

static uint8_t read8(void *context, uint32_t address)
{
    const CanShadow *shadow = context;
    assert(shadow->critical == 1);
    switch (address) {
        case CAN0_MSC13: return shadow->control;
        case CAN0_MODE: return shadow->mode;
        case OEM_CAN_STATE: return shadow->oem_state;
        default:
            assert(address >= CAN0_SLOT13 && address < CAN0_SLOT13 + 16);
            assert((shadow->control & 2u) == 0u);
            return shadow->slot[address - CAN0_SLOT13];
    }
}

static uint16_t read16(void *context, uint32_t address)
{
    const CanShadow *shadow = context;
    assert(shadow->critical == 1);
    switch (address) {
        case CAN0_CNT: return shadow->cnt;
        case CAN0_STAT: return shadow->stat;
        case CAN0_EXTID: return shadow->extid;
        case CAN0_TIMESTAMP: return shadow->now;
        default:
            assert(address == CAN0_SLOT13 + 14);
            assert((shadow->control & 2u) == 0u);
            return (uint16_t)((uint16_t)shadow->slot[14] << 8 | shadow->slot[15]);
    }
}

static void write8(void *context, uint32_t address, uint8_t value)
{
    CanShadow *shadow = context;
    assert(shadow->critical == 1);
    assert(shadow->stat == 0u);
    ++shadow->writes;
    if (address == CAN0_MSC13) {
        if (value == 0x0f) {
            assert(shadow->control == 0x80 || shadow->control == 0x82);
            shadow->control &= 2u;
            ++shadow->aborts;
        } else {
            assert(value == 0 || value == 0x80);
            assert(shadow->control == 0 || shadow->control == 1 || shadow->control == 0x81);
            shadow->control = value;
            shadow->requests += value == 0x80;
        }
    } else {
        assert(address >= CAN0_SLOT13 && address < CAN0_SLOT13 + 14);
        assert(shadow->control == 0);
        shadow->slot[address - CAN0_SLOT13] = value;
    }
}

static uint32_t enter(void *context)
{
    CanShadow *shadow = context;
    assert(shadow->critical == 0);
    shadow->critical = 1;
    return 0x41;
}

static void leave(void *context, uint32_t saved)
{
    CanShadow *shadow = context;
    assert(saved == 0x41 && shadow->critical == 1);
    shadow->critical = 0;
}

static Lfj8H03DtcReceive rx(uint32_t generation, uint16_t stamp, uint8_t length,
                            uint8_t first, uint8_t second, uint8_t third)
{
    return (Lfj8H03DtcReceive){
        .frame = {.id = 0x732, .length = length, .data = {first, second, third}},
        .generation = generation, .can_timestamp = stamp,
    };
}

static void complete(CanShadow *shadow, uint16_t stamp, uint8_t control)
{
    assert(shadow->control == 0x80 || shadow->control == 0x82 || shadow->control == 2u);
    shadow->slot[14] = (uint8_t)(stamp >> 8);
    shadow->slot[15] = (uint8_t)stamp;
    shadow->control = control;
}

static void expect_reply(const CanShadow *shadow, const uint8_t expected[8])
{
    assert(shadow->slot[0] == (0x722u >> 6));
    assert(shadow->slot[1] == (0x722u & 0x3fu));
    assert(shadow->slot[5] == 8u);
    assert(memcmp(&shadow->slot[6], expected, 8) == 0);
}

static void test_basiccan_decode(void)
{
    uint8_t slot[16] = {0x1c, 0x32, 0, 0, 0, 3, 0x30, 0, 0, 0xff, 0, 0, 0, 0, 0xff, 0xfe};
    Lfj8H03DtcReceive capture;
    assert(lfj8_h03_dtc_can_decode_basic(&capture, slot, 0x41, false, 42));
    assert(capture.frame.id == 0x732 && capture.frame.length == 3);
    assert(!capture.frame.extended && !capture.frame.remote && !capture.frame.fd);
    assert(capture.frame.data[0] == 0x30 && capture.frame.data[3] == 0);
    assert(capture.can_timestamp == 0xfffe && capture.generation == 42);
    assert(!lfj8_h03_dtc_can_decode_basic(&capture, slot, 0x41, true, 42));
    assert(!lfj8_h03_dtc_can_decode_basic(&capture, slot, 0x51, false, 42));
    assert(!lfj8_h03_dtc_can_decode_basic(&capture, slot, 0x45, false, 42));
    assert(!lfj8_h03_dtc_can_decode_basic(&capture, slot, 0x43, false, 42));
    assert(!lfj8_h03_dtc_can_decode_basic(&capture, slot, 0x40, false, 42));
    slot[5] = 9;
    assert(!lfj8_h03_dtc_can_decode_basic(&capture, slot, 0x41, false, 42));
    slot[5] = 8;
    slot[1] = 0x21;  /* 0x721 is a different service. */
    assert(!lfj8_h03_dtc_can_decode_basic(&capture, slot, 0x41, false, 42));
}

static void test_segmented_read(void)
{
    CanShadow shadow = {.oem_state = 6, .now = 60000};
    const Lfj8RegisterIo io = {.context = &shadow, .read8 = read8, .read16 = read16,
                             .write8 = write8, .enter = enter, .leave = leave};
    Lfj8H03DtcCan adapter;
    CheryDtcState dtc;
    assert(!lfj8_h03_dtc_can_init(&adapter, 0x8000));
    assert(lfj8_h03_dtc_can_init(&adapter, 800));
    chery_dtc_init(&dtc);
    assert(chery_dtc_store_snapshot(&dtc, 0, 0x10));
    assert(chery_dtc_store_snapshot(&dtc, 1, 0x12));

    Lfj8H03DtcReceive event = rx(1, 59990, 3, 2, 0x10, 0x86);
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 0, 1, 0, &event) ==
           LFJ8_H03_DTC_NO_OWNERSHIP);
    assert(shadow.requests == 0);
    event.frame.remote = true;
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, 0, &event) == LFJ8_H03_DTC_SLOT_FREE);
    event.frame.remote = false;
    event.frame.extended = true;
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, 0, &event) == LFJ8_H03_DTC_SLOT_FREE);
    event.frame.extended = false;
    event.can_timestamp = 59000;
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, 0, &event) == LFJ8_H03_DTC_SLOT_FREE);
    assert(shadow.requests == 0);
    event.can_timestamp = 59990;
    /* Simulate a telemetry frame still awaiting arbitration. */
    shadow.control = 0x80;
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, 1, &event) == LFJ8_H03_DTC_SLOT_RESERVED);
    assert(shadow.requests == 0);
    complete(&shadow, 60050, 0x81);
    shadow.now = 60100;
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, 2, NULL) == LFJ8_H03_DTC_SLOT_RESERVED);
    expect_reply(&shadow, (const uint8_t[8]){2, 0x50, 0x86});
    assert(shadow.requests == 1 && adapter.link.phase == CHERY_DTC_LINK_AWAITING_TX);
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, 3, NULL) == LFJ8_H03_DTC_SLOT_RESERVED);
    complete(&shadow, 60110, 1);
    shadow.now = 60120;
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, 4, NULL) == LFJ8_H03_DTC_SLOT_FREE);

    shadow.now = 65400;
    event = rx(1, 65390, 4, 3, 0x17, 0xff);
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, 10, &event) == LFJ8_H03_DTC_SLOT_RESERVED);
    expect_reply(&shadow, (const uint8_t[8]){0x10, 0x08, 0x57, 2, 0xd1, 0x2b, 0x4f, 0xd1});
    event = rx(1, 65415, 3, 0x30, 0, 0);
    shadow.now = 65420;
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, 11, &event) == LFJ8_H03_DTC_SLOT_RESERVED);
    assert(shadow.requests == 2);
    complete(&shadow, 65530, 0x81);
    shadow.now = 15;
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, 12, &event) == LFJ8_H03_DTC_SLOT_FREE);
    assert(adapter.link.phase == CHERY_DTC_LINK_AWAITING_FLOW_CONTROL && shadow.requests == 2);
    event = rx(1, 7, 3, 0x30, 0, 0);
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, 13, &event) == LFJ8_H03_DTC_SLOT_RESERVED);
    expect_reply(&shadow, (const uint8_t[8]){0x21, 0x20, 0x4f});
    complete(&shadow, 40, 0x81);
    shadow.now = 45;
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, 14, NULL) == LFJ8_H03_DTC_SLOT_FREE);
    assert(adapter.link.phase == CHERY_DTC_LINK_IDLE && shadow.requests == 3);
}

static void test_timeout_abort_and_recovery(void)
{
    CanShadow shadow = {.oem_state = 7, .now = 1000};
    const Lfj8RegisterIo io = {.context = &shadow, .read8 = read8, .read16 = read16,
                             .write8 = write8, .enter = enter, .leave = leave};
    Lfj8H03DtcCan adapter;
    CheryDtcState dtc;
    assert(lfj8_h03_dtc_can_init(&adapter, 100));
    chery_dtc_init(&dtc);
    Lfj8H03DtcReceive event = rx(1, 995, 3, 2, 0x10, 0x86);
    const uint32_t start = UINT32_MAX - 50u;
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, start, &event) == LFJ8_H03_DTC_SLOT_RESERVED);
    shadow.control = 0x82;
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, start + 179u, NULL) == LFJ8_H03_DTC_SLOT_RESERVED);
    assert(shadow.aborts == 0);
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, start + 180u, NULL) == LFJ8_H03_DTC_SLOT_RESERVED);
    assert(shadow.aborts == 1 && shadow.control == 2);
    assert(adapter.link.session.permission_bits == 0x11);
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, start + 181u, &event) == LFJ8_H03_DTC_SLOT_RESERVED);
    assert(shadow.requests == 1);
    complete(&shadow, 1002, 1);
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, start + 182u, NULL) == LFJ8_H03_DTC_SLOT_FREE);

    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, start + 183u, &event) == LFJ8_H03_DTC_SLOT_RESERVED);
    shadow.stat = 0x4000;
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, start + 184u, &event) == LFJ8_H03_DTC_NO_OWNERSHIP);
    assert(shadow.aborts == 1 && shadow.requests == 2 && adapter.link.phase == CHERY_DTC_LINK_IDLE);
    shadow.stat = 0;
    shadow.control = 0;
    const unsigned writes = shadow.writes;
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, start + 185u, &event) ==
           LFJ8_H03_DTC_NO_OWNERSHIP);
    assert(shadow.writes == writes);
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 2, start + 185u, &event) == LFJ8_H03_DTC_SLOT_FREE);
    assert(shadow.requests == 2);
    event.generation = 2;
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 2, start + 186u, &event) == LFJ8_H03_DTC_SLOT_RESERVED);
    assert(shadow.requests == 3);
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 0, 2, start + 187u, NULL) == LFJ8_H03_DTC_NO_OWNERSHIP);
    /* A caller cannot abort a different writer's frame by reasserting
     * ownership while the cancelled generation is still active. */
    shadow.slot[0] = 0x06;
    shadow.slot[1] = 0x2e;
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 2, start + 188u, NULL) == LFJ8_H03_DTC_NO_OWNERSHIP);
    assert(shadow.requests == 3 && shadow.aborts == 1 && shadow.control == 0x80);
    shadow.control = 0;
    event.generation = 3;
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 3, start + 189u, &event) == LFJ8_H03_DTC_SLOT_RESERVED);
    assert(shadow.requests == 4);
}

static void test_foreign_completion_revokes_session(void)
{
    CanShadow shadow = {.oem_state = 6, .now = 1000};
    const Lfj8RegisterIo io = {.context = &shadow, .read8 = read8, .read16 = read16,
                             .write8 = write8, .enter = enter, .leave = leave};
    Lfj8H03DtcCan adapter;
    CheryDtcState dtc;
    assert(lfj8_h03_dtc_can_init(&adapter, 100));
    chery_dtc_init(&dtc);
    assert(chery_dtc_store_snapshot(&dtc, 0, 0x15));

    const Lfj8H03DtcReceive start = rx(1, 995, 3, 2, 0x10, 0x86);
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, 0, &start) == LFJ8_H03_DTC_SLOT_RESERVED);
    expect_reply(&shadow, (const uint8_t[8]){2, 0x50, 0x86});

    /* A different writer left an OEM 0x231 completion in the mailbox. */
    complete(&shadow, 1001, 0x81);
    shadow.slot[0] = 0x231u >> 6;
    shadow.slot[1] = 0x231u & 0x3fu;
    shadow.now = 1010;
    const unsigned writes = shadow.writes;
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, 1, NULL) == LFJ8_H03_DTC_NO_OWNERSHIP);
    assert(adapter.link.phase == CHERY_DTC_LINK_IDLE && adapter.link.session.permission_bits == 0x11);
    assert(shadow.writes == writes && shadow.control == 0x81);

    shadow.control = 0;
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, 2, &start) == LFJ8_H03_DTC_NO_OWNERSHIP);
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 2, 3, &start) == LFJ8_H03_DTC_SLOT_FREE);
    assert(shadow.writes == writes);

    const Lfj8H03DtcReceive clear = rx(2, 1009, 4, 3, 0x14, 0xff);
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 2, 4, &clear) == LFJ8_H03_DTC_SLOT_RESERVED);
    expect_reply(&shadow, (const uint8_t[8]){3, 0x7f, 0x14, 0x80});
    assert(!dtc.clear_pending && dtc.snapshot_index[0] == 0x15);
}

static void run_session_deadline(Lfj8H03DtcCan *adapter)
{
    for (unsigned event = 1; event < CHERY_DTC_LINK_SESSION_STEPS; ++event) {
        assert(!lfj8_h03_dtc_can_session_step(adapter));
    }
    assert(lfj8_h03_dtc_can_session_step(adapter));
}

static void test_session_expiry_drains_only_own_reply(void)
{
    CanShadow shadow = {.oem_state = 6, .now = 1000, .control = 0x80};
    const Lfj8RegisterIo io = {.context = &shadow, .read8 = read8, .read16 = read16,
                             .write8 = write8, .enter = enter, .leave = leave};
    Lfj8H03DtcCan adapter;
    CheryDtcState dtc;
    assert(lfj8_h03_dtc_can_init(&adapter, 100));
    chery_dtc_init(&dtc);
    assert(chery_dtc_store_snapshot(&dtc, 0, 4));
    const Lfj8H03DtcReceive start = rx(1, 995, 3, 2, 0x10, 0x86);

    /* A pending telemetry TX leaves the diagnostic reply queued. */
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, 0, &start) == LFJ8_H03_DTC_SLOT_RESERVED);
    run_session_deadline(&adapter);
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, 1, NULL) == LFJ8_H03_DTC_SLOT_FREE);
    assert(shadow.writes == 0 && shadow.control == 0x80);
    complete(&shadow, 1001, 0x81);
    shadow.now = 1002;

    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, 2, &start) == LFJ8_H03_DTC_SLOT_RESERVED);
    assert(shadow.requests == 1);
    shadow.control = 0x82;
    const unsigned writes = shadow.writes;
    run_session_deadline(&adapter);
    assert(shadow.writes == writes && shadow.aborts == 0 && adapter.link.session.mode_bits == 0x9f);
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, 3, NULL) == LFJ8_H03_DTC_SLOT_RESERVED);
    assert(shadow.aborts == 1 && shadow.control == 2 && shadow.requests == 1);
    complete(&shadow, 1003, 1);
    shadow.now = 1004;
    const Lfj8H03DtcReceive clear = rx(1, 1004, 4, 3, 0x14, 0xff);
    assert(lfj8_h03_dtc_can_poll(&adapter, &dtc, &io, 1, 1, 4, &clear) == LFJ8_H03_DTC_SLOT_RESERVED);
    expect_reply(&shadow, (const uint8_t[8]){3, 0x7f, 0x14, 0x80});
    assert(dtc.snapshot_index[0] == 4);
}

int main(void)
{
    test_basiccan_decode();
    test_segmented_read();
    test_foreign_completion_revokes_session();
    test_timeout_abort_and_recovery();
    test_session_expiry_drains_only_own_reply();
    puts("H03 CAN0 diagnostic TX13 completion, stale Flow Control, abort and recovery: PASS");
    return 0;
}
