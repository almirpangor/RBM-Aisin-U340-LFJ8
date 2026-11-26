#ifndef RBM_LFJ8_H03_ENGINE_RX_H
#define RBM_LFJ8_H03_ENGINE_RX_H

#include "lfj8_donor_io.h"
#include "ta2005_chery_inputs.h"

typedef enum {
    LFJ8_H03_RX_WAIT_FOR_OEM,
    LFJ8_H03_RX_ACTIVE,
    LFJ8_H03_RX_DRAIN_PENDING,
    LFJ8_H03_RX_CLOCK_WARMUP,
} Lfj8H03EngineRxPhase;

typedef struct {
    Ta2005CheryInputs inputs;
    uint32_t time_ticks;
    uint32_t last_poll_us;
    uint32_t last_clock_advance_us;
    uint16_t last_can_tick;
    uint16_t max_age_ticks;
    uint16_t max_poll_gap_us;
    uint8_t clock_running;
    /* Sticky until the feed owner invalidates any retained engine values. */
    uint8_t discontinuity;
    uint8_t rpm_stamp_valid;
    Lfj8H03EngineRxPhase phase;
    const volatile uint32_t *generation_source;
    uint32_t last_generation;
    uint32_t rpm_stamp_us; /* TML0 lower bound for the RPM retained by the qualifier. */
} Lfj8H03EngineRx;

/* The scheduler uses an independent monotonic microsecond clock. The CAN
 * age limit is in H03 timestamp ticks (one per CAN bit). The poll gap limit
 * must be <= 30000 us to keep the 16-bit counter delta below half a wrap.
 * Initialize before dispatch and reinitialize when changing the policy.
 * Initialization clears the generation binding. */
int lfj8_h03_engine_rx_init(Lfj8H03EngineRx *rx, uint16_t max_age_ticks,
                           uint16_t max_poll_gap_us);

/* Bind the CAN setup generation after init and before enabling RX. The
 * word is nonnull, aligned and lives as long as the receiver. The CAN
 * owner updates it under the same interrupt serialization used by poll.
 * Binding clears buffered data and restarts slot attachment. */
void lfj8_h03_engine_rx_bind_generation(Lfj8H03EngineRx *rx,
                                       const volatile uint32_t *generation);

/* A single foreground owner calls poll. io uses nestable saved interrupt
 * state so a reconfiguration cannot interrupt the two-slot transaction.
 * H03 completes CAN startup/recovery with the two slots clear. On BusOff
 * or ownership loss, attach again after OEM is operational with clear slots.
 * If bound, a change of generation takes the same path even if both the
 * CAN timestamp and the ownership flag appear continuous across polls.
 * After a scheduling or counter discontinuity, discard pending frames and
 * reestablish the clock before accepting new frames. During startup and
 * recovery, accept only frames timestamped strictly after the clock anchor.
 * The snapshot grants no permission to actuate. */
unsigned lfj8_h03_engine_rx_poll(Lfj8H03EngineRx *rx, const Lfj8RegisterIo *io,
                                uint32_t now_us, uint8_t slots_owned,
                                Ta2005CherySnapshot *snapshot);

typedef struct {
    int (*now_us)(uint32_t *now_us);
    uint8_t max_span_us;
    uint8_t max_bit_time_us;
} Lfj8H03EngineRxClock;

/* Bench route: now_us was read before CAN0TSTMP. Recheck TML0 after the
 * final counter read under the same lock, and allow one tick of CAN
 * quantization plus the qualified sampling bracket between anchors. */
unsigned lfj8_h03_engine_rx_poll_bounded(Lfj8H03EngineRx *rx, const Lfj8RegisterIo *io,
    uint32_t now_us, uint8_t slots_owned, Ta2005CherySnapshot *snapshot,
    const Lfj8H03EngineRxClock *clock);


#endif
