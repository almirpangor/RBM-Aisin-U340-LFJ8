#ifndef RBM_LFJ8_H03_BENCH_OUTPUT_PROFILE_H
#define RBM_LFJ8_H03_BENCH_OUTPUT_PROFILE_H

#include "h03_native_hooks.h"
#include "lfj8_h03_takeover.h"

/* Compile lfj8_h03_bench_outputs.c for this profile and leave both
 * RBM_H03_PROFILE_OUTPUT_* macros used by application_binding.c unset.
 * Alias this clock to control.phase_clock. Do not allocate a second clock. */
extern volatile Lfj8H03PhaseClock rbm_h03_bench_phase_clock;

/* In this profile only, wire the phase 3 strategy callback at 0x036F30 to
 * rbm_h03_commit_callback as well. Both phases then use the same native,
 * ownership-checked revoke. Dropping the ordinary OEM calls requires both
 * redirects; this header does not change either call site. */

typedef struct {
    uint32_t captured_at;              /* Native TML0 ticks, capture time */
    uint16_t pressure_sense_counts;    /* ADC0/AN3 raw 10-bit count, sample age unknown */
    uint16_t pressure_reload1;         /* TIO4 timer counts */
    uint16_t pressure_reload0;
    uint16_t tio9_reload1;             /* TIO9 timer counts */
    uint16_t tio9_reload0;
    uint8_t shift_p3;                  /* D/E/F latch bits 7/6/5 */
    uint8_t shift_feedback_p13;        /* D/E/F monitor bits 3/2/1 */
    uint8_t pressure_control;          /* bit 0: P107 latch, bit 1: P107 mux */
    uint8_t tio9_control;              /* bit 0: P97 latch, bit 1: P97 mux */
} Lfj8H03BenchOutputSnapshot;

/* Capture observable registers for a diagnostic consumer. Foreground may call
 * this with a caller-owned buffer. A false return leaves that buffer untouched.
 * ADC results are monitor input only, with no conversion to current or pressure.
 * An IRQ lock excludes firmware writers; timer and ADC hardware still run. */
int lfj8_h03_bench_output_snapshot(Lfj8H03BenchOutputSnapshot *snapshot);

#endif
