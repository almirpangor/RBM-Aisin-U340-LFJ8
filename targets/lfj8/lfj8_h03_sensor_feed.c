#include "lfj8_h03_sensor_feed.h"
#include "lfj8_bridge.h"

#define CLOCK_HALF_RANGE UINT32_C(0x80000000)

static int valid_timeout(uint32_t ticks)
{
    return ticks != 0u && ticks < CLOCK_HALF_RANGE;
}

static void reset_sources(const Lfj8H03SensorSources *sources)
{
    lfj8_9e1c_raw_vss_init(sources->s51);
    lfj8_9e1c_raw_nt_init(sources->s83);
    lfj8_h03_atf_init(sources->atf);
}

static int track_clock_offset(Lfj8H03SensorFeed *feed, const Lfj8CapturePair *pair)
{
    uint32_t lower = pair->tml1_offset_min;
    uint32_t span = pair->tml_read_span_ticks;
    if (feed->tml1_offset_seen) {
        uint32_t previous_span = feed->tml1_offset_span;
        const uint32_t advance = lower - feed->tml1_offset_min;
        if (advance <= previous_span) {
            previous_span -= advance;
        } else {
            const uint32_t retreat = feed->tml1_offset_min - lower;
            if (retreat > span) {
                return 0;
            }
            lower = feed->tml1_offset_min;
            span -= retreat;
        }
        /* Keep only offsets admitted by every coherent read this epoch. */
        if (span > previous_span) {
            span = previous_span;
        }
    }
    feed->tml1_offset_min = lower;
    feed->tml1_offset_span = (uint16_t)span;
    feed->tml1_offset_seen = 1u;
    return 1;
}

Lfj8H03SensorResult lfj8_h03_sensor_feed_snapshot(
    Lfj8H03SensorFeed *feed, const Lfj8H03SensorSources *sources,
    const Lfj8RegisterIo *io, const Lfj8H03SensorFeedConfig *config,
    Lfj8H03SensorClock clock, Lfj8H03SensorSnapshot *snapshot)
{
    if (!snapshot) {
        return LFJ8_H03_SENSOR_INVALID;
    }
    if (!feed || !sources || !sources->s51 || !sources->s83 || !sources->atf ||
        !io || !io->enter || !io->leave || !io->read32 || !io->read8 || !config ||
        !valid_timeout(config->s51_timeout_ticks) || !valid_timeout(config->s83_timeout_ticks) ||
        !valid_timeout(config->atf_max_age_us) || clock.standstill_confirmed > 1u) {
        *snapshot = (Lfj8H03SensorSnapshot){.epoch = 0u};
        return LFJ8_H03_SENSOR_INVALID;
    }

    const uint32_t saved = io->enter(io->context);
    Lfj8H03SensorResult result;
    if (clock.qualified_1mhz != 1u) {
        reset_sources(sources);
        feed->epoch_seen = 0u;
        feed->tml1_offset_seen = 0u;
        result = LFJ8_H03_SENSOR_CLOCK_UNAVAILABLE;
    } else if (!feed->epoch_seen || feed->epoch != clock.epoch) {
        reset_sources(sources);
        feed->epoch = clock.epoch;
        feed->epoch_seen = 1u;
        feed->tml1_offset_seen = 0u;
        result = LFJ8_H03_SENSOR_NEW_EPOCH;
    } else if (!lfj8_h03_capture_pair(sources->s51, sources->s83, io,
                config->s51_timeout_ticks, config->s83_timeout_ticks,
                config->max_read_span_ticks, &snapshot->capture)) {
        result = LFJ8_H03_SENSOR_UNALIGNED;
    } else if (!track_clock_offset(feed, &snapshot->capture)) {
        reset_sources(sources);
        feed->epoch_seen = 0u;
        feed->tml1_offset_seen = 0u;
        result = LFJ8_H03_SENSOR_CLOCK_UNAVAILABLE;
    } else {
        if (snapshot->capture.vss.state == LFJ8_VSS_UNAVAILABLE &&
            !sources->s51->primed && clock.standstill_confirmed) {
            snapshot->capture.vss.state = LFJ8_VSS_STOPPED;
        }
        snapshot->atf_valid = (uint8_t)lfj8_h03_atf_snapshot(sources->atf, io,
            snapshot->capture.now_tml0, config->atf_max_age_us, &snapshot->atf);
        snapshot->epoch = feed->epoch;
        result = LFJ8_H03_SENSOR_SNAPSHOT;
    }
    if (result != LFJ8_H03_SENSOR_SNAPSHOT) {
        *snapshot = (Lfj8H03SensorSnapshot){.epoch = 0u};
    }
    io->leave(io->context, saved);
    return result;
}
