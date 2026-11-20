#include "lfj8_h03_dtc_foreground.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>

enum {
    CNT = 0x801000, STAT = 0x801002, EXTID = 0x801004, TSTMP = 0x801008,
    SLIMK = 0x801010, MODE = 0x801018, GMSKS0 = 0x801028, GMSKS1 = 0x801029,
    MSC13 = 0x80105d, SLOT13 = 0x8011d0, MSC14 = 0x80105e, SLOT14 = 0x8011e0,
    OEM_STATE = 0x806ae6, TML0 = 0x8003e0, BASIC_RUNNING = 0x0800, BUS_OFF = 0x4000,
    DTC_AGE_BITS = 100,
};

static const uint8_t session[] = {2, 0x10, 0x86};
static const uint8_t read_dtc[] = {3, 0x17, 0xff, 0};
static const uint8_t flow_control[] = {0x30, 0, 0};

typedef struct {
    Lfj8H03Can13 broker;
    Lfj8H03DtcRxQueue queue;
    CheryDtcState dtc;
    Lfj8RegisterIo io;
    uint32_t generation;
    uint32_t now_us;
    uint16_t status;
    uint8_t tx[16];
    uint8_t rx[16];
    uint8_t tx_control;
    uint8_t rx_control;
    uint8_t rx_slot;
    bool grant;
    bool locked;
    bool replace_after_peek;
    unsigned sent;
} Fixture;

static uint16_t can_tick(uint32_t now_us)
{
    return (uint16_t)(0xff00u + now_us / 2u);
}

static void stamp(uint8_t slot[16], uint32_t now_us)
{
    const uint16_t time = can_tick(now_us);
    slot[14] = (uint8_t)(time >> 8);
    slot[15] = (uint8_t)time;
}

static uint8_t read8(void *context, uint32_t address)
{
    Fixture *f = context;
    assert(f->locked);
    const uint32_t rx_start = SLOT14 + 16u * f->rx_slot;
    if (address == MSC14 + (uint32_t)f->rx_slot) {
        return f->rx_control;
    }
    if (address >= rx_start && address < rx_start + 16u) {
        return f->rx[address - rx_start];
    }
    switch (address) {
    case OEM_STATE: return 6;
    case MODE: return 0;
    case GMSKS0: return 0x1f;
    case GMSKS1: return 0x3f;
    case MSC13: return f->tx_control;
    default:
        assert(address >= SLOT13 && address < SLOT13 + 16u);
        return f->tx[address - SLOT13];
    }
}

static uint16_t read16(void *context, uint32_t address)
{
    Fixture *f = context;
    assert(f->locked);
    switch (address) {
    case CNT: return 0x0008;
    case STAT: return f->status;
    case EXTID: return 0;
    case TSTMP: return can_tick(f->now_us);
    case SLIMK: return 0x8003;
    default:
        assert(address == SLOT13 + 14u);
        return (uint16_t)((uint16_t)f->tx[14] << 8 | f->tx[15]);
    }
}

static uint32_t read32(void *context, uint32_t address)
{
    Fixture *f = context;
    assert(f->locked && address == TML0);
    return f->now_us;
}

static void write8(void *context, uint32_t address, uint8_t value)
{
    Fixture *f = context;
    assert(f->locked && f->grant && f->status == BASIC_RUNNING);
    if (address == MSC13) {
        assert(value == 0x00 || value == 0x0f || value == 0x40 || value == 0x80);
        f->tx_control = value == 0x0f ? f->tx_control & 2u : value;
        f->sent += value == 0x80;
    } else {
        assert(address >= SLOT13 && address < SLOT13 + 14u && f->tx_control == 0);
        f->tx[address - SLOT13] = value;
    }
}

static uint32_t enter(void *context)
{
    Fixture *f = context;
    assert(!f->locked);
    f->locked = true;
    return 17;
}

static Lfj8H03DtcRxPublish capture(Fixture *f, uint8_t slot, uint32_t generation,
                                   uint32_t now_us, const uint8_t *frame, uint8_t length)
{
    f->now_us = now_us;
    f->rx_slot = (uint8_t)(slot - 14u);
    memset(f->rx, 0, sizeof(f->rx));
    f->rx[0] = 0x1c;
    f->rx[1] = 0x32;
    f->rx[5] = length;
    memcpy(&f->rx[6], frame, length);
    stamp(f->rx, now_us);
    f->rx_control = 0x41;
    const Lfj8H03DtcRxPublish result = lfj8_h03_dtc_rx_queue_capture_basic(
        &f->queue, &f->io, slot, generation, now_us, can_tick(now_us));
    assert(f->rx_control == 0x41 && !f->locked);
    f->rx_control = 0x40; /* OEM acknowledges after the observer returns. */
    return result;
}

static void leave(void *context, uint32_t saved)
{
    Fixture *f = context;
    assert(f->locked && saved == 17u);
    f->locked = false;
    if (f->replace_after_peek) {
        f->replace_after_peek = false;
        /* The pending RX IRQ preempts foreground after the queue's peek. */
        assert(capture(f, 15, f->generation, 300, session, sizeof(session)) == LFJ8_H03_DTC_RX_QUEUED);
    }
}

static void init(Fixture *f, uint32_t generation)
{
    *f = (Fixture){.generation = generation, .status = BASIC_RUNNING, .grant = true};
    f->io = (Lfj8RegisterIo){f, read8, read16, read32, write8, enter, leave};
    const Lfj8H03Can13Config config = {
        .torque_receive_age_bits = 4000, .diagnostic_receive_age_bits = DTC_AGE_BITS,
        .max_poll_gap_us = 5000, .bit_time_us = 2,
    };
    assert(lfj8_h03_can13_init(&f->broker, &config, 0));
    assert(lfj8_h03_dtc_rx_queue_init(&f->queue, generation, DTC_AGE_BITS, 2));
    chery_dtc_init(&f->dtc);
}

static Lfj8H03Can13Result poll(Fixture *f, uint32_t now_us, bool clock_valid)
{
    f->now_us = now_us;
    const uint16_t now_bits = can_tick(now_us);
    const Lfj8H03DtcReceive caller_frame = {
        .frame = {.id = CHERY_DTC_CAN_REQUEST_ID, .length = 3, .data = {2, 0x10, 0x86}},
        .generation = f->generation, .can_timestamp = now_bits,
    };
    Lfj8H03Can13Input input = {
        .generation = f->generation, .now_us = now_us, .diagnostic_tick = now_us / 100u,
        .owns_slot13 = f->grant, .dtc = &f->dtc, .received = &caller_frame,
    };
    const Lfj8H03Can13Result result = lfj8_h03_dtc_foreground_poll(
        &f->broker, &f->queue, &f->io, &input, clock_valid ? &now_bits : NULL);
    assert(!f->locked && input.received == &caller_frame);
    return result;
}

static void complete_tx(Fixture *f, uint32_t at)
{
    assert(f->tx_control == 0x80);
    f->tx_control = 0x81;
    stamp(f->tx, at);
}

static void assert_reply(const Fixture *f, unsigned expected_count, uint8_t pci)
{
    assert(f->sent == expected_count && f->tx_control == 0x80);
    assert(((uint16_t)f->tx[0] << 6 | f->tx[1]) == CHERY_DTC_CAN_REPLY_ID);
    assert(f->tx[6] == pci);
}

static void test_fifo_busy_and_flow_control(void)
{
    Fixture f;
    init(&f, 7);
    assert(chery_dtc_store_snapshot(&f.dtc, 0, 0x10));
    assert(chery_dtc_store_snapshot(&f.dtc, 1, 0x12));
    assert(capture(&f, 14, 7, 20, session, sizeof(session)) == LFJ8_H03_DTC_RX_QUEUED);
    assert(capture(&f, 15, 7, 30, read_dtc, sizeof(read_dtc)) == LFJ8_H03_DTC_RX_QUEUED);
    assert(poll(&f, 40, true).diagnostic_consumed && f.queue.count == 1);
    assert_reply(&f, 1, 2);
    assert(f.tx[7] == 0x50);
    assert(!poll(&f, 42, true).diagnostic_consumed && f.queue.count == 1);
    complete_tx(&f, 50);
    assert(!poll(&f, 55, false).diagnostic_consumed && f.queue.count == 1);
    assert(poll(&f, 60, true).diagnostic_consumed && f.queue.count == 0);
    assert_reply(&f, 2, 0x10);

    assert(capture(&f, 14, 7, 70, flow_control, sizeof(flow_control)) == LFJ8_H03_DTC_RX_QUEUED);
    assert(!poll(&f, 75, true).diagnostic_consumed && f.queue.count == 1);
    complete_tx(&f, 90);
    assert(poll(&f, 96, true).diagnostic_consumed && f.queue.count == 0 && f.sent == 2);
    assert(f.broker.diagnostic.link.phase == CHERY_DTC_LINK_AWAITING_FLOW_CONTROL);
    assert(capture(&f, 15, 7, 100, flow_control, sizeof(flow_control)) == LFJ8_H03_DTC_RX_QUEUED);
    assert(poll(&f, 106, true).diagnostic_consumed && f.queue.count == 0);
    assert_reply(&f, 3, 0x21);
}

static void test_generation_reset(void)
{
    Fixture f;
    init(&f, UINT32_MAX);
    assert(poll(&f, 0, true).available);
    assert(capture(&f, 15, UINT32_MAX, 10, session, sizeof(session)) == LFJ8_H03_DTC_RX_QUEUED);
    assert(capture(&f, 14, UINT32_MAX, 12, read_dtc, sizeof(read_dtc)) == LFJ8_H03_DTC_RX_QUEUED);
    f.status |= BUS_OFF;
    f.grant = false;
    assert(!poll(&f, 20, false).available && f.queue.count == 2 && f.sent == 0);

    f.status = BASIC_RUNNING;
    f.grant = true;
    const Lfj8H03Can13Result old_lease = poll(&f, 24, true);
    assert(!old_lease.available && old_lease.diagnostic_consumed && f.queue.count == 1 && f.sent == 0);

    f.generation = 0;
    f.tx_control = 0; /* Hardware drain before releasing the new generation. */
    assert(!poll(&f, 30, true).diagnostic_consumed && f.queue.count == 1 && f.sent == 0);
    assert(lfj8_h03_dtc_rx_queue_reset(&f.queue, &f.io, f.generation) && f.queue.count == 0);
    assert(capture(&f, 14, UINT32_MAX, 34, session, sizeof(session)) == LFJ8_H03_DTC_RX_REJECTED);
    assert(capture(&f, 15, 0, 36, session, sizeof(session)) == LFJ8_H03_DTC_RX_QUEUED);
    assert(poll(&f, 40, true).diagnostic_consumed && f.queue.count == 0);
    assert_reply(&f, 1, 2);
}

static void test_busy_expiry_after_can_wrap(void)
{
    Fixture f;
    init(&f, 7);
    assert(capture(&f, 14, 7, 20, session, sizeof(session)) == LFJ8_H03_DTC_RX_QUEUED);
    assert(poll(&f, 24, true).diagnostic_consumed && f.sent == 1);
    assert(capture(&f, 15, 7, 30, read_dtc, sizeof(read_dtc)) == LFJ8_H03_DTC_RX_QUEUED);
    assert(!poll(&f, 32, true).diagnostic_consumed && f.queue.count == 1 && f.tx_control == 0x80);
    const uint32_t wrap = UINT32_C(2) * 65536u;
    assert(can_tick(32 + wrap) == can_tick(32));
    assert(!poll(&f, 32 + wrap, true).diagnostic_consumed);
    assert(f.queue.count == 0 && f.queue.expired == 1 && f.sent == 1);
}

static void test_irq_during_dispatch(void)
{
    Fixture f;
    init(&f, 7);
    assert(capture(&f, 14, 7, 20, session, sizeof(session)) == LFJ8_H03_DTC_RX_QUEUED);
    f.replace_after_peek = true;
    assert(poll(&f, 40, true).diagnostic_consumed);
    /* A stale broker decision cannot acknowledge the new queue head. */
    assert(f.queue.count == 1 && f.queue.expired == 1 && f.sent == 0);
    assert(poll(&f, 304, true).diagnostic_consumed && f.queue.count == 0);
    assert_reply(&f, 1, 2);
}

int main(void)
{
    test_fifo_busy_and_flow_control();
    test_generation_reset();
    test_busy_expiry_after_can_wrap();
    test_irq_during_dispatch();
    puts("PASS H03 DTC foreground: FIFO/FC, CAN generation, busy wrap, IRQ between peek and consume");
    return 0;
}
