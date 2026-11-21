#ifndef RBM_LFJ8_H03_BENCH_DIAG_H
#define RBM_LFJ8_H03_BENCH_DIAG_H

#include "chery_dtc_link.h"

/* Bench-only readout under the existing CAN13 interrupt lock.
 * The strong implementation uses the same typed application objects.
 * The default target provider returns zero for every page. */
size_t lfj8_h03_bench_diag_read(const CheryDtcState *state, uint8_t page,
                              uint32_t words[CHERY_DTC_READOUT_MAX_WORDS]);

#endif
