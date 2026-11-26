#include "bench_sensor_profile.h"
#include "lfj8_bridge.h"
#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_input_lifecycle.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_sensor_target.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>

volatile Lfj8H03Atf rbm_h03_atf_state;
volatile uint8_t rbm_h03_tml0_1mhz_qualified;
Lfj8H03SensorTarget rbm_h03_sensor_state;

static uint32_t ticks[2], delta[2], edge[2];
static uint8_t prescaler = 9u, tml1_mode = 0x31u, running;
static uint32_t depth, register_reads, timer_reads, change_on_read;

static uint8_t read8(void *context, uint32_t address)
{
    assert(!context && depth);
    switch (address) {
    case 0x800203: ++register_reads; return prescaler;
    case 0x8003EB: return 0x01u;
    case 0x800FEB: return tml1_mode;
    case 0x8063E7: return 0u;
    }
    assert(0);
    return 0u;
}

static uint16_t read16(void *context, uint32_t address)
{
    assert(!context && depth && address == 0x804BC4);
    return 320u;
}

static uint32_t read32(void *context, uint32_t address)
{
    assert(!context && depth);
    switch (address) {
    case 0x8048B8: return edge[0];
    case 0x8048BC: return edge[1];
    case 0x804F04: return 0x3FC80000u; /* 320 * 5 / 1024 */
    case 0x805028: return 0x42700000u; /* 60 degrees from the simulated OEM store */
    }
    assert(address == 0x8003E0 || address == 0x800FE0);
    const unsigned timer = address == 0x800FE0;
    if (++timer_reads == change_on_read) {
        tml1_mode = 0x30u;
    }
    const uint32_t value = ticks[timer];
    ticks[timer] += delta[timer];
    return value;
}

static uint32_t enter(void *context)
{
    assert(!context);
    return depth++;
}

static void leave(void *context, uint32_t saved)
{
    assert(!context && depth == saved + 1u);
    depth = saved;
}

const Lfj8RegisterIo lfj8_h03_mmio = {
    .read8 = read8, .read16 = read16, .read32 = read32, .enter = enter, .leave = leave,
};

int lfj8_h03_application_running_locked(void)
{
    assert(depth);
    return running;
}

static int probe(void)
{
    const uint32_t saved = enter(NULL);
    const int ready = rbm_h03_target_clock_ready(NULL);
    leave(NULL, saved);
    return ready;
}

static void arm(void)
{
    delta[0] = delta[1] = 1u;
    assert(probe() && !rbm_h03_tml0_1mhz_qualified);
    delta[0] = delta[1] = 0u;
    assert(rbm_h03_sensor_clock_rebase(1u));
    running = 1u;
}

static void set_time(uint32_t tml0)
{
    ticks[0] = tml0;
    ticks[1] = tml0 + 137u;
}

static void capture_edges(uint32_t tml0)
{
    set_time(tml0);
    edge[0] = ticks[0];
    edge[1] = ticks[1];
    const uint32_t saved = enter(NULL);
    rbm_h03_s51_capture_callback();
    rbm_h03_s83_capture_callback();
    leave(NULL, saved);
}

static void publish_atf(uint32_t tml0)
{
    set_time(tml0);
    const uint32_t saved = enter(NULL);
    uint32_t acquired;
    rbm_h03_atf_adc_callback();
    assert(rbm_h03_atf_source_callback(320u, &acquired) && acquired == tml0);
    set_time(tml0 + 1u);
    rbm_h03_atf_publish_callback(LFJ8_H03_ATF_DIRECT_STORE, &acquired);
    leave(NULL, saved);
}

static void probe_faults(void)
{
    /* Neither a joint stall nor one stalled counter can admit an epoch. */
    timer_reads = 0u;
    assert(!probe());
    assert(timer_reads == 2u + 2u * (LFJ8_H03_BENCH_CPU_NOMINAL_HZ / LFJ8_H03_BENCH_TML_NOMINAL_HZ));
    delta[0] = 1u;
    assert(!probe());
    delta[0] = 0u;
    delta[1] = 1u;
    assert(!probe());

    /* Register mismatch at entry, or newly observed within the bracket. */
    delta[0] = 1u;
    prescaler = 8u;
    assert(!probe());
    prescaler = 9u;
    timer_reads = register_reads = 0u;
    change_on_read = 3u;
    assert(!probe() && register_reads == 2u);
    change_on_read = 0u;
    tml1_mode = 0x31u;

    /* A true 32-bit wrap progresses. A backward jump within the probe fails. */
    ticks[0] = ticks[1] = UINT32_MAX;
    assert(probe());
    delta[1] = UINT32_MAX;
    assert(!probe());
    delta[0] = delta[1] = 0u;
}

static void sensor_path(void)
{
    Lfj8H03SensorSnapshot snapshot;
    Lfj8H03BenchRawCapture raw;
    set_time(UINT32_MAX - 2000u);
    arm();
    const uint32_t epoch = rbm_h03_sensor_state.feed.epoch;
    assert(rbm_h03_sensor_foreground(0u, &snapshot) == LFJ8_H03_SENSOR_SNAPSHOT);
    assert(snapshot.capture.vss.state == LFJ8_VSS_UNAVAILABLE);
    assert(!snapshot.atf_valid);
    assert(rbm_h03_sensor_foreground(1u, &snapshot) == LFJ8_H03_SENSOR_SNAPSHOT);
    assert(snapshot.capture.vss.state == LFJ8_VSS_STOPPED);

    capture_edges(UINT32_MAX - 999u);
    assert(rbm_h03_sensor_foreground(1u, &snapshot) == LFJ8_H03_SENSOR_SNAPSHOT);
    assert(snapshot.capture.vss.state == LFJ8_VSS_UNAVAILABLE); /* First edge is not stop. */
    capture_edges(0u);
    publish_atf(200u);
    assert(rbm_h03_sensor_foreground(0u, &snapshot) == LFJ8_H03_SENSOR_SNAPSHOT);
    assert(snapshot.epoch == epoch && snapshot.atf_valid && snapshot.atf.acquired_us == 200u);
    assert(snapshot.atf.atf_c == 60 && snapshot.atf.toyota_gp_m7184 == 25600u);
    assert(rbm_h03_bench_raw_capture(&snapshot, &raw));
    assert(raw.epoch == epoch && raw.clock_basis == LFJ8_H03_BENCH_CLOCK_OEM_NOMINAL);
    assert(raw.nominal_tick_hz == 1000000u && raw.s51_edges_num == 100u && raw.s51_edges_den == 22u);
    assert(raw.capture->vss.state == LFJ8_VSS_VALID && raw.capture->vss.interval_ticks == 1000u);
    assert(raw.capture->vss_at_tml0 == 0u && raw.capture->nt_edge_tml1 == 137u);
    assert(raw.capture->nt.state == LFJ8_VSS_VALID && raw.capture->nt.interval_ticks == 1000u);

    set_time(200u + rbm_h03_sensor_config.atf_max_age_us - 1u);
    assert(rbm_h03_sensor_foreground(0u, &snapshot) == LFJ8_H03_SENSOR_SNAPSHOT && snapshot.atf_valid);
    set_time(200u + rbm_h03_sensor_config.atf_max_age_us);
    assert(rbm_h03_sensor_foreground(0u, &snapshot) == LFJ8_H03_SENSOR_SNAPSHOT && !snapshot.atf_valid);
    set_time(rbm_h03_sensor_config.s51_timeout_ticks + 1u);
    assert(rbm_h03_sensor_foreground(0u, &snapshot) == LFJ8_H03_SENSOR_SNAPSHOT);
    assert(snapshot.capture.vss.state == LFJ8_VSS_UNAVAILABLE && snapshot.capture.nt.state == LFJ8_VSS_VALID);

    /* Relative change with unchanged controls revokes the common epoch. */
    ++ticks[1];
    assert(rbm_h03_sensor_foreground(0u, &snapshot) == LFJ8_H03_SENSOR_CLOCK_UNAVAILABLE);
    assert(!rbm_h03_tml0_1mhz_qualified && !rbm_h03_sensor_state.s83.primed);
    set_time(0u);
    assert(!rbm_h03_sensor_clock_rebase(0u));
    arm();
    assert(rbm_h03_sensor_foreground(0u, &snapshot) == LFJ8_H03_SENSOR_SNAPSHOT);
    assert(snapshot.epoch != epoch && !snapshot.atf_valid);
    assert(snapshot.capture.nt.state == LFJ8_VSS_UNAVAILABLE);
    delta[0] = rbm_h03_sensor_config.max_read_span_ticks + 1u;
    assert(rbm_h03_sensor_foreground(0u, &snapshot) == LFJ8_H03_SENSOR_UNALIGNED);
    delta[0] = 0u;

    /* A stall while admitted latches off. Recovery needs an explicit rebase. */
    assert(!probe() && !rbm_h03_tml0_1mhz_qualified);
    delta[0] = delta[1] = 1u;
    assert(probe() && !rbm_h03_tml0_1mhz_qualified);
    assert(rbm_h03_sensor_foreground(0u, &snapshot) == LFJ8_H03_SENSOR_CLOCK_UNAVAILABLE);
    assert(!rbm_h03_bench_raw_capture(NULL, &raw) && !raw.capture && !raw.clock_basis);
    assert(depth == 0u);
}

int main(void)
{
    probe_faults();
    sensor_path();
    puts("PASS H03 bench profile: register changes, stalls, wrap, epochs, S51/S83 and AN1 freshness");
    return 0;
}
