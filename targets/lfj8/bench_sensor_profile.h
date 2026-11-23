#ifndef RBM_LFJ8_H03_BENCH_SENSOR_PROFILE_H
#define RBM_LFJ8_H03_BENCH_SENSOR_PROFILE_H

#include "lfj8_h03_sensor_feed.h"

/* LFJ8-18-9E1C H03 only. The clock scale is inferred from the OEM period
 * conversion and the 32176 clock tree. It needs an independent bench reference. */
#define LFJ8_H03_BENCH_TML_NOMINAL_HZ UINT32_C(1000000)
#define LFJ8_H03_BENCH_CPU_NOMINAL_HZ UINT32_C(40000000)
#define LFJ8_H03_BENCH_TOP10_TICKS UINT32_C(500)
#define LFJ8_H03_BENCH_PHASE_TICKS (10u * LFJ8_H03_BENCH_TOP10_TICKS)
#define LFJ8_H03_BENCH_SWEEP_TICKS (5u * LFJ8_H03_BENCH_PHASE_TICKS)
#define LFJ8_H03_BENCH_S51_TIMEOUT_TICKS UINT32_C(225000)
#define LFJ8_H03_BENCH_S83_TIMEOUT_TICKS UINT32_C(500000)
#define LFJ8_H03_BENCH_ATF_MAX_AGE_US (2u * LFJ8_H03_BENCH_SWEEP_TICKS)
#define LFJ8_H03_BENCH_MAX_READ_SPAN_TICKS LFJ8_H03_BENCH_TOP10_TICKS

enum {
    LFJ8_H03_BENCH_CLOCK_OEM_NOMINAL = 1,
    LFJ8_H03_BENCH_S51_EDGES_NUM = 100,
    LFJ8_H03_BENCH_S51_EDGES_DEN = 22,
};

typedef struct {
    /* Borrows the coherent native snapshot for the lifetime of the caller. */
    const Lfj8CapturePair *capture;
    uint32_t epoch;
    uint32_t nominal_tick_hz;
    uint8_t clock_basis;
    uint8_t s51_edges_num;
    uint8_t s51_edges_den;
} Lfj8H03BenchRawCapture;

/* Startup and foreground callback for the native H03 MMIO context. */
int rbm_h03_target_clock_ready(void *context);

/* The application phase service receives this snapshot after the OEM
 * collection. A valid interval represents one captured edge period. S51
 * differential revolutions/tick = edges_den / (edges_num * interval_ticks).
 * S83 is exported in TML1 ticks/edge until its edges/revolution are known.
 * A zero timestamp can be a wrap. Interpret timestamps with channel state. */
int rbm_h03_bench_raw_capture(const Lfj8H03SensorSnapshot *snapshot,
                             Lfj8H03BenchRawCapture *raw);

#endif
