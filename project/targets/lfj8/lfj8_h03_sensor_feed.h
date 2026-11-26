#ifndef RBM_LFJ8_H03_SENSOR_FEED_H
#define RBM_LFJ8_H03_SENSOR_FEED_H

#include "lfj8_h03_atf.h"

typedef struct {
    uint32_t epoch;
    uint32_t tml1_offset_min;
    uint16_t tml1_offset_span;
    uint8_t epoch_seen;
    uint8_t tml1_offset_seen;
} Lfj8H03SensorFeed;

typedef struct {
    volatile Lfj8RawVss *s51;
    volatile Lfj8RawCapture *s83;
    volatile Lfj8H03Atf *atf;
} Lfj8H03SensorSources;

typedef struct {
    uint32_t s51_timeout_ticks;
    uint32_t s83_timeout_ticks;
    uint32_t atf_max_age_us;
    uint16_t max_read_span_ticks;
} Lfj8H03SensorFeedConfig;

typedef struct {
    uint32_t epoch;
    uint8_t qualified_1mhz;
    uint8_t standstill_confirmed;
} Lfj8H03SensorClock;

typedef struct {
    Lfj8CapturePair capture; /* vss_at_tml0 and nt_at_tml0 share now_tml0. */
    Lfj8H03AtfSample atf;   /* acquired_us is in the same 1 MHz epoch. */
    uint32_t epoch;
    uint8_t atf_valid;
} Lfj8H03SensorSnapshot;

typedef enum {
    LFJ8_H03_SENSOR_INVALID,
    LFJ8_H03_SENSOR_CLOCK_UNAVAILABLE,
    LFJ8_H03_SENSOR_NEW_EPOCH,
    LFJ8_H03_SENSOR_UNALIGNED,
    LFJ8_H03_SENSOR_SNAPSHOT
} Lfj8H03SensorResult;

/* Zero-initialize feed. All objects are disjoint. The clock owner must
 * verify continuous TML0/TML1 rates of 1 MHz, keep the supplied observation
 * stable during the call and revoke or advance the epoch on discontinuity.
 * Coherent capture brackets must share a TML1-to-TML0 offset throughout
 * an epoch. Loss of that overlap also invalidates producer history.
 * Standstill confirmation is independent of S51 pulse absence and belongs
 * to the supplied epoch. A fresh first S51 edge precludes STOPPED.
 * Poll often enough for modulo ages to stay valid.
 *
 * Use a nestable interrupt exclusion such as the native H03 MMIO adapter.
 * The raw capture and ATF producers must share that exclusion. Unqualified
 * time or a new epoch invalidates producer history before reuse. Only
 * SENSOR_SNAPSHOT publishes data, with per-channel validity. */
Lfj8H03SensorResult lfj8_h03_sensor_feed_snapshot(
    Lfj8H03SensorFeed *feed, const Lfj8H03SensorSources *sources,
    const Lfj8RegisterIo *io, const Lfj8H03SensorFeedConfig *config,
    Lfj8H03SensorClock clock, Lfj8H03SensorSnapshot *snapshot);

#endif
