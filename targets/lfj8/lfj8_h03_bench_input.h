#ifndef RBM_LFJ8_H03_BENCH_INPUT_H
#define RBM_LFJ8_H03_BENCH_INPUT_H

#include "lfj8_h03_input_binding.h"
#include "lfj8_h03_load_raw.h"

typedef struct {
    Lfj8H03RawLoadRx raw;
    RbmU340eQualifiedLoadFeed load;
    RbmU340eInput driver;
    Lfj8H03RangeInputs range;
} Lfj8H03BenchInputState;

typedef struct {
    Lfj8H03BenchInputState *state; /* Owned RAM, disjoint from cycle/proposal. */
    const Lfj8H03RawLoadConfig *raw_config;
    uint32_t driver_max_age_us;
    /* Called with the H03 IRQ exclusion held. Return 1 only with measured or
     * donor-qualified sources. Driver supplies the observation, shift state
     * and gear mask. Range contains independently timestamped interlocks. */
    int (*read_local)(const Lfj8H03SensorSnapshot *sensors, uint32_t now_us,
        RbmU340eInput *driver, Lfj8H03RangeInputs *range, uint32_t *driver_at);
    /* Supply all eight signed S01 operands and GP-5299.1, or refuse. Set
     * sampled_at earlier if the conversion used earlier qualified history. */
    int (*project_load)(const Lfj8H03RawLoadSample *raw, RbmU340eQualifiedLoadFeed *out);
} Lfj8H03BenchInputProfile;

/* Run in the closed application startup, under native IRQ exclusion. */
int lfj8_h03_bench_input_reset_locked(const Lfj8H03BenchInputProfile *profile);

/* From the stable, ordered BasicCAN copy before the OEM acknowledgement.
 * Reuse the dispatcher clock pair and its ownership/residence guards. */
Lfj8H03RawLoadResult lfj8_h03_bench_input_rx_locked(
    const Lfj8H03BenchInputProfile *profile, const uint8_t slot[16], uint32_t now_us,
    uint16_t can_now);

/* Gate release startup while BasicCAN/the first complete sample are acquiring.
 * Call under the native IRQ lock. Actual capture rechecks all operands. */
int lfj8_h03_bench_input_load_ready_locked(const Lfj8H03BenchInputProfile *profile);

/* Use as the native capture descriptor callbacks. Read runs under the
 * exclusion taken by lfj8_h03_bench_input_take. */
int lfj8_h03_bench_input_ram_owned(void *context);
int lfj8_h03_bench_input_read(void *context, const Lfj8H03SensorSnapshot *sensors,
    uint32_t due_at, Lfj8H03CycleInput *input, Lfj8H03CycleLoad *load, Lfj8H03InputSources *sources);
int lfj8_h03_bench_input_take(const Lfj8H03ToyotaInputCapture *capture,
    const Lfj8H03SensorSnapshot *sensors, uint32_t due_at,
    Lfj8H03CycleInput *input, Lfj8H03CycleLoad *load);

#endif
