#include "lfj8_h03_dtc_rx_queue.h"

#define CAN0_STAT UINT32_C(0x801002)
#define CAN0_EXTID UINT32_C(0x801004)
#define CAN0_SLOT_CONTROL UINT32_C(0x801050)
#define CAN0_SLOT_DATA UINT32_C(0x801100)

enum {
    CAN0_STAT_BASIC = 0x0800,
    CAN0_STAT_UNAVAILABLE = 0x4300, /* BOS | LBS | CRS */
    CAN0_RX_COMPLETE = 0x41,       /* RR | TRFIN, without ML, TRSTAT or RA */
};

static bool ready(const Lfj8H03DtcRxQueue *queue, const Lfj8RegisterIo *io)
{
    return queue && queue->initialized && io && io->enter && io->leave;
}

static void increment(uint32_t *counter)
{
    if (*counter != UINT32_MAX) {
        ++*counter;
    }
}

static void remove_head(Lfj8H03DtcRxQueue *queue)
{
    queue->head = (uint8_t)((queue->head + 1u) % LFJ8_H03_DTC_RX_CAPACITY);
    --queue->count;
}

static bool expire(Lfj8H03DtcRxQueue *queue, uint32_t now_us, uint16_t can_now)
{
    const uint32_t budget = (uint32_t)queue->max_age_bits * queue->bit_time_us;
    while (queue->count) {
        const Lfj8H03DtcRxEntry *entry = &queue->entries[queue->head];
        const uint32_t elapsed = now_us - entry->captured_at_us;
        const uint32_t initial_age = (uint32_t)entry->initial_age_bits * queue->bit_time_us;
        const uint16_t can_age = (uint16_t)(can_now - entry->delivery.received.can_timestamp);
        /* The producer may interrupt after the foreground sampled its
         * clocks but before it entered this critical section. Wait for
         * a newer poll instead of deleting that newly arrived request. */
        if (elapsed >= UINT32_C(0x80000000)) {
            return false;
        }
        if (entry->delivery.received.generation == queue->generation &&
            elapsed < budget && initial_age < budget - elapsed) {
            if (can_age < queue->max_age_bits) {
                return true;
            }
            if (can_age >= 0x8000u) {
                return false;
            }
        }
        remove_head(queue);
        increment(&queue->expired);
    }
    return false;
}

bool lfj8_h03_dtc_rx_queue_init(Lfj8H03DtcRxQueue *queue, uint32_t generation,
                               uint16_t max_age_bits, uint16_t bit_time_us)
{
    if (!queue) {
        return false;
    }
    *queue = (Lfj8H03DtcRxQueue){0};
    if (!max_age_bits || max_age_bits >= 0x8000u || !bit_time_us) {
        return false;
    }
    queue->generation = generation;
    queue->max_age_bits = max_age_bits;
    queue->bit_time_us = bit_time_us;
    queue->initialized = true;
    return true;
}

bool lfj8_h03_dtc_rx_queue_reset(Lfj8H03DtcRxQueue *queue, const Lfj8RegisterIo *io,
                                uint32_t generation)
{
    if (!ready(queue, io)) {
        return false;
    }
    const uint32_t saved = io->enter(io->context);
    const bool changed = queue->generation != generation;
    if (changed) {
        queue->head = 0;
        queue->count = 0;
        queue->generation = generation;
        /* Keep next_ticket and lifetime counters across reset. */
    }
    io->leave(io->context, saved);
    return changed;
}

static Lfj8H03DtcRxPublish publish_locked(
    Lfj8H03DtcRxQueue *queue, const uint8_t slot[16], uint8_t control,
    bool extended, uint32_t generation, uint32_t now_us, uint16_t can_now)
{
    Lfj8H03DtcReceive received;
    Lfj8H03DtcRxPublish result = LFJ8_H03_DTC_RX_REJECTED;
    if (generation != queue->generation ||
        !lfj8_h03_dtc_can_decode_basic(&received, slot, control, extended, generation) ||
        (uint16_t)(can_now - received.can_timestamp) >= queue->max_age_bits) {
        increment(&queue->rejected);
    } else {
        expire(queue, now_us, can_now);
        if (queue->count == LFJ8_H03_DTC_RX_CAPACITY) {
            /* Preserve queued requests and any outstanding head delivery. */
            increment(&queue->overflow);
            result = LFJ8_H03_DTC_RX_FULL;
        } else {
            const unsigned index = (queue->head + queue->count) % LFJ8_H03_DTC_RX_CAPACITY;
            queue->entries[index] = (Lfj8H03DtcRxEntry){
                .delivery = {.received = received, .ticket = ++queue->next_ticket},
                .captured_at_us = now_us,
                .initial_age_bits = (uint16_t)(can_now - received.can_timestamp),
            };
            ++queue->count;
            result = LFJ8_H03_DTC_RX_QUEUED;
        }
    }
    return result;
}

Lfj8H03DtcRxPublish lfj8_h03_dtc_rx_queue_publish(
    Lfj8H03DtcRxQueue *queue, const Lfj8RegisterIo *io, const uint8_t slot[16],
    uint8_t control, bool extended, uint32_t generation, uint32_t now_us,
    uint16_t can_now)
{
    if (!ready(queue, io)) {
        return LFJ8_H03_DTC_RX_NOT_READY;
    }
    const uint32_t saved = io->enter(io->context);
    const Lfj8H03DtcRxPublish result =
        publish_locked(queue, slot, control, extended, generation, now_us, can_now);
    io->leave(io->context, saved);
    return result;
}

static bool basiccan_active(const Lfj8RegisterIo *io)
{
    const uint16_t status = io->read16(io->context, CAN0_STAT);
    return (status & (CAN0_STAT_BASIC | CAN0_STAT_UNAVAILABLE)) == CAN0_STAT_BASIC;
}

static bool capture_basic(const Lfj8RegisterIo *io, uint8_t slot, uint8_t copy[16])
{
    if (slot < 14u || slot > 15u || !basiccan_active(io)) {
        return false;
    }
    const uint32_t control = CAN0_SLOT_CONTROL + slot;
    if (io->read8(io->context, control) != CAN0_RX_COMPLETE ||
        (io->read16(io->context, CAN0_EXTID) & (UINT16_C(0x8000) >> slot)) != 0u) {
        return false;
    }

    /* Leave TRFIN set for the OEM. An overwrite during the copy sets ML
     * while TRFIN is set (Renesas 32176 §13.6.2, Fig. 13.6.2). */
    const uint32_t data = CAN0_SLOT_DATA + (uint32_t)slot * 16u;
    for (uint32_t offset = 0; offset < 16u; ++offset) {
        copy[offset] = io->read8(io->context, data + offset);
    }
    return io->read8(io->context, control) == CAN0_RX_COMPLETE && basiccan_active(io);
}

Lfj8H03DtcRxPublish lfj8_h03_dtc_rx_queue_capture_basic(
    Lfj8H03DtcRxQueue *queue, const Lfj8RegisterIo *io, uint8_t slot,
    uint32_t generation, uint32_t now_us, uint16_t can_now)
{
    if (!ready(queue, io) || !io->read8 || !io->read16) {
        return LFJ8_H03_DTC_RX_NOT_READY;
    }
    const uint32_t saved = io->enter(io->context);
    uint8_t copy[16];
    Lfj8H03DtcRxPublish result = LFJ8_H03_DTC_RX_REJECTED;
    if (generation == queue->generation && capture_basic(io, slot, copy)) {
        result = publish_locked(queue, copy, CAN0_RX_COMPLETE, false, generation, now_us, can_now);
    } else {
        increment(&queue->rejected);
    }
    io->leave(io->context, saved);
    return result;
}

bool lfj8_h03_dtc_rx_queue_peek(Lfj8H03DtcRxQueue *queue, const Lfj8RegisterIo *io,
                               uint32_t generation, uint32_t now_us,
                               uint16_t can_now, Lfj8H03DtcRxDelivery *delivery)
{
    if (!ready(queue, io) || !delivery) {
        return false;
    }
    const uint32_t saved = io->enter(io->context);
    bool found = false;
    if (generation == queue->generation) {
        if (expire(queue, now_us, can_now)) {
            *delivery = queue->entries[queue->head].delivery;
            found = true;
        }
    }
    io->leave(io->context, saved);
    return found;
}

bool lfj8_h03_dtc_rx_queue_consume(Lfj8H03DtcRxQueue *queue, const Lfj8RegisterIo *io,
                                  const Lfj8H03DtcRxDelivery *delivery)
{
    if (!ready(queue, io) || !delivery) {
        return false;
    }
    const uint32_t saved = io->enter(io->context);
    const bool matches = queue->count &&
        delivery->received.generation == queue->generation &&
        delivery->ticket == queue->entries[queue->head].delivery.ticket;
    if (matches) {
        remove_head(queue);
    }
    io->leave(io->context, saved);
    return matches;
}
