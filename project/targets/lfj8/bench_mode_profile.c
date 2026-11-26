#include "bench_mode_profile.h"

enum {
    /* H03 TOP10: ten 0.5 ms interrupts per nominal AN2 foreground cycle. */
    H03_NOMINAL_SAMPLE_US = 5000u,
    /* Admit one sample interval plus less than one interval of lateness. */
    BENCH_INPUT_MAX_AGE_US = 2u * H03_NOMINAL_SAMPLE_US,
    /* Engineering debounce: four full nominal intervals at a stable level. */
    BENCH_BUTTON_DEBOUNCE_US = 4u * H03_NOMINAL_SAMPLE_US,
};

const RbmU340eSelectorProfile lfj8_h03_bench_selector = {
    /* 10-bit AN2, [lower, upper) on the H03 raw × 5/1024 scale.
     * P/R/N/D follow the OEM classification. Keep the separate lower
     * S/L windows identified in ROM for the added 2/L resistors. */
    .windows = {{889u, 980u}, {784u, 857u}, {624u, 717u}, {456u, 544u}, {301u, 377u}, {164u, 224u}},
    .stable_samples = 4u, /* OEM four-observation history at 0x034D14. */
};

const Lfj8H03InputStartup lfj8_h03_bench_selector_startup = {
    .policy = {.initial_mode = RBM_U340E_AUTO, .initial_overdrive_enabled = 1u},
    .selector_max_age_us = BENCH_INPUT_MAX_AGE_US,
    .button_debounce_us = BENCH_BUTTON_DEBOUNCE_US,
    .button_max_age_us = BENCH_INPUT_MAX_AGE_US,
};

const Lfj8H03InputStartup lfj8_h03_bench_manual_startup = {
    .policy = {
        .manual_selectors = 1u << RBM_U340E_SELECTOR_D,
        .overdrive_limit_modes = RBM_U340E_OVERDRIVE_TIPTRONIC,
        .initial_mode = RBM_U340E_AUTO,
        .initial_overdrive_enabled = 1u,
    },
    .selector_max_age_us = BENCH_INPUT_MAX_AGE_US,
    .button_debounce_us = BENCH_BUTTON_DEBOUNCE_US,
    .button_max_age_us = BENCH_INPUT_MAX_AGE_US,
};
