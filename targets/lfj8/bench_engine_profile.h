#ifndef RBM_LFJ8_BENCH_ENGINE_PROFILE_H
#define RBM_LFJ8_BENCH_ENGINE_PROFILE_H

#include "lfj8_h03_engine_context.h"

/* H03 stock CONF/BRP and the paired S04 diagnostic TX schedule imply a
 * nominal 2 us per CAN bit and attempts every 8 ms (RPM) / 16 ms (ECT).
 * Use two ECT periods and 4 ms arbitration margin at nominal rate.
 * The 3 us upper bound and the 32 us read bracket are bench limits
 * enforced against qualified TML0, subject to post-flash measurement. */
#define RBM_H03_PROFILE_ENGINE_MAX_AGE_TICKS 18000u
#define RBM_H03_PROFILE_ENGINE_MAX_POLL_GAP_US 10000u
#define RBM_H03_PROFILE_ENGINE_BIT_TIME_US 3u
#define RBM_H03_PROFILE_ENGINE_MAX_CAN_SAMPLE_SPAN_US 32u
#define RBM_H03_PROFILE_ENGINE_CONTEXT rbm_h03_engine_context_for_task2

#endif
