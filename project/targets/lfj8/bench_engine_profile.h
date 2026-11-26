#ifndef RBM_LFJ8_BENCH_ENGINE_PROFILE_H
#define RBM_LFJ8_BENCH_ENGINE_PROFILE_H

#include "lfj8_h03_engine_context.h"

/* Stock H03 CONF/BRP and the paired S04 TX schedule imply a nominal 2 us
 * CAN bit and attempts every 8 ms (RPM) / 16 ms (ECT). The 18,000-tick raw
 * age is two ECT periods plus 4 ms arbitration at nominal rate. The
 * 1..3 us bit-time range and 32 us read bracket are engineering bounds,
 * enforced against qualified TML0; none is a hardware measurement. */
#define RBM_H03_PROFILE_ENGINE_MAX_AGE_TICKS 18000u
#define RBM_H03_PROFILE_ENGINE_MAX_POLL_GAP_US 10000u
#define RBM_H03_PROFILE_ENGINE_BIT_TIME_US 3u
#define RBM_H03_PROFILE_ENGINE_MAX_CAN_SAMPLE_SPAN_US 32u
#define RBM_H03_PROFILE_ENGINE_CONTEXT rbm_h03_engine_context_for_task2

#endif
