/* Native providers for the first H03 bench image. Link instead of the
 * measurement-backed providers emitted by check_h03_sensor_config.py. */
#include "bench_sensor_profile.h"
#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_sensor_target.h"

#define TML0CT UINT32_C(0x8003E0)
#define TML1CT UINT32_C(0x800FE0)
#define SERIAL_HALF_RANGE UINT32_C(0x80000000)
#define PROGRESS_POLLS (LFJ8_H03_BENCH_CPU_NOMINAL_HZ / LFJ8_H03_BENCH_TML_NOMINAL_HZ)

_Static_assert(LFJ8_H03_BENCH_MAX_READ_SPAN_TICKS <= UINT16_MAX, "Capture bracket is uint16_t");

const Lfj8H03SensorFeedConfig rbm_h03_sensor_config = {
    .s51_timeout_ticks = LFJ8_H03_BENCH_S51_TIMEOUT_TICKS,
    .s83_timeout_ticks = LFJ8_H03_BENCH_S83_TIMEOUT_TICKS,
    .atf_max_age_us = LFJ8_H03_BENCH_ATF_MAX_AGE_US,
    .max_read_span_ticks = LFJ8_H03_BENCH_MAX_READ_SPAN_TICKS,
};

/* Called under the platform interrupt lock, both before opening an epoch
 * and from the phase wait/foreground path. Sampling both counters detects
 * a joint stall that a relative offset check alone cannot see. At the
 * nominal clock ratio one tick takes 40 CPU clocks. Each poll executes
 * several instructions, so 40 polls also cover the worst initial phase.
 * This finite loop checks progress only. Sensor foreground checks relative
 * continuity and the application owns epoch creation and phase timing. */
int rbm_h03_target_clock_ready(void *context)
{
    const Lfj8RegisterIo *const io = &lfj8_h03_mmio;
    if (context != io->context) {
        return 0;
    }
    if (lfj8_h03_sensor_clock_registers_match()) {
        const uint32_t start0 = io->read32(context, TML0CT);
        const uint32_t start1 = io->read32(context, TML1CT);
        for (unsigned remaining = PROGRESS_POLLS; remaining != 0u; --remaining) {
            const uint32_t elapsed0 = io->read32(context, TML0CT) - start0;
            const uint32_t elapsed1 = io->read32(context, TML1CT) - start1;
            if ((elapsed0 | elapsed1) >= SERIAL_HALF_RANGE) {
                break;
            }
            if (elapsed0 && elapsed1) {
                if (lfj8_h03_sensor_clock_registers_match()) {
                    return 1;
                }
                break;
            }
        }
    }
    rbm_h03_tml0_1mhz_qualified = 0u;
    return 0;
}

int rbm_h03_bench_raw_capture(const Lfj8H03SensorSnapshot *snapshot, Lfj8H03BenchRawCapture *raw)
{
    if (!raw) {
        return 0;
    }
    if (!snapshot) {
        *raw = (Lfj8H03BenchRawCapture){0};
        return 0;
    }
    *raw = (Lfj8H03BenchRawCapture){
        .capture = &snapshot->capture,
        .epoch = snapshot->epoch,
        .nominal_tick_hz = LFJ8_H03_BENCH_TML_NOMINAL_HZ,
        .clock_basis = LFJ8_H03_BENCH_CLOCK_OEM_NOMINAL,
        .s51_edges_num = LFJ8_H03_BENCH_S51_EDGES_NUM,
        .s51_edges_den = LFJ8_H03_BENCH_S51_EDGES_DEN,
    };
    return 1;
}
