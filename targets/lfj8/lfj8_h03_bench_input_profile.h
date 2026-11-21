#ifndef RBM_LFJ8_H03_BENCH_INPUT_PROFILE_H
#define RBM_LFJ8_H03_BENCH_INPUT_PROFILE_H

#include "lfj8_h03_bench_input.h"

/* Name the objects in the application profile before including this fragment.
 * The startup object, immutable selector profile, proposal and backend
 * workspace are supplied by their respective owners. */
#ifndef RBM_H03_PROFILE_BENCH_INPUT
#error "Name the owned Lfj8H03BenchInputProfile"
#endif
#ifndef RBM_H03_PROFILE_BENCH_INPUT_BINDING
#error "Name the owned Lfj8H03InputBinding"
#endif
#ifndef RBM_H03_PROFILE_BENCH_INPUT_PROPOSAL
#error "Name the owned Lfj8H03InputProposal workspace"
#endif
#ifndef RBM_H03_PROFILE_TOYOTA_INPUT_STARTUP
#error "Name the native selector/button startup configuration"
#endif

static const Lfj8H03ToyotaInputCapture lfj8_h03_bench_capture = {
    .binding = &RBM_H03_PROFILE_BENCH_INPUT_BINDING,
    .proposal = &RBM_H03_PROFILE_BENCH_INPUT_PROPOSAL,
    .platform = (void *)&RBM_H03_PROFILE_BENCH_INPUT,
    .ram_owned = lfj8_h03_bench_input_ram_owned,
    .read = lfj8_h03_bench_input_read,
};
#define RBM_H03_PROFILE_TOYOTA_INPUT_CAPTURE lfj8_h03_bench_capture
#include "lfj8_h03_toyota_input_profile.h"

static inline int lfj8_h03_bench_profile_reset(void)
{
    return lfj8_h03_profile_reset_toyota_inputs() &&
        lfj8_h03_bench_input_reset_locked(&RBM_H03_PROFILE_BENCH_INPUT);
}

static inline int lfj8_h03_bench_profile_capture(void *context, const Lfj8H03SensorSnapshot *sensors,
    uint32_t due_at, Lfj8H03CycleInput *input, Lfj8H03CycleLoad *load)
{
    (void)context;
    return lfj8_h03_bench_input_take(&lfj8_h03_bench_capture, sensors, due_at, input, load);
}

#undef RBM_H03_PROFILE_RESET_TOYOTA_INPUTS
#define RBM_H03_PROFILE_RESET_TOYOTA_INPUTS lfj8_h03_bench_profile_reset
#undef RBM_H03_PROFILE_CAPTURE_TOYOTA
#define RBM_H03_PROFILE_CAPTURE_TOYOTA lfj8_h03_bench_profile_capture

#endif
