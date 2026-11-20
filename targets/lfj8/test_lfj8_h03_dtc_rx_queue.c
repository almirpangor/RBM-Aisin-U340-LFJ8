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

int main(void)
{
    test_fifo_full_and_interrupted_consumer();
    test_age_wrap_and_initial_age();
    test_clock_sample_preempted_by_producer();
    test_expired_head_and_can_reset();
    test_validation_and_saturation();
    puts("H03 DTC RX queue: FIFO, overflow, stale delivery, time wrap and CAN reset PASS");
    printf("queue_bytes=%u delivery_bytes=%u capacity=%u\n",
           (unsigned)sizeof(Lfj8H03DtcRxQueue), (unsigned)sizeof(Lfj8H03DtcRxDelivery),
           LFJ8_H03_DTC_RX_CAPACITY);
    return 0;
}
