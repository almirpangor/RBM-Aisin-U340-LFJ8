#include "lfj8_h03_engine_feed.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>

enum {
    CAN_COUNTS = 0x801008,
    CAN_STATUS = 0x801002,
    CAN_MODE = 0x801018,
    CAN_SLOTS = 0x80105b,
    CAN_BYTES = 0x8011b0,
    CAN_STOCK_STATE = 0x806ae6,
    SLOT_SIZE = 16,
    FRAME_MAX_AGE = 4,
    RPM_BIT = 0x20,
    COOLANT_BIT = 0x10,
};

typedef struct {
    Lfj8H03EngineRx receiver;
    Ta2005EngineQualifier qualifier;
    CheryDtcState dtc;
    RbmU340eQualifiedEngineFeed feed;
    uint32_t now_us;
    uint16_t timestamp;
    uint16_t status;
    uint8_t slots[2];
    uint8_t data[2 * SLOT_SIZE];
    unsigned lock_depth;
} Fixture;

static const Ta2005EngineQualificationContext context = {
    .coolant_can_enabled = 1, .coherent = 1, .fallback_fa7b = 87,
};

static uint32_t enter(void *context)
{
    Fixture *fixture = context;
    return fixture->lock_depth++;
}

static void leave(void *context, uint32_t previous)
{
    Fixture *fixture = context;
    assert(fixture->lock_depth != 0 && --fixture->lock_depth == previous);
}

static uint8_t read8(void *context, uint32_t address)
{
    Fixture *fixture = context;
    assert(fixture->lock_depth > 0);
    if (address == CAN_MODE) return 0;
    if (address == CAN_STOCK_STATE) return 6;
    if (address == 0x801028u) return 0x1f;
    if (address == 0x801029u) return 0x3f;
    if (address >= CAN_SLOTS && address < CAN_SLOTS + 2) return fixture->slots[address - CAN_SLOTS];
    assert(address >= CAN_BYTES && address < CAN_BYTES + sizeof(fixture->data));
    return fixture->data[address - CAN_BYTES];
}

static uint16_t read16(void *context, uint32_t address)
{
    Fixture *fixture = context;
    assert(fixture->lock_depth > 0);
    if (address == CAN_COUNTS) return fixture->timestamp;
    if (address == CAN_STATUS) return fixture->status;
    if (address == 0x801000u || address == 0x801004u || address == 0x801010u) return 0;
    assert(address == CAN_BYTES + 14 || address == CAN_BYTES + 30);
    return (uint16_t)((uint16_t)fixture->data[address - CAN_BYTES] << 8 |
        fixture->data[address - CAN_BYTES + 1u]);
}

static void write8(void *context, uint32_t address, uint8_t value)
{
    Fixture *fixture = context;
    assert(fixture->lock_depth > 0);
    if (address >= CAN_SLOTS && address < CAN_SLOTS + 2) {
        fixture->slots[address - CAN_SLOTS] = value == 0x4eu ? 0x40u : value;
    } else {
        assert(address >= CAN_BYTES && address < CAN_BYTES + sizeof(fixture->data));
        fixture->data[address - CAN_BYTES] = value;
    }
}

static Lfj8RegisterIo registers(Fixture *fixture)
{
    return (Lfj8RegisterIo){
        .context = fixture, .read8 = read8, .read16 = read16, .write8 = write8,
        .enter = enter, .leave = leave,
    };
}

static unsigned task2(Fixture *fixture, uint8_t channels, bool inhibit_history)
{
    const Lfj8RegisterIo io = registers(fixture);
    ++fixture->now_us;
    ++fixture->timestamp;
    for (unsigned index = 0; index < 2; ++index) {
        if (channels & (1u << index)) {
            assert(fixture->slots[index] == 0x40u);
            fixture->slots[index] = 0x41u;
            uint8_t *slot = &fixture->data[index * SLOT_SIZE];
            slot[5] = 8u;
            slot[6] = index == 0 ? 0x12u : 180u;
            slot[7] = 0xc0u;
            slot[14] = (uint8_t)(fixture->timestamp >> 8);
            slot[15] = (uint8_t)fixture->timestamp;
        }
    }
    return lfj8_h03_engine_feed_task2(&fixture->receiver, &fixture->qualifier, &fixture->dtc,
        &io, fixture->now_us, 1u, &context, inhibit_history, &fixture->feed);
}

static void setup(Fixture *fixture)
{
    memset(fixture, 0, sizeof(*fixture));
    fixture->now_us = UINT32_MAX - 2;
    fixture->timestamp = UINT16_MAX - 2;
    chery_dtc_init(&fixture->dtc);
    ta2005_engine_qualifier_init(&fixture->qualifier);
    assert(lfj8_h03_engine_rx_init(&fixture->receiver, FRAME_MAX_AGE, 30));
    assert(task2(fixture, 0u, false) == TA2005_ENGINE_EVALUATED);
    assert(fixture->feed.fa62 == 0 && fixture->feed.f9b8 == 87);
    assert(task2(fixture, 3u, false) == TA2005_ENGINE_EVALUATED);
    assert(fixture->feed.fa62 == 9600 && fixture->feed.f9b8 == 137);
}

static void expect_read(Fixture *fixture, uint8_t status)
{
    const uint8_t request[] = {0x17, 0xff, 0};
    const uint8_t want[] = {0x57, 2, 0xd1, 0, status, 0xd1, 0x1f, status};
    const CheryDtcSession session = {0x90, 0x08};
    uint8_t reply[CHERY_DTC_MAX_REPLY_BYTES];
    size_t size;
    assert(chery_dtc_respond(&fixture->dtc, session, request, sizeof(request),
        reply, sizeof(reply), &size) == CHERY_DTC_REPLIED);
    assert(size == sizeof(want) && memcmp(reply, want, size) == 0);
}

static void check_timeout_and_history(void)
{
    Fixture fixture;
    setup(&fixture);
    fixture.dtc.current[2] = 4;
    for (unsigned tick = 1; tick < FRAME_MAX_AGE; ++tick) {
        assert(task2(&fixture, 0u, false) == TA2005_ENGINE_EVALUATED);
        assert(fixture.qualifier.rpm_count == 0 && fixture.qualifier.coolant_count == 0);
    }
    for (unsigned bad = 1; bad <= 202; ++bad) {
        unsigned want = TA2005_ENGINE_EVALUATED |
            (bad == 102 ? TA2005_ENGINE_NEW_RPM_DTC : 0u) |
            (bad == 202 ? TA2005_ENGINE_NEW_COOLANT_DTC : 0u);
        assert(task2(&fixture, 0u, false) == want);
        assert(fixture.feed.fa62 == (bad < 102 ? 9600 : 0));
        if (bad == 102) {
            assert(fixture.dtc.current[2] == (RPM_BIT | 4));
        }
    }
    assert(fixture.dtc.history[2] == (RPM_BIT | COOLANT_BIT) && fixture.feed.f9b8 == 87);
    expect_read(&fixture, 0x6f);
    for (unsigned good = 1; good <= 252; ++good) {
        assert(task2(&fixture, 3u, false) == TA2005_ENGINE_EVALUATED);
        assert(fixture.feed.fa62 == (good < 252 ? 0 : 9600));
    }
    assert(fixture.dtc.current[2] == 4 && fixture.feed.f9b8 == 137);
    expect_read(&fixture, 0x4f);
}

static void check_clear_and_reinit(void)
{
    Fixture fixture;
    setup(&fixture);
    for (unsigned step = 0; step < 90; ++step) {
        assert(task2(&fixture, 0u, false) == TA2005_ENGINE_EVALUATED);
    }
    assert(fixture.qualifier.rpm_count == 87 && fixture.qualifier.coolant_count == 87);
    const uint8_t clear[] = {0x14, 0xff, 0};
    const CheryDtcSession authorized = {0x90, 0x08}, denied = {0x90, 0};
    uint8_t reply[3];
    size_t length;
    assert(chery_dtc_respond(&fixture.dtc, authorized, clear, sizeof(clear), reply, 2u, &length)
           == CHERY_DTC_SHORT_BUFFER && !fixture.dtc.clear_pending);
    assert(chery_dtc_respond(&fixture.dtc, denied, clear, sizeof(clear), reply, sizeof(reply), &length)
           == CHERY_DTC_REPLIED && reply[0] == 0x7f && !fixture.dtc.clear_pending);
    assert(chery_dtc_respond(&fixture.dtc, authorized, clear, sizeof(clear), reply, sizeof(reply), &length)
           == CHERY_DTC_REPLIED && reply[0] == 0x54 && fixture.dtc.clear_pending);

    assert(!lfj8_h03_engine_feed_task2(NULL, &fixture.qualifier, &fixture.dtc, NULL,
        0u, 0u, NULL, false, &fixture.feed));
    assert(!fixture.dtc.clear_pending && fixture.qualifier.rpm_count == 0 &&
           fixture.qualifier.coolant_count == 0 && !fixture.feed.coherent);
    assert(task2(&fixture, 0u, false) == TA2005_ENGINE_EVALUATED);
    assert(!lfj8_h03_engine_feed_task2(NULL, &fixture.qualifier, &fixture.dtc, NULL,
        0u, 0u, NULL, false, &fixture.feed));
    assert(fixture.qualifier.rpm_count == 1 && fixture.qualifier.coolant_count == 1);

    fixture.dtc.current[3] = 4;
    assert(task2(&fixture, 3u, true) == TA2005_ENGINE_EVALUATED);
    assert(fixture.qualifier.rpm_count == 1 && fixture.feed.fa62 == 0 && fixture.feed.f9b8 == 87);
    fixture.dtc.current[3] = 0;
    assert(task2(&fixture, 3u, true) == TA2005_ENGINE_EVALUATED && fixture.feed.fa62 == 9600);
    memset(fixture.slots, 0, sizeof(fixture.slots));
    assert(lfj8_h03_engine_rx_init(&fixture.receiver, FRAME_MAX_AGE, 30));
    assert(task2(&fixture, 0u, true) == TA2005_ENGINE_EVALUATED);
    assert(fixture.feed.fa62 == 0 && fixture.feed.f9b8 == 87 && fixture.dtc.current[2] == 0);
    assert(task2(&fixture, 3u, true) == TA2005_ENGINE_EVALUATED && fixture.feed.fa62 == 9600);

    fixture.qualifier.rpm_count = 101;
    fixture.qualifier.coolant_count = 201;
    for (unsigned age = 1; age < FRAME_MAX_AGE; ++age) {
        /* Preserve the seeded count until a continuously timed invalid
         * interval can exercise the inhibited-history path. */
        fixture.dtc.current[3] = 4;
        assert(task2(&fixture, 0u, true) == TA2005_ENGINE_EVALUATED);
    }
    fixture.dtc.current[3] = 0;
    assert(task2(&fixture, 0u, true) ==
           (TA2005_ENGINE_EVALUATED | TA2005_ENGINE_NEW_RPM_DTC | TA2005_ENGINE_NEW_COOLANT_DTC));
    assert(fixture.dtc.current[2] == (RPM_BIT | COOLANT_BIT) && fixture.dtc.history[2] == 0);
}

static void check_outage_between_releases(void)
{
    Fixture fixture;
    setup(&fixture);
    const Lfj8RegisterIo io = registers(&fixture);
    Ta2005CherySnapshot raw;

    assert(!fixture.receiver.discontinuity && fixture.receiver.clock_running);
    fixture.status = 0x4000u;
    assert(!lfj8_h03_engine_rx_poll(&fixture.receiver, &io, ++fixture.now_us, 1u, &raw));
    assert(fixture.receiver.discontinuity && !fixture.receiver.clock_running);

    fixture.status = 0u;
    memset(fixture.slots, 0, sizeof(fixture.slots));
    assert(!lfj8_h03_engine_rx_poll(&fixture.receiver, &io, ++fixture.now_us, 1u, &raw));
    ++fixture.timestamp;
    assert(!lfj8_h03_engine_rx_poll(&fixture.receiver, &io, ++fixture.now_us, 1u, &raw));
    assert(fixture.receiver.discontinuity && fixture.receiver.clock_running);
    assert(fixture.qualifier.fa62 == 9600);

    assert(task2(&fixture, 0u, false) == TA2005_ENGINE_EVALUATED);
    assert(fixture.feed.fa62 == 0 && fixture.feed.f9b8 == 87 &&
           fixture.qualifier.rpm_count == 0 && fixture.dtc.current[2] == 0);
    assert(task2(&fixture, 3u, false) == TA2005_ENGINE_EVALUATED);
    assert(fixture.feed.fa62 == 9600 && fixture.feed.f9b8 == 137);
}

int main(void)
{
    check_timeout_and_history();
    check_clear_and_reinit();
    check_outage_between_releases();
    puts("H03 qualified engine feed and Chery clear/fault/recovery passed");
    return 0;
}
