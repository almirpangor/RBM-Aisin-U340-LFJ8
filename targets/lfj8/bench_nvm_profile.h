#ifndef RBM_LFJ8_H03_BENCH_NVM_PROFILE_H
#define RBM_LFJ8_H03_BENCH_NVM_PROFILE_H

#include <stddef.h>
#include "lfj8_h03_nvm_native.h"

/* First bench profile: no exclusively assigned UFL1 or DTC erase blocks.
 * The real startup uses its S01 baseline with no adaptation reader.
 * Keep the native DTC broker's durable-clear requirement enabled. Inspect
 * with lfj8_h03_nvm_native_bench_status / lfj8_h03_nvm_native_bench_inspect. */
#ifdef RBM_H03_PROFILE_READ_ADAPTATION
#error "The H03 no-media bench profile cannot supply an adaptation reader"
#endif
#define RBM_H03_PROFILE_READ_ADAPTATION NULL

/* The platform calls this once on a cold start, after acquiring the DTC
 * RAM and before starting any producer. CAN/TML0 rebinds preserve RAM. */
#define RBM_H03_BENCH_NVM_DTC_COLD_INIT chery_dtc_init

#endif
