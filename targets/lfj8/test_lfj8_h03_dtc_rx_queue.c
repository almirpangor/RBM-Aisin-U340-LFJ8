#include "lfj8_h03_dtc_rx_queue.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    bool inside;
    uint32_t irq_mask;
    unsigned entries;
    unsigned leaves;
} Critical;

static uint32_t enter(void *context)
{
    Critical *critical = context;
    assert(!critical->inside);
    critical->inside = true;
    ++critical->entries;
    const uint32_t saved = critical->irq_mask;
    critical->irq_mask = 1;
    return saved;
}

static void leave(void *context, uint32_t saved)
{
    Critical *critical = context;
    assert(critical->inside && critical->irq_mask == 1);
    critical->irq_mask = saved;
    critical->inside = false;
    ++critical->leaves;
}

static Lfj8RegisterIo io_for(Critical *critical)
{
    /* No hardware callbacks: the queue must never access MMIO. */
    return (Lfj8RegisterIo){.context = critical, .enter = enter, .leave = leave};
}

static void slot_at(uint8_t slot[16], uint16_t timestamp, uint8_t marker)
{
    memset(slot, 0, 16);
    slot[0] = 0x1c;
    slot[1] = 0x32;
    slot[5] = 3;
    slot[6] = 2;
    slot[7] = 0x10;
    slot[8] = marker;
    slot[14] = (uint8_t)(timestamp >> 8);
    slot[15] = (uint8_t)timestamp;
}

static Lfj8H03DtcRxPublish publish(Lfj8H03DtcRxQueue *queue, const Lfj8RegisterIo *io,
                                  uint32_t generation, uint32_t us,
                                  uint16_t bits, uint8_t marker)
{
    uint8_t slot[16];
    slot_at(slot, bits, marker);
    return lfj8_h03_dtc_rx_queue_publish(queue, io, slot, 0x41, false, generation, us, bits);
}

static void test_fifo_full_and_interrupted_consumer(void)
{
    Critical critical = {0};
    const Lfj8RegisterIo io = io_for(&critical);
    Lfj8H03DtcRxQueue queue;
    assert(lfj8_h03_dtc_rx_queue_init(&queue, 7, 800, 2));
    for (uint8_t i = 0; i < LFJ8_H03_DTC_RX_CAPACITY; ++i) {
        assert(publish(&queue, &io, 7, 1000 + 2u * i, 500 + i, i) == LFJ8_H03_DTC_RX_QUEUED);
    }
    Lfj8H03DtcRxDelivery first, again;
    assert(lfj8_h03_dtc_rx_queue_peek(&queue, &io, 7, 1020, 510, &first));
    /* IRQ arrives between foreground peek and acknowledgement. Full queue
     * drops the NEW request; it cannot replace the outstanding delivery. */
    assert(publish(&queue, &io, 7, 1022, 511, 99) == LFJ8_H03_DTC_RX_FULL);
    assert(lfj8_h03_dtc_rx_queue_peek(&queue, &io, 7, 1024, 512, &again));
    assert(again.ticket == first.ticket && again.received.frame.data[2] == 0);
    assert(queue.overflow == 1);
    assert(lfj8_h03_dtc_rx_queue_consume(&queue, &io, &first));
    assert(!lfj8_h03_dtc_rx_queue_consume(&queue, &io, &first));
    assert(publish(&queue, &io, 7, 1026, 513, 4) == LFJ8_H03_DTC_RX_QUEUED);
    for (uint8_t i = 1; i <= LFJ8_H03_DTC_RX_CAPACITY; ++i) {
        assert(lfj8_h03_dtc_rx_queue_peek(&queue, &io, 7, 1028, 514, &again));
        assert(again.received.frame.data[2] == i);
        assert(lfj8_h03_dtc_rx_queue_consume(&queue, &io, &again));
    }
    first = again;
    assert(!lfj8_h03_dtc_rx_queue_peek(&queue, &io, 7, 1028, 514, &again));
    assert(memcmp(&first, &again, sizeof(first)) == 0);
    assert(critical.entries == critical.leaves && !critical.inside && critical.irq_mask == 0);
}

static void test_age_wrap_and_initial_age(void)
{
    Critical critical = {.irq_mask = 1};
    const Lfj8RegisterIo io = io_for(&critical);
    Lfj8H03DtcRxQueue queue;
    Lfj8H03DtcRxDelivery delivered;
    uint8_t slot[16];
    assert(lfj8_h03_dtc_rx_queue_init(&queue, 1, 100, 2));
    slot_at(slot, 0xfff0, 0x86);
    /* Already 20 bits old at capture: 40 us of the 200 us budget spent. */
    const uint32_t start = UINT32_MAX - 100u;
    assert(lfj8_h03_dtc_rx_queue_publish(&queue, &io, slot, 0x41, false, 1, start, 4) ==
           LFJ8_H03_DTC_RX_QUEUED);
    memset(slot, 0xff, sizeof(slot)); /* Queue owns its copy. */
    assert(lfj8_h03_dtc_rx_queue_peek(&queue, &io, 1, start + 159u, 83, &delivered));
    assert(delivered.received.frame.data[2] == 0x86);
    assert(delivered.received.frame.data[3] == 0);
    /* 32-bit us and 16-bit CAN counters both wrapped; age equality expires. */
    assert(!lfj8_h03_dtc_rx_queue_peek(&queue, &io, 1, start + 160u, 83, &delivered));
    assert(queue.expired == 1);

    assert(publish(&queue, &io, 1, 1000, 500, 1) == LFJ8_H03_DTC_RX_QUEUED);
    /* CAN time alone would report zero age after an entire wrap. */
    assert(!lfj8_h03_dtc_rx_queue_peek(&queue, &io, 1, 1000 + 65536u * 2u, 500, &delivered));
    assert(queue.expired == 2);

    assert(publish(&queue, &io, 1, 200000, 1000, 2) == LFJ8_H03_DTC_RX_QUEUED);
    /* A backwards CAN sample is not deliverable, even with fresh us time. */
    assert(!lfj8_h03_dtc_rx_queue_peek(&queue, &io, 1, 200001, 999, &delivered));
    assert(lfj8_h03_dtc_rx_queue_peek(&queue, &io, 1, 200002, 1001, &delivered));
    assert(lfj8_h03_dtc_rx_queue_consume(&queue, &io, &delivered));
    assert(publish(&queue, &io, 1, 200004, 1002, 3) == LFJ8_H03_DTC_RX_QUEUED);
    assert(!lfj8_h03_dtc_rx_queue_peek(&queue, &io, 1, 200003, 1002, &delivered));
    assert(lfj8_h03_dtc_rx_queue_peek(&queue, &io, 1, 200006, 1003, &delivered));
    assert(lfj8_h03_dtc_rx_queue_consume(&queue, &io, &delivered));
    assert(queue.expired == 2 && critical.irq_mask == 1);
    assert(critical.entries == critical.leaves && !critical.inside);
}

static void test_clock_sample_preempted_by_producer(void)
{
    Critical critical = {0};
    const Lfj8RegisterIo io = io_for(&critical);
    Lfj8H03DtcRxQueue queue;
    Lfj8H03DtcRxDelivery delivered;
    assert(lfj8_h03_dtc_rx_queue_init(&queue, 1, 100, 2));
    /* Foreground sampled (1002 us, 701 bits); producer IRQ ran before
     * foreground could enter the queue's critical section. */
    assert(publish(&queue, &io, 1, 1004, 702, 0x86) == LFJ8_H03_DTC_RX_QUEUED);
    assert(!lfj8_h03_dtc_rx_queue_peek(&queue, &io, 1, 1002, 701, &delivered));
    assert(queue.count == 1 && queue.expired == 0);
    assert(lfj8_h03_dtc_rx_queue_peek(&queue, &io, 1, 1006, 703, &delivered));
    assert(delivered.received.frame.data[2] == 0x86);
}

static void test_expired_head_and_can_reset(void)
{
    Critical critical = {0};
    const Lfj8RegisterIo io = io_for(&critical);
    Lfj8H03DtcRxQueue queue;
    Lfj8H03DtcRxDelivery old, fresh;
    assert(lfj8_h03_dtc_rx_queue_init(&queue, UINT32_MAX, 100, 2));
    queue.next_ticket = UINT32_MAX - 1u;
    assert(publish(&queue, &io, UINT32_MAX, 1000, 500, 1) == LFJ8_H03_DTC_RX_QUEUED);
    assert(lfj8_h03_dtc_rx_queue_peek(&queue, &io, UINT32_MAX, 1000, 500, &old));
    assert(old.ticket == UINT32_MAX);
    /* The producer can retire an expired head while the consumer has a copy. */
    assert(publish(&queue, &io, UINT32_MAX, 1200, 600, 2) == LFJ8_H03_DTC_RX_QUEUED);
    assert(!lfj8_h03_dtc_rx_queue_consume(&queue, &io, &old));
    assert(lfj8_h03_dtc_rx_queue_peek(&queue, &io, UINT32_MAX, 1200, 600, &fresh));
    assert(fresh.ticket == 0 && fresh.received.frame.data[2] == 2);

    assert(!lfj8_h03_dtc_rx_queue_reset(&queue, &io, UINT32_MAX));
    assert(queue.count == 1);
    assert(lfj8_h03_dtc_rx_queue_reset(&queue, &io, 0));
    assert(queue.count == 0 && queue.expired == 1);
    assert(publish(&queue, &io, 0, 0, 0, 3) == LFJ8_H03_DTC_RX_QUEUED);
    assert(!lfj8_h03_dtc_rx_queue_consume(&queue, &io, &fresh));
    assert(publish(&queue, &io, UINT32_MAX, 0, 0, 9) == LFJ8_H03_DTC_RX_REJECTED);
    assert(!lfj8_h03_dtc_rx_queue_peek(&queue, &io, UINT32_MAX, 1000000, 0, &fresh));
    assert(queue.count == 1 && queue.generation == 0);
    assert(lfj8_h03_dtc_rx_queue_peek(&queue, &io, 0, 0, 0, &fresh));
    assert(fresh.received.frame.data[2] == 3 && fresh.ticket == 1);
    assert(lfj8_h03_dtc_rx_queue_consume(&queue, &io, &fresh));
}

static void test_validation_and_saturation(void)
{
    Critical critical = {0};
    const Lfj8RegisterIo io = io_for(&critical);
    Lfj8H03DtcRxQueue queue;
    Lfj8H03DtcRxDelivery delivered;
    uint8_t slot[16];
    assert(!lfj8_h03_dtc_rx_queue_init(NULL, 0, 100, 2));
    assert(!lfj8_h03_dtc_rx_queue_init(&queue, 0, 0, 2));
    assert(publish(&queue, &io, 0, 0, 0, 0) == LFJ8_H03_DTC_RX_NOT_READY);
    assert(!lfj8_h03_dtc_rx_queue_init(&queue, 0, 0x8000, 2));
    assert(!lfj8_h03_dtc_rx_queue_init(&queue, 0, 100, 0));
    assert(lfj8_h03_dtc_rx_queue_init(&queue, 0, 100, 2));
    assert(publish(&queue, NULL, 0, 0, 0, 0) == LFJ8_H03_DTC_RX_NOT_READY);
    Lfj8RegisterIo incomplete = io;
    incomplete.leave = NULL;
    assert(!lfj8_h03_dtc_rx_queue_peek(&queue, &incomplete, 0, 0, 0, &delivered));
    assert(critical.entries == 0);
    slot_at(slot, 0, 0x86);
    const uint8_t controls[] = {0x40, 0x43, 0x45, 0x51, 0x81};
    for (unsigned i = 0; i < sizeof(controls); ++i) {
        assert(lfj8_h03_dtc_rx_queue_publish(&queue, &io, slot, controls[i], false, 0, 0, 0) ==
               LFJ8_H03_DTC_RX_REJECTED);
    }
    assert(lfj8_h03_dtc_rx_queue_publish(&queue, &io, slot, 0x41, true, 0, 0, 0) ==
           LFJ8_H03_DTC_RX_REJECTED);
    assert(lfj8_h03_dtc_rx_queue_publish(&queue, &io, slot, 0x41, false, 0, 200, 100) ==
           LFJ8_H03_DTC_RX_REJECTED);
    slot[5] = 0;
    assert(lfj8_h03_dtc_rx_queue_publish(&queue, &io, slot, 0x41, false, 0, 0, 0) ==
           LFJ8_H03_DTC_RX_REJECTED);
    slot[5] = 9;
    assert(lfj8_h03_dtc_rx_queue_publish(&queue, &io, slot, 0x41, false, 0, 0, 0) ==
           LFJ8_H03_DTC_RX_REJECTED);
    slot[5] = 3;
    slot[1] = 0x21;
    assert(lfj8_h03_dtc_rx_queue_publish(&queue, &io, slot, 0x41, false, 0, 0, 0) ==
           LFJ8_H03_DTC_RX_REJECTED);
    queue.rejected = UINT32_MAX;
    assert(lfj8_h03_dtc_rx_queue_publish(&queue, &io, NULL, 0x41, false, 0, 0, 0) ==
           LFJ8_H03_DTC_RX_REJECTED);
    assert(queue.rejected == UINT32_MAX && queue.count == 0);
    for (unsigned i = 0; i < LFJ8_H03_DTC_RX_CAPACITY; ++i) {
        assert(publish(&queue, &io, 0, 0, 0, 0) == LFJ8_H03_DTC_RX_QUEUED);
    }
    queue.overflow = UINT32_MAX;
    assert(publish(&queue, &io, 0, 0, 0, 1) == LFJ8_H03_DTC_RX_FULL);
    assert(queue.overflow == UINT32_MAX);
    queue.expired = UINT32_MAX;
    /* Incoming fresh data reclaims expired entries, even if previously full. */
    assert(publish(&queue, &io, 0, 200, 100, 2) == LFJ8_H03_DTC_RX_QUEUED);
    assert(queue.expired == UINT32_MAX && queue.count == 1);
    assert(critical.entries == critical.leaves && !critical.inside);
}

enum { BASIC_STAT = 0x801002, BASIC_EXTID = 0x801004, BASIC_MSC = 0x801050,
       BASIC_DATA = 0x801100, BASIC_RUNNING = 0x0800 };

typedef struct {
    Critical critical; /* Shared enter/leave callbacks receive this first member. */
    uint8_t raw[16];
    uint8_t slot;
    uint8_t control;
    uint8_t replacement_control;
    uint16_t status;
    uint16_t extended;
    uint16_t replacement_status;
    unsigned replace_after;
    unsigned reads;
    unsigned control_reads;
} BasicCanModel;

static void begin_basic(BasicCanModel *model, uint8_t slot)
{
    *model = (BasicCanModel){.critical = {.irq_mask = 1}, .slot = slot,
                             .status = BASIC_RUNNING, .control = 0x41};
    slot_at(model->raw, 500, 0x86);
}

static uint8_t basic_read8(void *context, uint32_t address)
{
    BasicCanModel *model = context;
    assert(model->critical.inside);
    if (address == BASIC_MSC + (uint32_t)model->slot) {
        ++model->control_reads;
        return model->control;
    }
    const uint32_t base = BASIC_DATA + (uint32_t)model->slot * 16u;
    assert(address >= base && address < base + 16u);
    assert(model->control_reads == 1);
    const uint8_t value = model->raw[address - base];
    if (++model->reads == model->replace_after) {
        slot_at(model->raw, 501, 0x99);
        model->control = model->replacement_control;
        model->status = model->replacement_status;
    }
    return value;
}

static uint16_t basic_read16(void *context, uint32_t address)
{
    BasicCanModel *model = context;
    assert(model->critical.inside);
    assert(address == BASIC_STAT || address == BASIC_EXTID);
    return address == BASIC_STAT ? model->status : model->extended;
}

static Lfj8RegisterIo basic_io(BasicCanModel *model)
{
    return (Lfj8RegisterIo){.context = model, .enter = enter, .leave = leave,
                            .read8 = basic_read8, .read16 = basic_read16};
}

static void test_basic_capture_keeps_oem_ack(void)
{
    BasicCanModel model;
    const Lfj8RegisterIo io = basic_io(&model);
    Lfj8H03DtcRxQueue queue;
    assert(lfj8_h03_dtc_rx_queue_init(&queue, 9, 100, 2));
    begin_basic(&model, 14);
    model.raw[5] = 8;
    model.raw[13] = 0xC3;
    model.extended = 1; /* The other slot's IDE bit is independent. */
    assert(lfj8_h03_dtc_rx_queue_capture_basic(&queue, &io, 14, 9, 1008, 504) == LFJ8_H03_DTC_RX_QUEUED);
    assert(model.reads == 16 && model.control_reads == 2 && model.control == 0x41);
    assert(model.critical.entries == 1 && model.critical.leaves == 1 && model.critical.irq_mask == 1);

    begin_basic(&model, 15);
    model.raw[6] = 0x30;
    model.raw[7] = 0;
    model.raw[8] = 0;
    model.raw[13] = 0xEE; /* Bytes outside the actual DLC are undefined. */
    assert(lfj8_h03_dtc_rx_queue_capture_basic(&queue, &io, 15, 9, 1010, 505) == LFJ8_H03_DTC_RX_QUEUED);
    assert(model.control == 0x41 && queue.count == 2);
    memset(model.raw, 0xff, sizeof(model.raw));
    Lfj8H03DtcRxDelivery delivery;
    assert(lfj8_h03_dtc_rx_queue_peek(&queue, &io, 9, 1012, 506, &delivery));
    assert(delivery.received.frame.length == 8 && delivery.received.frame.data[7] == 0xC3);
    assert(delivery.received.can_timestamp == 500 && delivery.received.generation == 9);
    assert(lfj8_h03_dtc_rx_queue_consume(&queue, &io, &delivery));
    assert(lfj8_h03_dtc_rx_queue_peek(&queue, &io, 9, 1012, 506, &delivery));
    assert(delivery.received.frame.length == 3 && delivery.received.frame.data[0] == 0x30);
    assert(delivery.received.frame.data[7] == 0 && delivery.received.can_timestamp == 500);
    assert(lfj8_h03_dtc_rx_queue_consume(&queue, &io, &delivery));
}

static void test_basic_capture_drops_unqualified_slots(void)
{
    BasicCanModel model;
    const Lfj8RegisterIo io = basic_io(&model);
    Lfj8H03DtcRxQueue queue;
    assert(lfj8_h03_dtc_rx_queue_init(&queue, 9, 100, 2));
    const struct {
        uint8_t slot, control;
        uint16_t status, extended;
        uint32_t generation;
    } rejected[] = {
        {13, 0x41, BASIC_RUNNING, 0, 9}, {16, 0x41, BASIC_RUNNING, 0, 9},
        {15, 0x40, BASIC_RUNNING, 0, 9}, {15, 0x43, BASIC_RUNNING, 0, 9},
        {15, 0x45, BASIC_RUNNING, 0, 9}, {15, 0x49, BASIC_RUNNING, 0, 9},
        {15, 0x41, BASIC_RUNNING, 1, 9}, {14, 0x41, BASIC_RUNNING, 2, 9},
        {15, 0x41, 0x0000, 0, 9}, {15, 0x41, 0x4800, 0, 9},
        {15, 0x41, 0x0900, 0, 9}, {15, 0x41, 0x0a00, 0, 9},
        {15, 0x41, BASIC_RUNNING, 0, 8},
    };
    for (unsigned i = 0; i < sizeof(rejected) / sizeof(rejected[0]); ++i) {
        begin_basic(&model, rejected[i].slot);
        model.control = rejected[i].control;
        model.status = rejected[i].status;
        model.extended = rejected[i].extended;
        assert(lfj8_h03_dtc_rx_queue_capture_basic(&queue, &io, model.slot,
                   rejected[i].generation, 1008, 504) == LFJ8_H03_DTC_RX_REJECTED);
        assert(model.reads == 0 && queue.count == 0 && queue.rejected == i + 1);
    }

    begin_basic(&model, 15);
    model.raw[1] = 0x33;
    assert(lfj8_h03_dtc_rx_queue_capture_basic(&queue, &io, 15, 9, 1008, 504) == LFJ8_H03_DTC_RX_REJECTED);
    begin_basic(&model, 15);
    assert(lfj8_h03_dtc_rx_queue_capture_basic(&queue, &io, 15, 9, 1200, 600) == LFJ8_H03_DTC_RX_REJECTED);
    assert(queue.count == 0 && queue.next_ticket == 0);
}

static void test_basic_capture_drops_changes_during_copy(void)
{
    BasicCanModel model;
    const Lfj8RegisterIo io = basic_io(&model);
    Lfj8H03DtcRxQueue queue;
    assert(lfj8_h03_dtc_rx_queue_init(&queue, 9, 100, 2));
    for (unsigned boundary = 1; boundary <= 16; ++boundary) {
        begin_basic(&model, 15);
        model.replace_after = boundary;
        model.replacement_control = 0x45; /* TRFIN already set when this overwrite completes. */
        model.replacement_status = BASIC_RUNNING;
        assert(lfj8_h03_dtc_rx_queue_capture_basic(&queue, &io, 15, 9, 1008, 504) == LFJ8_H03_DTC_RX_REJECTED);
        assert(model.control_reads == 2 && model.control == 0x45 && queue.count == 0);
    }
    const uint8_t after[] = {0x47, 0x40, 0x41}; /* In progress, cleared, and bus-off below. */
    for (unsigned i = 0; i < sizeof(after); ++i) {
        begin_basic(&model, 14);
        model.replace_after = 8;
        model.replacement_control = after[i];
        model.replacement_status = after[i] == 0x41 ? 0x4800 : BASIC_RUNNING;
        assert(lfj8_h03_dtc_rx_queue_capture_basic(&queue, &io, 14, 9, 1008, 504) == LFJ8_H03_DTC_RX_REJECTED);
        assert(queue.count == 0 && queue.next_ticket == 0);
    }
    assert(queue.rejected == 19);
}

int main(void)
{
    test_fifo_full_and_interrupted_consumer();
    test_age_wrap_and_initial_age();
    test_clock_sample_preempted_by_producer();
    test_expired_head_and_can_reset();
    test_validation_and_saturation();
    test_basic_capture_keeps_oem_ack();
    test_basic_capture_drops_unqualified_slots();
    test_basic_capture_drops_changes_during_copy();
    puts("H03 DTC RX queue: FIFO, overflow, stale delivery, time wrap and CAN reset PASS");
    puts("H03 DTC BasicCAN capture: both slots, unchanged MSC, overwritten copy and bus-off PASS");
    printf("queue_bytes=%u delivery_bytes=%u capacity=%u\n",
           (unsigned)sizeof(Lfj8H03DtcRxQueue), (unsigned)sizeof(Lfj8H03DtcRxDelivery),
           LFJ8_H03_DTC_RX_CAPACITY);
    return 0;
}
