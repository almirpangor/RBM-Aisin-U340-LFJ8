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
    Lfj8H03CanOwner owner;
    uint32_t now_us;
    uint16_t timestamp;
    uint16_t status;
    uint8_t slots[2];
    uint8_t data[2 * SLOT_SIZE];
    unsigned lock_depth;
    unsigned clock_reads;
    bool tml0_ready;
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
    if (address == CAN_COUNTS) {
        ++fixture->clock_reads;
        return fixture->timestamp;
    }
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

static void next_release(Fixture *fixture, uint8_t channels, const uint8_t *rpm_payload)
{
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
            if (index == 0 && rpm_payload) {
                memcpy(slot + 6u, rpm_payload, 8u);
            }
            slot[14] = (uint8_t)(fixture->timestamp >> 8);
            slot[15] = (uint8_t)fixture->timestamp;
        }
    }
}

static unsigned task2(Fixture *fixture, uint8_t channels, bool inhibit_history)
{
    const Lfj8RegisterIo io = registers(fixture);
    next_release(fixture, channels, NULL);
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

static Lfj8H03EngineModelSample model_release(Fixture *fixture, const uint8_t *rpm_payload,
    const Ta2005EngineQualificationContext *signal)
{
    const Lfj8RegisterIo io = registers(fixture);
    Lfj8H03EngineModelSample sample = {
        .snapshot = {.speed_fad8 = 1000u, .coolant_f9e9 = 50u, .usable = 3u, .model = {1u, 2u, 3u}},
        .state = LFJ8_H03_MODEL_EVALUATE,
    };
    next_release(fixture, rpm_payload ? 1u : 0u, rpm_payload);
    const unsigned events = lfj8_h03_engine_feed_task2_with_model(
        &fixture->receiver, &fixture->qualifier, &fixture->dtc, &io, fixture->now_us, 1u,
        signal, false, &fixture->feed, &sample);
    assert((events & TA2005_ENGINE_EVALUATED) == (signal->coherent ? TA2005_ENGINE_EVALUATED : 0u));
    return sample;
}

static void expect_model(Lfj8H03EngineModelSample sample, uint8_t state,
                         uint8_t f9d8, uint8_t f9e8, uint8_t f914)
{
    const Ta2005CherySnapshot *raw = &sample.snapshot;
    assert(sample.state == state && raw->model.f9d8 == f9d8 &&
           raw->model.f9e8 == f9e8 && raw->model.f914 == f914);
    if (state != LFJ8_H03_MODEL_EVALUATE) {
        assert(raw->usable == 0u && raw->speed_fad8 == UINT16_MAX && raw->coolant_f9e9 == UINT8_MAX);
    }
}

static void check_generation_change(void)
{
    Fixture fixture;
    setup(&fixture);
    memset(fixture.slots, 0, sizeof(fixture.slots));
    volatile uint32_t generation = UINT32_MAX;
    lfj8_h03_engine_rx_bind_generation(&fixture.receiver, &generation);
    assert(task2(&fixture, 0u, false) == TA2005_ENGINE_EVALUATED);
    assert(task2(&fixture, 3u, false) == TA2005_ENGINE_EVALUATED);

    const uint8_t old_model[8] = {0x12, 0xc0, 0x21, 0x32, 0, 0x43, 0, 0};
    expect_model(model_release(&fixture, old_model, &context),
                 LFJ8_H03_MODEL_EVALUATE, 0x21, 0x32, 0x43);
    assert(fixture.feed.fa62 == 9600u && fixture.feed.f9b8 == 137u);
    fixture.dtc.history[2] = RPM_BIT;

    /* Setup completed between polls. The clock and slot flag still look
     * valid, with a frame left over from the previous CAN generation. */
    generation = 0u;
    expect_model(model_release(&fixture, old_model, &context),
                 LFJ8_H03_MODEL_INHIBITED, 0xff, 0xff, 0xff);
    assert(fixture.slots[0] == 0x41u && fixture.receiver.phase == LFJ8_H03_RX_WAIT_FOR_OEM);
    assert(fixture.feed.fa62 == 0u && fixture.feed.f9b8 == 87u);
    assert(!fixture.dtc.current[2] && fixture.dtc.history[2] == RPM_BIT);

    memset(fixture.slots, 0, sizeof(fixture.slots));
    expect_model(model_release(&fixture, NULL, &context),
                 LFJ8_H03_MODEL_INHIBITED, 0xff, 0xff, 0xff);
    assert(task2(&fixture, 3u, false) == TA2005_ENGINE_EVALUATED);
    const uint8_t new_model[8] = {0x12, 0xc0, 0x12, 0x23, 0, 0x34, 0, 0};
    expect_model(model_release(&fixture, new_model, &context),
                 LFJ8_H03_MODEL_EVALUATE, 0x12, 0x23, 0x34);
    assert(fixture.feed.fa62 == 9600u && fixture.feed.f9b8 == 137u);
    assert(fixture.receiver.last_generation == 0u && fixture.dtc.history[2] == RPM_BIT);
}

static void check_shared_model_snapshot(void)
{
    Fixture fixture;
    setup(&fixture);
    /* The next capture crosses both clock wraps. RPM is unavailable and
     * the middle field is absent, independently of the two other bytes. */
    const uint8_t model_only[8] = {0xff, 0xff, 0x56, 0xff, 0x99, 0x71, 0, 0};
    const unsigned before = fixture.clock_reads;
    const Lfj8H03EngineModelSample sample = model_release(&fixture, model_only, &context);
    expect_model(sample, LFJ8_H03_MODEL_EVALUATE, 0x56, 0xff, 0x71);
    assert(sample.snapshot.usable == TA2005_CHERY_COOLANT && sample.snapshot.speed_fad8 == UINT16_MAX);
    assert(fixture.now_us == 0u && fixture.timestamp == 0u);
    assert(fixture.clock_reads - before == 2u);
    assert(fixture.qualifier.rpm_count == 1u);
    assert(fixture.feed.coherent && fixture.feed.fa62 == 9600u && fixture.feed.f9b8 == 137u);
    for (unsigned age = 1; age < FRAME_MAX_AGE; ++age) {
        expect_model(model_release(&fixture, NULL, &context), LFJ8_H03_MODEL_EVALUATE, 0x56, 0xff, 0x71);
    }
    expect_model(model_release(&fixture, NULL, &context), LFJ8_H03_MODEL_EVALUATE, 0xff, 0xff, 0xff);

    const uint8_t complete[8] = {0x12, 0xc0, 0x21, 0x32, 0x99, 0x43, 0, 0};
    Ta2005EngineQualificationContext signal = context;
    signal.e02b = 4u;
    expect_model(model_release(&fixture, complete, &signal), LFJ8_H03_MODEL_INHIBITED, 0xff, 0xff, 0xff);
    assert(fixture.feed.fa62 == 0u);
    fixture.dtc.current[3] = 0x80u;
    expect_model(model_release(&fixture, complete, &context), LFJ8_H03_MODEL_INHIBITED, 0xff, 0xff, 0xff);
    fixture.dtc.current[3] = 0u;
    expect_model(model_release(&fixture, complete, &context), LFJ8_H03_MODEL_EVALUATE, 0x21, 0x32, 0x43);
    assert(fixture.feed.fa62 == 9600u && fixture.qualifier.rpm_count == 0u);

    fixture.status = 0x4000u;
    expect_model(model_release(&fixture, NULL, &context), LFJ8_H03_MODEL_INHIBITED, 0xff, 0xff, 0xff);
    fixture.status = 0u;
    memset(fixture.slots, 0, sizeof(fixture.slots));
    expect_model(model_release(&fixture, NULL, &context), LFJ8_H03_MODEL_INHIBITED, 0xff, 0xff, 0xff);
    expect_model(model_release(&fixture, complete, &context), LFJ8_H03_MODEL_EVALUATE, 0x21, 0x32, 0x43);
    assert(fixture.feed.coherent && fixture.feed.fa62 == 9600u && !fixture.dtc.current[2]);

    signal.coherent = 0u;
    const unsigned at_refusal = fixture.clock_reads;
    expect_model(model_release(&fixture, NULL, &signal), LFJ8_H03_MODEL_NOT_EVALUATED, 0xff, 0xff, 0xff);
    assert(!fixture.feed.coherent && fixture.clock_reads == at_refusal);
}

static Fixture *clock_fixture;

static int target_clock(uint32_t *now_us)
{
    assert(clock_fixture->lock_depth != 0u);
    if (!clock_fixture->tml0_ready) {
        return 0;
    }
    *now_us = clock_fixture->now_us;
    return 1;
}

static void check_target_owner_and_tml0(void)
{
    Fixture fixture = {
        .owner = {.initialized = true, .setup_generation = UINT32_MAX},
        .now_us = UINT32_MAX - 1u, .timestamp = UINT16_MAX - 1u,
    };
    clock_fixture = &fixture;
    const Lfj8RegisterIo io = registers(&fixture);
    const Lfj8H03EngineFeedTarget target = {
        .rx = &fixture.receiver, .qualifier = &fixture.qualifier, .dtc = &fixture.dtc,
        .io = &io, .can_owner = &fixture.owner, .now_us = target_clock, .bit_time_us = 2u,
    };
    chery_dtc_init(&fixture.dtc);
    fixture.dtc.history[2] = RPM_BIT;
    Lfj8H03EngineFeedTarget unqualified = target;
    unqualified.bit_time_us = 0u;
    assert(!lfj8_h03_engine_feed_target_init(&unqualified, FRAME_MAX_AGE, 30));
    assert(!lfj8_h03_engine_feed_target_init(&target, 0, 30));
    assert(lfj8_h03_engine_feed_target_init(&target, FRAME_MAX_AGE, 30));
    assert(fixture.receiver.generation_source == &fixture.owner.setup_generation);
    assert(fixture.dtc.history[2] == RPM_BIT);

    /* The pending generation has not been admitted by the CAN owner. */
    fixture.owner.grant = 1u;
    fixture.tml0_ready = true;
    lfj8_h03_engine_feed_target_poll(&target);
    assert(!fixture.clock_reads && !fixture.slots[0] && !fixture.slots[1]);

    fixture.owner.admitted_generation = UINT32_MAX;
    fixture.tml0_ready = false;
    lfj8_h03_engine_feed_target_poll(&target);
    assert(!fixture.clock_reads && !fixture.slots[0] && !fixture.slots[1]);
    fixture.tml0_ready = true;
    Lfj8H03EngineModelSample model;
    uint32_t oldest_us = fixture.now_us;
    assert(lfj8_h03_engine_feed_target_task2(&target, &context, false,
                &fixture.feed, &model, &oldest_us) == TA2005_ENGINE_EVALUATED);
    expect_model(model, LFJ8_H03_MODEL_INHIBITED, 0xff, 0xff, 0xff);
    assert(fixture.slots[0] == 0x40u && fixture.slots[1] == 0x40u);

    const uint8_t payload[] = {0x12, 0xc0, 0x21, 0x32, 0, 0x43, 0, 0};
    next_release(&fixture, 3u, payload);
    /* The RX-only call advances the clock without consuming a debounce step. */
    lfj8_h03_engine_feed_target_poll(&target);
    next_release(&fixture, 0u, NULL);
    assert(lfj8_h03_engine_feed_target_task2(&target, &context, false,
                &fixture.feed, &model, &oldest_us) == TA2005_ENGINE_EVALUATED);
    expect_model(model, LFJ8_H03_MODEL_EVALUATE, 0x21, 0x32, 0x43);
    assert(fixture.now_us == 0u && fixture.timestamp == 0u);
    assert(fixture.feed.fa62 == 9600u && fixture.feed.f9b8 == 137u);
    assert(oldest_us == UINT32_MAX - 3u);

    /* Age the RPM past the receive limit while the donor is still holding it.
     * Fresh ECT and a newer fallback must not refresh the held operand. */
    for (unsigned age = 2; age <= FRAME_MAX_AGE; ++age) {
        next_release(&fixture, 2u, NULL);
        oldest_us = fixture.now_us;
        assert(lfj8_h03_engine_feed_target_task2(&target, &context, false,
                   &fixture.feed, &model, &oldest_us) == TA2005_ENGINE_EVALUATED);
    }
    assert(fixture.feed.fa62 == 9600u && oldest_us == UINT32_MAX - FRAME_MAX_AGE - 1u);

    next_release(&fixture, 3u, payload);
    fixture.owner.grant = 0u;
    fixture.owner.setup_generation = 0u;
    const unsigned before_reset = fixture.clock_reads;
    oldest_us = fixture.now_us - 5u;
    assert(lfj8_h03_engine_feed_target_task2(&target, &context, false,
                &fixture.feed, &model, &oldest_us) == TA2005_ENGINE_EVALUATED);
    expect_model(model, LFJ8_H03_MODEL_INHIBITED, 0xff, 0xff, 0xff);
    assert(fixture.feed.fa62 == 0u && fixture.feed.f9b8 == 87u);
    assert(!fixture.receiver.rpm_stamp_valid && oldest_us == fixture.now_us - 5u);
    assert(fixture.receiver.last_generation == 0u && fixture.clock_reads == before_reset);
    assert(fixture.slots[0] == 0x41u && fixture.slots[1] == 0x41u);

    memset(fixture.slots, 0, sizeof(fixture.slots));
    fixture.owner.admitted_generation = 0u;
    fixture.owner.grant = 1u;
    assert(lfj8_h03_engine_feed_target_task2(&target, &context, false,
                &fixture.feed, &model, &oldest_us) == TA2005_ENGINE_EVALUATED);
    expect_model(model, LFJ8_H03_MODEL_INHIBITED, 0xff, 0xff, 0xff);
    next_release(&fixture, 3u, payload);
    assert(lfj8_h03_engine_feed_target_task2(&target, &context, false,
                &fixture.feed, &model, &oldest_us) == TA2005_ENGINE_EVALUATED);
    expect_model(model, LFJ8_H03_MODEL_EVALUATE, 0x21, 0x32, 0x43);
    assert(fixture.feed.fa62 == 9600u && fixture.feed.f9b8 == 137u);

    next_release(&fixture, 3u, payload);
    const uint16_t coolant_stamp = (uint16_t)(fixture.timestamp - 1u);
    fixture.data[SLOT_SIZE + 14u] = (uint8_t)(coolant_stamp >> 8);
    fixture.data[SLOT_SIZE + 15u] = (uint8_t)coolant_stamp;
    oldest_us = fixture.now_us;
    assert(lfj8_h03_engine_feed_target_task2(&target, &context, false,
               &fixture.feed, &model, &oldest_us) == TA2005_ENGINE_EVALUATED);
    assert(fixture.feed.fa62 == 9600u && fixture.feed.f9b8 == 137u &&
           oldest_us == fixture.now_us - 4u);

    /* Losing time also revokes RX when no coherent Task 2 context is ready. */
    fixture.tml0_ready = false;
    const unsigned before_clock_loss = fixture.clock_reads;
    assert(!lfj8_h03_engine_feed_target_task2(&target, NULL, false, &fixture.feed, &model, &oldest_us));
    expect_model(model, LFJ8_H03_MODEL_NOT_EVALUATED, 0xff, 0xff, 0xff);
    assert(!fixture.feed.coherent && fixture.receiver.discontinuity);
    assert(fixture.receiver.phase == LFJ8_H03_RX_WAIT_FOR_OEM);
    assert(fixture.clock_reads == before_clock_loss && fixture.lock_depth == 0u);
    assert(fixture.dtc.history[2] == RPM_BIT && fixture.dtc.current[2] == 0u);
}

int main(void)
{
    check_timeout_and_history();
    check_clear_and_reinit();
    check_outage_between_releases();
    check_shared_model_snapshot();
    check_generation_change();
    check_target_owner_and_tml0();
    puts("H03 qualified engine feed and Chery clear/fault/recovery passed");
    puts("H03 shared model snapshot: common RX poll, wrap, expiry, inhibit and recovery passed");
    puts("H03 engine RX: generation rollover, stale slot rejection and reattachment passed");
    puts("H03 engine target: CAN owner admission, shared clock, inter-release poll and revocation passed");
    return 0;
}
