#include "lfj8_bridge.h"
#include "lfj8_h03_sensor_feed.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>

typedef struct {
    uint32_t tml0, tml1, span, s51_edge, s83_edge;
    unsigned tml0_reads;
    unsigned lock_depth;
    uint8_t atf_fault;
} Registers;

static uint32_t enter(void *context)
{
    Registers *registers = context;
    assert(registers->lock_depth < 2);
    return registers->lock_depth++;
}

static void leave(void *context, uint32_t saved)
{
    Registers *registers = context;
    assert(registers->lock_depth == saved + 1u);
    registers->lock_depth = saved;
}

static uint8_t read8(void *context, uint32_t address)
{
    const Registers *registers = context;
    assert(registers->lock_depth && address == UINT32_C(0x8063E7));
    return registers->atf_fault;
}

static uint16_t read16(void *context, uint32_t address)
{
    const Registers *registers = context;
    assert(registers->lock_depth && address == UINT32_C(0x804BC4));
    return 315u;
}

static uint32_t read32(void *context, uint32_t address)
{
    Registers *registers = context;
    assert(registers->lock_depth);
    switch (address) {
    case UINT32_C(0x8003E0):
        assert(registers->lock_depth == 2);
        return registers->tml0 + ((registers->tml0_reads++ & 1u) ? registers->span : 0u);
    case UINT32_C(0x800FE0):
        assert(registers->lock_depth == 2);
        return registers->tml1;
    case UINT32_C(0x8048B8):
        return registers->s51_edge;
    case UINT32_C(0x8048BC):
        return registers->s83_edge;
    case UINT32_C(0x804F04):
        return UINT32_C(0x3FC4E000);
    default:
        assert(address == UINT32_C(0x805028));
        return UINT32_C(0x42700000);
    }
}

static void seed_edges(Registers *registers, const Lfj8RegisterIo *io,
                       const Lfj8H03SensorSources *sources)
{
    const uint32_t saved = io->enter(registers);
    registers->s51_edge = UINT32_MAX - 150u;
    registers->s83_edge = 800u;
    lfj8_9e1c_raw_vss_after_capture_store(sources->s51, io, 1000u);
    lfj8_9e1c_raw_nt_after_capture_store(sources->s83, io, 1000u);
    registers->s51_edge += 100u;
    registers->s83_edge += 100u;
    lfj8_9e1c_raw_vss_after_capture_store(sources->s51, io, 1000u);
    lfj8_9e1c_raw_nt_after_capture_store(sources->s83, io, 1000u);
    io->leave(registers, saved);
}

static void seed_atf(const Lfj8RegisterIo *io, volatile Lfj8H03Atf *atf,
                     uint32_t acquired, uint32_t published)
{
    assert(lfj8_h03_atf_after_adc_store(atf, io, acquired));
    assert(lfj8_h03_atf_after_store(atf, io, LFJ8_H03_ATF_DIRECT_STORE,
                                     &acquired, published));
}

int main(void)
{
    Registers registers = {.tml0 = UINT32_MAX - 1u, .tml1 = 1000u, .span = 4u};
    const Lfj8RegisterIo io = {
        .context = &registers, .enter = enter, .leave = leave,
        .read8 = read8, .read16 = read16, .read32 = read32,
    };
    Lfj8RawVss s51;
    Lfj8RawCapture s83;
    Lfj8H03Atf atf;
    const Lfj8H03SensorSources sources = {.s51 = &s51, .s83 = &s83, .atf = &atf};
    Lfj8H03SensorFeed feed = {0};
    Lfj8H03SensorFeedConfig config = {1000u, 1000u, 1000u, 4u};
    Lfj8H03SensorClock clock = {.epoch = 1u, .qualified_1mhz = 1u};
    Lfj8H03SensorSnapshot snapshot;
    assert(lfj8_h03_sensor_feed_snapshot(&feed, &sources, &io, &config, clock, &snapshot)
           == LFJ8_H03_SENSOR_NEW_EPOCH);
    assert(!registers.lock_depth && !registers.tml0_reads && !snapshot.atf_valid);

    seed_edges(&registers, &io, &sources);
    seed_atf(&io, &atf, UINT32_MAX - 30u, UINT32_MAX - 5u);
    assert(lfj8_h03_sensor_feed_snapshot(&feed, &sources, &io, &config, clock, &snapshot)
           == LFJ8_H03_SENSOR_SNAPSHOT);
    assert(!registers.lock_depth && snapshot.epoch == 1u && snapshot.capture.now_tml0 == 2u);
    assert(snapshot.capture.vss.state == LFJ8_VSS_VALID && snapshot.capture.vss.interval_ticks == 100u);
    assert(snapshot.capture.vss_at_tml0 == UINT32_MAX - 50u);
    assert(snapshot.capture.nt.state == LFJ8_VSS_VALID && snapshot.capture.nt.interval_ticks == 100u);
    assert(snapshot.capture.nt_at_tml0 == UINT32_MAX - 99u);
    assert(snapshot.capture.nt_alignment_error_ticks == 2u);
    assert(snapshot.atf_valid && snapshot.atf.acquired_us == UINT32_MAX - 30u && snapshot.atf.atf_c == 60);

    clock.standstill_confirmed = 1u;
    registers.atf_fault = 1u;
    assert(lfj8_h03_sensor_feed_snapshot(&feed, &sources, &io, &config, clock, &snapshot)
           == LFJ8_H03_SENSOR_SNAPSHOT);
    assert(snapshot.capture.vss.state == LFJ8_VSS_VALID && !snapshot.atf_valid);

    registers.atf_fault = 0u;
    seed_atf(&io, &atf, UINT32_MAX - 25u, UINT32_MAX - 4u);
    config.atf_max_age_us = 29u; /* Age 26 at midpoint, age 28 at end. */
    assert(lfj8_h03_sensor_feed_snapshot(&feed, &sources, &io, &config, clock, &snapshot)
           == LFJ8_H03_SENSOR_SNAPSHOT);
    assert(snapshot.atf_valid && snapshot.atf.acquired_us == UINT32_MAX - 25u);
    config.atf_max_age_us = 28u;
    assert(lfj8_h03_sensor_feed_snapshot(&feed, &sources, &io, &config, clock, &snapshot)
           == LFJ8_H03_SENSOR_SNAPSHOT);
    assert(!snapshot.atf_valid && snapshot.capture.vss.state == LFJ8_VSS_VALID);
    config.atf_max_age_us = 1000u;

    registers.tml0 = 2000u;
    registers.tml1 = 3000u;
    clock.standstill_confirmed = 0u;
    assert(lfj8_h03_sensor_feed_snapshot(&feed, &sources, &io, &config, clock, &snapshot)
           == LFJ8_H03_SENSOR_SNAPSHOT);
    assert(snapshot.capture.vss.state == LFJ8_VSS_UNAVAILABLE);
    assert(snapshot.capture.nt.state == LFJ8_VSS_UNAVAILABLE && !snapshot.atf_valid);
    clock.standstill_confirmed = 1u;
    assert(lfj8_h03_sensor_feed_snapshot(&feed, &sources, &io, &config, clock, &snapshot)
           == LFJ8_H03_SENSOR_SNAPSHOT);
    assert(snapshot.capture.vss.state == LFJ8_VSS_STOPPED && snapshot.capture.nt.state == LFJ8_VSS_UNAVAILABLE);

    const uint32_t saved = io.enter(io.context);
    registers.s51_edge = 1900u; /* First new edge is not a complete interval. */
    lfj8_9e1c_raw_vss_after_capture_store(sources.s51, &io, config.s51_timeout_ticks);
    io.leave(io.context, saved);
    assert(lfj8_h03_sensor_feed_snapshot(&feed, &sources, &io, &config, clock, &snapshot)
           == LFJ8_H03_SENSOR_SNAPSHOT);
    assert(snapshot.capture.vss.state == LFJ8_VSS_UNAVAILABLE && s51.primed);

    registers.span = 5u;
    assert(lfj8_h03_sensor_feed_snapshot(&feed, &sources, &io, &config, clock, &snapshot)
           == LFJ8_H03_SENSOR_UNALIGNED);
    assert(!registers.lock_depth && !snapshot.capture.now_tml0 && !snapshot.atf_valid);
    assert(snapshot.capture.vss.state == LFJ8_VSS_UNAVAILABLE);

    registers.span = 4u;
    registers.atf_fault = 0u;
    seed_edges(&registers, &io, &sources);
    seed_atf(&io, &atf, 1900u, 1950u);
    assert(s51.primed && s83.primed && atf.valid);
    ++clock.epoch;
    assert(lfj8_h03_sensor_feed_snapshot(&feed, &sources, &io, &config, clock, &snapshot)
           == LFJ8_H03_SENSOR_NEW_EPOCH);
    assert(!s51.primed && !s83.primed && !atf.valid && !atf.adc_seen);
    assert(snapshot.capture.vss.state == LFJ8_VSS_UNAVAILABLE);

    /* A wrapped offset interval narrows, then a frozen TML1 is rejected
     * even when every individual TML0 step fits inside the read span. */
    registers.tml1 = registers.tml0 + 2u;
    assert(lfj8_h03_sensor_feed_snapshot(&feed, &sources, &io, &config, clock, &snapshot)
           == LFJ8_H03_SENSOR_SNAPSHOT);
    registers.tml0 += 4u;
    registers.tml1 += 6u;
    assert(lfj8_h03_sensor_feed_snapshot(&feed, &sources, &io, &config, clock, &snapshot)
           == LFJ8_H03_SENSOR_SNAPSHOT);
    for (unsigned i = 0; i < 4u; ++i) {
        ++registers.tml0;
        assert(lfj8_h03_sensor_feed_snapshot(&feed, &sources, &io, &config, clock, &snapshot)
               == LFJ8_H03_SENSOR_SNAPSHOT);
    }
    s51 = (Lfj8RawVss){.last_edge = registers.tml0, .interval_ticks = 100u, .primed = 1u};
    s83 = (Lfj8RawCapture){.last_edge = registers.tml1, .interval_ticks = 100u, .primed = 1u};
    seed_atf(&io, &atf, registers.tml0 - 10u, registers.tml0);
    ++registers.tml0;
    assert(lfj8_h03_sensor_feed_snapshot(&feed, &sources, &io, &config, clock, &snapshot)
           == LFJ8_H03_SENSOR_CLOCK_UNAVAILABLE);
    assert(!registers.lock_depth && !snapshot.epoch && !snapshot.atf_valid);
    assert(!s51.primed && !s83.primed && !atf.valid && !feed.tml1_offset_seen);
    assert(snapshot.capture.vss.state == LFJ8_VSS_UNAVAILABLE);

    ++clock.epoch;
    clock.qualified_1mhz = 0u;
    assert(lfj8_h03_sensor_feed_snapshot(&feed, &sources, &io, &config, clock, &snapshot)
           == LFJ8_H03_SENSOR_CLOCK_UNAVAILABLE);
    clock.qualified_1mhz = 1u;
    assert(lfj8_h03_sensor_feed_snapshot(&feed, &sources, &io, &config, clock, &snapshot)
           == LFJ8_H03_SENSOR_NEW_EPOCH);
    assert(lfj8_h03_sensor_feed_snapshot(&feed, &sources, &io, &config, clock, &snapshot)
           == LFJ8_H03_SENSOR_SNAPSHOT);
    registers.tml0 += 8u;
    registers.tml1 += 16u;
    assert(lfj8_h03_sensor_feed_snapshot(&feed, &sources, &io, &config, clock, &snapshot)
           == LFJ8_H03_SENSOR_CLOCK_UNAVAILABLE);
    config.s51_timeout_ticks = UINT32_C(0x80000000);
    assert(lfj8_h03_sensor_feed_snapshot(&feed, &sources, &io, &config, clock, &snapshot)
           == LFJ8_H03_SENSOR_INVALID);
    assert(!registers.lock_depth && !snapshot.atf_valid);
    puts("H03 S51/S83/ATF snapshot: shared epoch, standstill, expiry and reset PASS");
    return 0;
}
