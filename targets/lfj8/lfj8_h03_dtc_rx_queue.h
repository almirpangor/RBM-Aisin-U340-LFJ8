#ifndef RBM_LFJ8_H03_DTC_RX_QUEUE_H
#define RBM_LFJ8_H03_DTC_RX_QUEUE_H

#include "lfj8_h03_dtc_can.h"

enum { LFJ8_H03_DTC_RX_CAPACITY = 4 };
enum { LFJ8_H03_DTC_RX15_PENDING = 0x0001, LFJ8_H03_DTC_RX14_PENDING = 0x0002 };

typedef struct {
    Lfj8H03DtcReceive received;
    uint32_t ticket;
} Lfj8H03DtcRxDelivery;

typedef struct {
    Lfj8H03DtcRxDelivery delivery;
    uint32_t captured_at_us;
    uint16_t initial_age_bits;
} Lfj8H03DtcRxEntry;

typedef struct {
    Lfj8H03DtcRxEntry entries[LFJ8_H03_DTC_RX_CAPACITY];
    uint32_t generation;
    uint32_t next_ticket;
    uint32_t expired;
    uint32_t rejected;
    uint32_t overflow;
    uint16_t max_age_bits;
    uint16_t bit_time_us;
    uint8_t head;
    uint8_t count;
    bool initialized;
} Lfj8H03DtcRxQueue;

typedef enum {
    LFJ8_H03_DTC_RX_NOT_READY,
    LFJ8_H03_DTC_RX_REJECTED,
    LFJ8_H03_DTC_RX_FULL,
    LFJ8_H03_DTC_RX_QUEUED,
} Lfj8H03DtcRxPublish;

/* Cold initialization only, before enabling the producer. No heap allocation.
 * max_age_bits must be below half of the CAN timestamp period.
 * bit_time_us must be the actual integer bit period (2 for 500 kbit/s).
 * Queue age must be at most the diagnostic broker's receive age budget. */
bool lfj8_h03_dtc_rx_queue_init(Lfj8H03DtcRxQueue *queue, uint32_t generation,
                               uint16_t max_age_bits, uint16_t bit_time_us);

/* Called by the CAN owner after a hardware reset/drain, serialized with
 * broker dispatch. A changed generation flushes queued captures. Old
 * producer generations cannot reset the queue implicitly. */
bool lfj8_h03_dtc_rx_queue_reset(Lfj8H03DtcRxQueue *queue, const Lfj8RegisterIo *io,
                                uint32_t generation);

/* Native RX must supply a coherent stable 16-byte COPY, its pre-clear MSC
 * control and matching EXTID. This function does not read/clear hardware.
 * Capture now_us and can_now together, then publish without deferral.
 * Native capture must already reject overwrites and timestamp ambiguity.
 * All queue operations use enter/leave; they must mask the producer IRQ,
 * preserve prior state and provide compiler ordering on the single CPU. */
Lfj8H03DtcRxPublish lfj8_h03_dtc_rx_queue_publish(
    Lfj8H03DtcRxQueue *queue, const Lfj8RegisterIo *io, const uint8_t slot[16],
    uint8_t control, bool extended, uint32_t generation, uint32_t now_us,
    uint16_t can_now);

/* Observe one pending RX14/RX15 attempt before the OEM clears TRFIN.
 * Call once per OEM attempt with freshly paired clocks and the active
 * CAN generation. The owner must discard old hardware slots on reset before
 * publishing with the new generation. The only MMIO accesses are reads.
 * The OEM retains responsibility for acknowledgement and retries.
 * io->enter/leave must serialize with other CPU users of the slots and
 * preserve the caller's IRQ state. Hardware overwrites can still occur. */
Lfj8H03DtcRxPublish lfj8_h03_dtc_rx_queue_capture_basic(
    Lfj8H03DtcRxQueue *queue, const Lfj8RegisterIo *io, uint8_t slot,
    uint32_t generation, uint32_t now_us, uint16_t can_now);

/* Before OEM dispatch, pass one CAN0SLIST snapshot and one current pair
 * of clocks for the group. This owns observation of the pending RX14/RX15
 * slots for that pass. Use one capture path per attempt to avoid duplicates.
 * The OEM retains acknowledgement. Qualified copies are appended oldest
 * first by CAN timestamp, with RX15 first on a tie. Existing FIFO entries
 * retain their order. Return the CAN0SLIST bits of the slots appended. */
uint16_t lfj8_h03_dtc_rx_queue_capture_pending(
    Lfj8H03DtcRxQueue *queue, const Lfj8RegisterIo *io, uint16_t pending,
    uint32_t generation, uint32_t now_us, uint16_t can_now);

/* Call before EVERY broker poll, even while it is busy. This returns a
 * COPY, leaving the head queued. Expiry uses both CAN bits and monotonic
 * microseconds, so waiting a full 16-bit CAN wrap cannot rejuvenate it.
 * now_us must progress with real time; reset on clock discontinuity or
 * suspension of >= 2^31 us. Do not retain a delivery across dispatch cycles.
 * Serialize peek -> broker poll -> consume with CAN reset. The producer
 * may run between those steps. Consume only if diagnostic_consumed is true.
 * A stale consume cannot remove a newer head or a new CAN generation. */
bool lfj8_h03_dtc_rx_queue_peek(Lfj8H03DtcRxQueue *queue, const Lfj8RegisterIo *io,
                               uint32_t generation, uint32_t now_us,
                               uint16_t can_now, Lfj8H03DtcRxDelivery *delivery);
bool lfj8_h03_dtc_rx_queue_consume(Lfj8H03DtcRxQueue *queue, const Lfj8RegisterIo *io,
                                  const Lfj8H03DtcRxDelivery *delivery);

#endif
