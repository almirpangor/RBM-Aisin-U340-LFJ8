#include "lfj8_h03_dtc_target.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>

enum {
    CNT = 0x801000, STAT = 0x801002, EXTID = 0x801004, TSTMP = 0x801008,
    SLIMK = 0x801010, MODE = 0x801018, GMSKS0 = 0x801028, GMSKS1 = 0x801029,
    MSC13 = 0x80105d, SLOT13 = 0x8011d0, MSC14 = 0x80105e, SLOT14 = 0x8011e0,
    OEM_STATE = 0x806ae6, TML0 = 0x8003e0, BASIC_RUNNING = 0x0800, BUS_OFF = 0x4000,
    DTC_AGE_BITS = 100, BOTH_RX = LFJ8_H03_DTC_RX14_PENDING | LFJ8_H03_DTC_RX15_PENDING,
};

static const uint8_t session[] = {2, 0x10, 0x86};
static const uint8_t read_dtc[] = {3, 0x17, 0xff, 0};
static const uint8_t clear_dtc[] = {3, 0x14, 0xff, 0};
static const uint8_t flow_control[] = {0x30, 0, 0};

typedef struct {
    Lfj8H03Can13 broker;
    Lfj8H03DtcRxQueue queue;
    CheryDtcState dtc;
    Lfj8RegisterIo io;
    uint32_t generation;
    uint32_t now_us;
    uint32_t clock_reads;
    uint32_t clock_span_us;
    uint16_t status;
    uint8_t tx[16];
    uint8_t rx[2][16];
    uint8_t tx_control;
    uint8_t rx_control[2];
    uint8_t bus_off_on_rx_slot;
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
    if (address >= MSC14 && address < MSC14 + 2u) {
        return f->rx_control[address - MSC14];
    }
    if (address >= SLOT14 && address < SLOT14 + 32u) {
        const unsigned slot = (address - SLOT14) / 16u;
        const unsigned offset = (address - SLOT14) % 16u;
        if (slot + 14u == f->bus_off_on_rx_slot && offset == 15u) {
            f->status |= BUS_OFF;
        }
        return f->rx[slot][offset];
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
    const uint32_t saved = f->locked ? 18u : 17u;
    f->locked = true;
    return saved;
}

static void prepare_rx(Fixture *f, uint8_t slot, uint32_t at_us,
                       const uint8_t *frame, uint8_t length)
{
    const unsigned index = slot - 14u;
    uint8_t *rx = f->rx[index];
    memset(rx, 0, sizeof(f->rx[index]));
    rx[0] = 0x1c;
    rx[1] = 0x32;
    rx[5] = length;
    memcpy(&rx[6], frame, length);
    stamp(rx, at_us);
    f->rx_control[index] = 0x41;
}

static Lfj8H03DtcRxPublish capture(Fixture *f, uint8_t slot, uint32_t generation,
                                   uint32_t now_us, const uint8_t *frame, uint8_t length)
{
    prepare_rx(f, slot, now_us, frame, length);
    f->now_us = now_us;
    const Lfj8H03DtcRxPublish result = lfj8_h03_dtc_rx_queue_capture_basic(
        &f->queue, &f->io, slot, generation, now_us, can_tick(now_us));
    assert(f->rx_control[slot - 14u] == 0x41 && !f->locked);
    f->rx_control[slot - 14u] = 0x40; /* OEM acknowledges after the observer returns. */
    return result;
}

static uint16_t capture_pending(Fixture *f, uint16_t pending, uint32_t now_us)
{
    f->now_us = now_us;
    const uint16_t result = lfj8_h03_dtc_rx_queue_capture_pending(
        &f->queue, &f->io, pending, f->generation, now_us, can_tick(now_us));
    assert(!f->locked);
    return result;
}

static void leave(void *context, uint32_t saved)
{
    Fixture *f = context;
    assert(f->locked && (saved == 17u || saved == 18u));
    f->locked = saved == 18u;
    if (!f->locked && f->replace_after_peek) {
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
    assert(!f->locked && input.received == &caller_frame && input.owns_slot13 == f->grant);
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
    prepare_rx(&f, 14, 20, session, sizeof(session));
    prepare_rx(&f, 15, 30, read_dtc, sizeof(read_dtc));
    assert(capture_pending(&f, BOTH_RX, 34) == BOTH_RX);
    assert(f.rx_control[0] == 0x41 && f.rx_control[1] == 0x41);
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
    /* The sample and grant were valid before CAN went bus-off. */
    f.status |= BUS_OFF;
    assert(!poll(&f, 20, true).available && f.queue.count == 0 && f.sent == 0);

    f.status = BASIC_RUNNING;
    const Lfj8H03Can13Result old_lease = poll(&f, 24, true);
    assert(!old_lease.available && !old_lease.diagnostic_consumed && f.queue.count == 0 && f.sent == 0);

    f.generation = 0;
    f.tx_control = 0; /* Hardware drain before releasing the new generation. */
    assert(!poll(&f, 30, true).diagnostic_consumed && f.queue.count == 0 && f.sent == 0);
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
    /* The TX timeout also elapsed, so the session cutoff clears the queue
     * before any entry can be aged using the wrapped CAN timestamp. */
    assert(f.queue.count == 0 && f.queue.session_boundary_active && f.sent == 1);
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

static void take_service(Fixture *f, uint32_t now_us, uint8_t service)
{
    Lfj8H03DtcRxDelivery delivery;
    assert(lfj8_h03_dtc_rx_queue_peek(&f->queue, &f->io, f->generation, now_us,
                                     can_tick(now_us), &delivery));
    assert(delivery.received.frame.data[1] == service);
    assert(lfj8_h03_dtc_rx_queue_consume(&f->queue, &f->io, &delivery));
}

static void test_batch_wrap_and_tie(void)
{
    Fixture f;
    init(&f, 7);
    prepare_rx(&f, 14, 508, session, sizeof(session));
    prepare_rx(&f, 15, 514, read_dtc, sizeof(read_dtc));
    assert(can_tick(508) == 0xfffeu && can_tick(514) == 0x0001u);
    assert(capture_pending(&f, BOTH_RX, 516) == BOTH_RX);
    take_service(&f, 518, 0x10);
    take_service(&f, 518, 0x17);

    prepare_rx(&f, 14, 520, read_dtc, sizeof(read_dtc));
    prepare_rx(&f, 15, 520, session, sizeof(session));
    assert(capture_pending(&f, BOTH_RX, 522) == BOTH_RX);
    take_service(&f, 524, 0x10);
    take_service(&f, 524, 0x17);

    prepare_rx(&f, 14, 528, read_dtc, sizeof(read_dtc));
    prepare_rx(&f, 15, 526, session, sizeof(session));
    assert(capture_pending(&f, BOTH_RX, 530) == BOTH_RX);
    take_service(&f, 532, 0x10);
    take_service(&f, 532, 0x17);
}

static void test_batch_rejects_loss_and_stale_samples(void)
{
    Fixture f;
    init(&f, 7);
    prepare_rx(&f, 14, 20, session, sizeof(session));
    prepare_rx(&f, 15, 30, read_dtc, sizeof(read_dtc));
    f.rx_control[0] = 0x45;
    assert(capture_pending(&f, 0x8000u, 32) == 0 && f.queue.rejected == 0);
    assert(capture_pending(&f, BOTH_RX | 0x8000u, 32) == LFJ8_H03_DTC_RX15_PENDING);
    assert(f.rx_control[0] == 0x45 && f.rx_control[1] == 0x41 && f.queue.rejected == 1);
    take_service(&f, 34, 0x17);

    prepare_rx(&f, 14, 20, session, sizeof(session));
    prepare_rx(&f, 15, 240, read_dtc, sizeof(read_dtc));
    assert(capture_pending(&f, BOTH_RX, 242) == LFJ8_H03_DTC_RX15_PENDING);
    take_service(&f, 244, 0x17);
    assert(f.queue.rejected == 2);

    prepare_rx(&f, 14, 246, session, sizeof(session));
    prepare_rx(&f, 15, 254, read_dtc, sizeof(read_dtc));
    assert(capture_pending(&f, BOTH_RX, 250) == LFJ8_H03_DTC_RX14_PENDING);
    take_service(&f, 252, 0x10);
    assert(f.queue.rejected == 3 && f.queue.count == 0);

    prepare_rx(&f, 14, 260, session, sizeof(session));
    prepare_rx(&f, 15, 262, read_dtc, sizeof(read_dtc));
    assert(capture_pending(&f, LFJ8_H03_DTC_RX15_PENDING, 264) == LFJ8_H03_DTC_RX15_PENDING);
    take_service(&f, 266, 0x17);
    assert(f.queue.count == 0 && f.queue.rejected == 3);
    assert(lfj8_h03_dtc_rx_queue_capture_pending(&f.queue, &f.io, BOTH_RX, 6,
                                                 268, can_tick(268)) == 0);
    assert(f.queue.count == 0 && f.queue.rejected == 5);
}

static void test_batch_capacity_and_bus_off(void)
{
    Fixture f;
    init(&f, 7);
    for (unsigned i = 0; i < LFJ8_H03_DTC_RX_CAPACITY - 1; ++i) {
        assert(capture(&f, 14, 7, 20 + 2u * i, read_dtc, sizeof(read_dtc)) == LFJ8_H03_DTC_RX_QUEUED);
    }
    prepare_rx(&f, 14, 30, session, sizeof(session));
    prepare_rx(&f, 15, 32, flow_control, sizeof(flow_control));
    assert(capture_pending(&f, BOTH_RX, 34) == LFJ8_H03_DTC_RX14_PENDING);
    assert(f.queue.count == LFJ8_H03_DTC_RX_CAPACITY && f.queue.overflow == 1);
    for (unsigned i = 0; i < LFJ8_H03_DTC_RX_CAPACITY - 1; ++i) {
        take_service(&f, 36, 0x17);
    }
    take_service(&f, 36, 0x10);

    prepare_rx(&f, 14, 40, read_dtc, sizeof(read_dtc));
    prepare_rx(&f, 15, 42, session, sizeof(session));
    f.bus_off_on_rx_slot = 14;
    assert(capture_pending(&f, BOTH_RX, 44) == 0 && f.queue.count == 0 && f.queue.rejected == 2);
}

static void test_dispatch_marks_one_attempt(void)
{
    Fixture f;
    init(&f, 7);
    Lfj8H03DtcRxDispatch dispatch;
    prepare_rx(&f, 14, 20, session, sizeof(session));
    prepare_rx(&f, 15, 22, read_dtc, sizeof(read_dtc));
    assert(lfj8_h03_dtc_rx_dispatch_begin(&dispatch, &f.queue, &f.io, BOTH_RX,
                                         7, 24, can_tick(24)) == BOTH_RX);
    assert(!lfj8_h03_dtc_rx_dispatch_skip_paired(&dispatch, 13, 7));
    assert(lfj8_h03_dtc_rx_dispatch_skip_paired(&dispatch, 15, 7));
    assert(!lfj8_h03_dtc_rx_dispatch_skip_paired(&dispatch, 15, 7));
    assert(!lfj8_h03_dtc_rx_dispatch_skip_paired(&dispatch, 14, 8));
    assert(!lfj8_h03_dtc_rx_dispatch_skip_paired(&dispatch, 14, 7));
    take_service(&f, 26, 0x10);
    take_service(&f, 26, 0x17);

    prepare_rx(&f, 14, 26, session, sizeof(session));
    prepare_rx(&f, 15, 28, read_dtc, sizeof(read_dtc));
    assert(lfj8_h03_dtc_rx_dispatch_begin(&dispatch, &f.queue, &f.io, BOTH_RX,
                                         7, 30, can_tick(30)) == BOTH_RX);
    assert(lfj8_h03_dtc_rx_dispatch_begin(&dispatch, &f.queue, &f.io, LFJ8_H03_DTC_RX14_PENDING,
                                         7, 32, can_tick(32)) == 0);
    assert(!lfj8_h03_dtc_rx_dispatch_skip_paired(&dispatch, 14, 7) && f.queue.count == 2);
}

static uint32_t target_clock(void *context)
{
    Fixture *f = context;
    assert(f->locked);
    return f->now_us + ((f->clock_reads++ & 1u) ? f->clock_span_us : 0u);
}

static bool target_test_epoch(void *context, uint32_t *generation)
{
    const Fixture *f = context;
    *generation = f->generation;
    return f->grant;
}

static Lfj8H03Can13Result target_test_poll(void *context, Lfj8H03Can13 *broker,
                                          Lfj8H03DtcRxQueue *queue, const Lfj8RegisterIo *io,
                                          Lfj8H03Can13Input *input, const uint16_t *can_now,
                                          bool native_ready)
{
    const Fixture *f = context;
    const bool grant = f->grant && native_ready && can_now;
    if (grant) {
        lfj8_h03_dtc_rx_queue_reset(queue, io, f->generation);
    }
    const uint32_t saved_generation = input->generation;
    const uint8_t saved_grant = input->owns_slot13;
    input->generation = queue->generation;
    input->owns_slot13 = grant;
    const Lfj8H03Can13Result result = lfj8_h03_dtc_foreground_poll(
        broker, queue, io, input, grant ? can_now : NULL);
    input->generation = saved_generation;
    input->owns_slot13 = saved_grant;
    return result;
}

static Lfj8H03Can13Result poll_target_at(Fixture *f, Lfj8H03DtcTarget *target,
                                        uint32_t now_us, uint32_t t6_tick)
{
    f->now_us = now_us;
    Lfj8H03Can13Input input = {
        .generation = 1234, .now_us = 5678, .diagnostic_tick = t6_tick,
        .owns_slot13 = 0, .dtc = &f->dtc,
    };
    const Lfj8H03Can13Result result = lfj8_h03_dtc_target_poll(target, &input, true);
    assert(!f->locked && input.generation == 1234 && input.now_us == now_us);
    assert(input.owns_slot13 == 0 && input.received == NULL);
    return result;
}

static Lfj8H03Can13Result poll_target(Fixture *f, Lfj8H03DtcTarget *target, uint32_t now_us)
{
    return poll_target_at(f, target, now_us, now_us / 100u);
}

static void test_target_transport_and_reset(void)
{
    Fixture f;
    Lfj8H03DtcTarget target;
    init(&f, UINT32_MAX);
    const Lfj8H03DtcCanOwnerOps owner = {target_test_epoch, target_test_poll, &f};
    f.grant = false;
    assert(lfj8_h03_dtc_target_init(&target, &f.broker, &f.io, &owner, target_clock, 4));
    prepare_rx(&f, 14, 20, session, sizeof(session));
    rbm_h03_dtc_rx_observe(14);
    assert(target.queue.count == 0 && f.clock_reads == 0);
    f.grant = true;
    assert(poll_target(&f, &target, 18).available);
    assert(target.queue.generation == UINT32_MAX);
    f.clock_reads = 0;
    assert(chery_dtc_store_snapshot(&f.dtc, 0, 0x10));
    assert(chery_dtc_store_snapshot(&f.dtc, 1, 0x12));
    prepare_rx(&f, 15, 22, read_dtc, sizeof(read_dtc));
    f.now_us = 24;
    rbm_h03_dtc_rx_begin(BOTH_RX);
    rbm_h03_dtc_rx_observe(15);
    rbm_h03_dtc_rx_observe(14);
    assert(target.queue.count == 2 && f.clock_reads == 2);
    assert(f.rx_control[0] == 0x41 && f.rx_control[1] == 0x41);
    assert(poll_target(&f, &target, 26).diagnostic_consumed && target.queue.count == 1);
    assert_reply(&f, 1, 2);
    assert(f.tx[7] == 0x50 && f.tx[8] == 0x86);
    assert(!poll_target(&f, &target, 28).diagnostic_consumed && target.queue.count == 1);
    complete_tx(&f, 30);
    assert(poll_target(&f, &target, 32).diagnostic_consumed && target.queue.count == 0);
    assert_reply(&f, 2, 0x10);
    complete_tx(&f, 34);
    poll_target(&f, &target, 36);
    prepare_rx(&f, 15, 38, flow_control, sizeof(flow_control));
    f.now_us = 40;
    rbm_h03_dtc_rx_begin(LFJ8_H03_DTC_RX15_PENDING);
    rbm_h03_dtc_rx_observe(15);
    assert(poll_target(&f, &target, 42).diagnostic_consumed);
    assert_reply(&f, 3, 0x21);

    prepare_rx(&f, 14, 44, session, sizeof(session));
    f.now_us = 46;
    rbm_h03_dtc_rx_begin(LFJ8_H03_DTC_RX14_PENDING);
    rbm_h03_dtc_rx_observe(14);
    assert(target.queue.count == 1);
    f.grant = false;
    f.status |= BUS_OFF;
    rbm_h03_dtc_rx_observe(14);
    assert(!poll_target(&f, &target, 48).available && f.sent == 3);
    f.status = BASIC_RUNNING;
    f.tx_control = 0;
    f.rx_control[0] = f.rx_control[1] = 0x40; /* Owner drains hardware before admission. */
    f.generation = 0;
    f.grant = true;
    assert(poll_target(&f, &target, 50).available && f.sent == 3);
    assert(target.queue.count == 0 && target.dispatch.paired_slots == 0 && target.queue.generation == 0);
    assert(f.broker.diagnostic.link.session.mode_bits == 0x9f);
    prepare_rx(&f, 15, 52, session, sizeof(session));
    f.now_us = 54;
    rbm_h03_dtc_rx_begin(LFJ8_H03_DTC_RX15_PENDING);
    rbm_h03_dtc_rx_observe(15);
    assert(poll_target(&f, &target, 56).diagnostic_consumed);
    assert_reply(&f, 4, 2);
    lfj8_h03_dtc_target_unbind();
}

static void test_target_clock_pair_and_unbind(void)
{
    Fixture f;
    Lfj8H03DtcTarget target;
    init(&f, 0);
    const Lfj8H03DtcCanOwnerOps owner = {target_test_epoch, target_test_poll, &f};
    assert(!lfj8_h03_dtc_target_init(&target, &f.broker, &f.io, &owner, target_clock, 200));
    assert(lfj8_h03_dtc_target_init(&target, &f.broker, &f.io, &owner, target_clock, 4));
    f.now_us = UINT32_MAX - 1u;
    f.clock_span_us = 5;
    prepare_rx(&f, 14, f.now_us, session, sizeof(session));
    rbm_h03_dtc_rx_observe(14);
    assert(target.queue.count == 0);
    f.clock_span_us = 4;
    rbm_h03_dtc_rx_observe(14);
    assert(target.queue.count == 1);
    f.clock_span_us = 5;
    assert(!poll_target(&f, &target, UINT32_MAX).available && target.queue.count == 0 && f.sent == 0);
    f.clock_span_us = 0;
    const Lfj8H03Can13Result recovered = poll_target_at(&f, &target, 0, UINT32_MAX / 100u);
    assert(recovered.available && !recovered.diagnostic_consumed && f.sent == 0);
    prepare_rx(&f, 15, 2, session, sizeof(session));
    f.now_us = 4;
    rbm_h03_dtc_rx_observe(15);
    assert(poll_target_at(&f, &target, 6, UINT32_MAX / 100u).diagnostic_consumed);
    assert_reply(&f, 1, 2);
    lfj8_h03_dtc_target_unbind();
    Lfj8H03Can13Input input = {.dtc = &f.dtc, .owns_slot13 = 1};
    rbm_h03_dtc_rx_observe(14);
    assert(!lfj8_h03_dtc_target_poll(&target, &input, true).available && target.queue.count == 0);
}

static void observe_target(Fixture *f, uint8_t slot, uint32_t arrived_at, uint32_t now_us,
                           const uint8_t *frame, uint8_t length)
{
    prepare_rx(f, slot, arrived_at, frame, length);
    f->now_us = now_us;
    rbm_h03_dtc_rx_observe(slot);
    assert(f->rx_control[slot - 14u] == 0x41u);
    f->rx_control[slot - 14u] = 0x40u;
}

static void open_target_session(Fixture *f, Lfj8H03DtcTarget *target, uint32_t tick)
{
    assert(poll_target_at(f, target, 10, tick).available);
    observe_target(f, 14, 20, 22, session, sizeof(session));
    assert(poll_target_at(f, target, 24, tick).diagnostic_consumed);
    assert_reply(f, 1, 2);
}

static void test_target_session_expiry_and_rx_boundary(void)
{
    Fixture f;
    Lfj8H03DtcTarget target;
    init(&f, 7);
    const Lfj8H03DtcCanOwnerOps owner = {target_test_epoch, target_test_poll, &f};
    assert(lfj8_h03_dtc_target_init(&target, &f.broker, &f.io, &owner, target_clock, 4));
    assert(chery_dtc_store_snapshot(&f.dtc, 0, 0x10));
    assert(chery_dtc_set_current(&f.dtc, 0x10, true));
    const CheryDtcState before = f.dtc;
    const uint32_t first_release = UINT32_C(0xffffff40);
    open_target_session(&f, &target, first_release - 1);
    complete_tx(&f, 26);
    poll_target_at(&f, &target, 28, first_release - 1);

    for (unsigned i = 0; i < 8u; ++i) {
        const uint32_t release = first_release + 128u * i;
        const uint32_t us = 48u + 40u * i;
        poll_target_at(&f, &target, us, release - 1u);
        assert(f.broker.diagnostic.link.session_steps_left == 9u - i);
        poll_target_at(&f, &target, us + 2u, release);
        poll_target_at(&f, &target, us + 4u, release);
        assert(f.broker.diagnostic.link.session_steps_left == 8u - i);
    }
    observe_target(&f, 14, 504, 506, clear_dtc, sizeof(clear_dtc));
    observe_target(&f, 15, 506, 508, session, sizeof(session));
    assert(target.queue.count == 2u);
    const uint32_t deadline = first_release + 8u * 128u;
    assert(!poll_target_at(&f, &target, 512, deadline).diagnostic_consumed);
    assert(target.queue.count == 0u && f.sent == 1u && target.queue.generation == 7u);
    assert(f.broker.diagnostic.link.session.mode_bits == 0x9fu);
    assert(f.broker.diagnostic.link.session.permission_bits == 0x11u);
    assert(memcmp(&f.dtc, &before, sizeof(before)) == 0);

    /* An IRQ that had not observed its hardware slot cannot restore the
     * old frame. Include CAN timestamp wrap and an equal timestamp. */
    observe_target(&f, 14, 510, 514, session, sizeof(session));
    observe_target(&f, 15, 512, 516, session, sizeof(session));
    assert(target.queue.count == 0u && target.queue.rejected == 2u);
    observe_target(&f, 15, 518, 520, session, sizeof(session));
    assert(target.queue.count == 1u);
    assert(poll_target_at(&f, &target, 522, deadline).diagnostic_consumed);
    assert_reply(&f, 2u, 2u);
    assert(f.broker.diagnostic.link.session_steps_left == 9u);
    lfj8_h03_dtc_target_unbind();
}

static void test_target_session_clock_loss(void)
{
    Fixture f;
    Lfj8H03DtcTarget target;
    init(&f, 7);
    const Lfj8H03DtcCanOwnerOps owner = {target_test_epoch, target_test_poll, &f};
    assert(lfj8_h03_dtc_target_init(&target, &f.broker, &f.io, &owner, target_clock, 4));
    open_target_session(&f, &target, 63);
    complete_tx(&f, 26);
    poll_target_at(&f, &target, 28, 63);
    /* Four releases accumulated in one readiness bit. */
    poll_target_at(&f, &target, 40, 448);
    assert(f.broker.diagnostic.link.session_steps_left == 8u);
    observe_target(&f, 15, 42, 44, clear_dtc, sizeof(clear_dtc));
    assert(target.queue.count == 1u);
    poll_target_at(&f, &target, 46, 16);
    assert(target.queue.count == 0u && f.sent == 1u);
    assert(f.broker.diagnostic.link.session.mode_bits == 0x9fu);

    /* A new, drained CAN generation starts without the old RX boundary. */
    f.generation++;
    poll_target_at(&f, &target, 46, 16);
    observe_target(&f, 14, 46, 48, session, sizeof(session));
    assert(poll_target_at(&f, &target, 50, 16).diagnostic_consumed);
    assert_reply(&f, 2u, 2u);
    lfj8_h03_dtc_target_unbind();
}

static void test_target_loses_clock_pair_with_tx_in_flight(void)
{
    Fixture f;
    Lfj8H03DtcTarget target;
    init(&f, 7);
    const Lfj8H03DtcCanOwnerOps owner = {target_test_epoch, target_test_poll, &f};
    assert(lfj8_h03_dtc_target_init(&target, &f.broker, &f.io, &owner, target_clock, 4));
    assert(chery_dtc_raise_c0(&f.dtc, 0x10, false));
    const CheryDtcState before = f.dtc;
    open_target_session(&f, &target, 63);
    observe_target(&f, 14, 26, 28, clear_dtc, sizeof(clear_dtc));
    observe_target(&f, 15, 30, 32, session, sizeof(session));
    assert(target.queue.count == 2u);

    f.clock_span_us = 5;
    const Lfj8H03Can13Result lost = poll_target_at(&f, &target, 34, 0);
    assert(!lost.available && !lost.diagnostic_consumed && target.queue.count == 0);
    assert(f.broker.diagnostic.link.session.mode_bits == 0x9fu &&
           f.broker.diagnostic.link.session.permission_bits == 0x11u &&
           f.broker.diagnostic.session_clock_tick == 63);
    assert(f.sent == 1u && f.tx_control == 0x80u);
    assert(memcmp(&f.dtc, &before, sizeof(before)) == 0);

    f.clock_span_us = 0;
    assert(!poll_target_at(&f, &target, 36, 64).available && f.sent == 1u);
    f.tx_control = 0; /* Native setup drains TX before publishing the new epoch. */
    ++f.generation;
    assert(poll_target_at(&f, &target, 38, 64).available && f.sent == 1u);
    observe_target(&f, 14, 40, 42, session, sizeof(session));
    assert(poll_target_at(&f, &target, 44, 64).diagnostic_consumed);
    assert_reply(&f, 2u, 2u);
    assert(memcmp(&f.dtc, &before, sizeof(before)) == 0);
    lfj8_h03_dtc_target_unbind();
}

static void test_target_session_expiry_drains_tx(void)
{
    Fixture f;
    Lfj8H03DtcTarget target;
    init(&f, 7);
    const Lfj8H03DtcCanOwnerOps owner = {target_test_epoch, target_test_poll, &f};
    assert(lfj8_h03_dtc_target_init(&target, &f.broker, &f.io, &owner, target_clock, 4));
    open_target_session(&f, &target, 63);
    /* Start this boundary test with a submitted reply and one step left. */
    for (unsigned i = 0; i < 8u; ++i) {
        assert(!lfj8_h03_dtc_can_session_step(&f.broker.diagnostic));
    }
    observe_target(&f, 15, 26, 28, session, sizeof(session));
    assert(!poll_target_at(&f, &target, 30, 64).diagnostic_consumed);
    assert(f.sent == 1u && f.tx_control == 0u);
    assert(target.queue.count == 0u && f.broker.diagnostic.link.session.mode_bits == 0x9fu);
    lfj8_h03_dtc_target_unbind();
}

static void check_target_transport_expiry(bool waiting_for_fc)
{
    Fixture f;
    Lfj8H03DtcTarget target;
    init(&f, 7);
    const Lfj8H03DtcCanOwnerOps owner = {target_test_epoch, target_test_poll, &f};
    assert(lfj8_h03_dtc_target_init(&target, &f.broker, &f.io, &owner, target_clock, 4));
    assert(chery_dtc_store_snapshot(&f.dtc, 0, 0x10));
    assert(chery_dtc_store_snapshot(&f.dtc, 1, 0x12));
    const CheryDtcState before = f.dtc;
    const uint32_t tick = UINT32_MAX - 100u;
    open_target_session(&f, &target, tick);

    if (waiting_for_fc) {
        complete_tx(&f, 26);
        observe_target(&f, 14, 28, 30, read_dtc, sizeof(read_dtc));
        assert(poll_target_at(&f, &target, 32, tick).diagnostic_consumed);
        assert_reply(&f, 2u, 0x10u);
        complete_tx(&f, 34);
        assert(poll_target_at(&f, &target, 36, tick).available);
    }
    const CheryDtcLinkPhase phase = waiting_for_fc
        ? CHERY_DTC_LINK_AWAITING_FLOW_CONTROL : CHERY_DTC_LINK_AWAITING_TX;
    const uint32_t duration = waiting_for_fc
        ? CHERY_DTC_LINK_FLOW_CONTROL_TICKS : CHERY_DTC_LINK_TX_CONFIRM_TICKS;
    const unsigned sent = f.sent;
    const uint32_t deadline = tick + duration;
    assert(poll_target_at(&f, &target, 504, deadline - 1u).available);
    assert(f.broker.diagnostic.link.phase == phase && f.sent == sent);
    observe_target(&f, 14, 506, 508, session, sizeof(session));
    observe_target(&f, 15, 508, 510, clear_dtc, sizeof(clear_dtc));
    assert(target.queue.count == 2u);

    const Lfj8H03Can13Result expired = poll_target_at(&f, &target, 512, deadline);
    assert(expired.available && !expired.diagnostic_consumed && target.queue.count == 0u);
    assert(f.sent == sent && !(f.tx_control & 0x80u));
    assert(f.broker.diagnostic.link.session.mode_bits == 0x9fu);
    assert(memcmp(&f.dtc, &before, sizeof(before)) == 0);

    /* IRQ delivery of an older or equal hardware timestamp must not
     * reintroduce a request after the transport boundary. */
    observe_target(&f, 14, 510, 514, session, sizeof(session));
    observe_target(&f, 15, 512, 516, session, sizeof(session));
    assert(target.queue.count == 0u && target.queue.rejected == 2u);
    observe_target(&f, 15, 518, 520, session, sizeof(session));
    assert(poll_target_at(&f, &target, 522, deadline + 1u).diagnostic_consumed);
    assert_reply(&f, sent + 1u, 2u);
    assert(memcmp(&f.dtc, &before, sizeof(before)) == 0);
    lfj8_h03_dtc_target_unbind();
}

static void test_new_generation_discards_the_old_deadline(void)
{
    Fixture f;
    init(&f, 7);
    assert(capture(&f, 14, 7, 20, session, sizeof(session)) == LFJ8_H03_DTC_RX_QUEUED);
    assert(poll(&f, 24, true).diagnostic_consumed);
    assert_reply(&f, 1u, 2u);

    /* Native setup drains the previous TX and publishes a fresh RX generation. */
    ++f.generation;
    f.tx_control = 0u;
    assert(lfj8_h03_dtc_rx_queue_reset(&f.queue, &f.io, f.generation));
    assert(capture(&f, 15, f.generation, 20000, session, sizeof(session)) == LFJ8_H03_DTC_RX_QUEUED);
    assert(poll(&f, 20002, true).diagnostic_consumed);
    assert_reply(&f, 2u, 2u);
    assert(f.queue.count == 0u && !f.queue.session_boundary_active);
}

int main(void)
{
    test_fifo_busy_and_flow_control();
    test_generation_reset();
    test_busy_expiry_after_can_wrap();
    test_irq_during_dispatch();
    test_batch_wrap_and_tie();
    test_batch_rejects_loss_and_stale_samples();
    test_batch_capacity_and_bus_off();
    test_dispatch_marks_one_attempt();
    test_target_transport_and_reset();
    test_target_clock_pair_and_unbind();
    test_target_session_expiry_and_rx_boundary();
    test_target_session_clock_loss();
    test_target_loses_clock_pair_with_tx_in_flight();
    test_target_session_expiry_drains_tx();
    check_target_transport_expiry(false);
    check_target_transport_expiry(true);
    test_new_generation_discards_the_old_deadline();
    puts("PASS H03 DTC foreground: FIFO/FC, CAN generation, busy wrap, IRQ between peek and consume");
    puts("PASS BasicCAN pair: timestamp order, rollover, tie, loss, FIFO capacity, bus-off");
    puts("PASS BasicCAN dispatch markers: one attempt, generation, next dispatch");
    puts("PASS H03 DTC target: bound IRQ, FC, reset, bounded clocks and unbind");
    puts("PASS H03 C0 session: nine releases, coalescing, T6/CAN wrap, RX boundary, clock loss and TX drain");
    puts("PASS H03 transport expiry: TX and FC deadlines discard queued and late RX");
    return 0;
}
