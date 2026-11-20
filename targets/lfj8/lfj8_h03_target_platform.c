#include "lfj8_h03_target_platform.h"

#include "lfj8_h03_application_binding.h"
#include "lfj8_h03_mmio.h"

#ifndef RBM_H03_APPLICATION_PROFILE
#error "Define RBM_H03_APPLICATION_PROFILE as an explicit, qualified profile header"
#else
#include RBM_H03_APPLICATION_PROFILE

#define SERIAL_HALF_RANGE UINT32_C(0x80000000)
#define TOYOTA_PERIOD ((uint64_t)(RBM_H03_PROFILE_TOYOTA_PERIOD_TICKS))
#define TOYOTA_LATENESS ((uint64_t)(RBM_H03_PROFILE_TOYOTA_MAX_LATENESS_TICKS))
#define TOYOTA_WATCHDOG ((uint64_t)(RBM_H03_PROFILE_TOYOTA_MAX_PERIOD_TICKS))
_Static_assert(TOYOTA_PERIOD > 0u && TOYOTA_PERIOD < SERIAL_HALF_RANGE &&
               TOYOTA_LATENESS < TOYOTA_PERIOD,
               "Invalid Toyota release timing");
_Static_assert(TOYOTA_WATCHDOG < SERIAL_HALF_RANGE && TOYOTA_WATCHDOG >= TOYOTA_PERIOD + TOYOTA_LATENESS,
               "Toyota release and lateness must fit the application watchdog");

static const Lfj8H03ToyotaSource toyota_source = {
    .release = &rbm_h03_toyota_release_state,
    .application = &rbm_h03_application,
    .period_ticks = RBM_H03_PROFILE_TOYOTA_PERIOD_TICKS,
    .max_lateness_ticks = RBM_H03_PROFILE_TOYOTA_MAX_LATENESS_TICKS,
    .ram_owned = rbm_h03_target_ram_owned,
    .clock_ready = rbm_h03_target_clock_ready,
    .capture = &RBM_H03_PROFILE_CAPTURE_TOYOTA,
};

static int native_io(void *context)
{
    return rbm_h03_target_takeover_ops.io == &lfj8_h03_mmio &&
           rbm_h03_target_takeover_ops.clock_ticks == lfj8_h03_tml0ct_m32r &&
           context == lfj8_h03_mmio.context;
}

static int startup_allowed_locked(void *context)
{
    return rbm_h03_target_ram_owned(context) == 1 &&
           rbm_h03_target_clock_ready(context) == 1 &&
           rbm_h03_application.running == 0u;
}

int rbm_h03_target_initialize(void *context)
{
    if (!native_io(context)) {
        return 0;
    }
    const Lfj8RegisterIo *const io = &lfj8_h03_mmio;
    uint32_t saved = io->enter(context);
    int allowed = startup_allowed_locked(context);
    io->leave(context, saved);
    if (!allowed || RBM_H03_PROFILE_INITIALIZE_INPUTS(context) != 1) {
        return 0;
    }

    saved = io->enter(context);
    allowed = startup_allowed_locked(context);
    if (allowed) {
        lfj8_h03_toyota_source_reset(toyota_source.release);
    }
    io->leave(context, saved);
    return allowed;
}

Lfj8H03ToyotaEvent rbm_h03_target_take_toyota(void *context, const Lfj8H03SensorSnapshot *sensors,
    Lfj8H03CycleInput *input, Lfj8H03CycleLoad *load, uint32_t *released_at)
{
    if (!native_io(context)) {
        return LFJ8_H03_TOYOTA_FAULT;
    }
    /* Native H03 I/O has a NULL context. The source owns its descriptor and
     * passes that same platform context to the clock, RAM and input providers. */
    return lfj8_h03_toyota_source_take((void *)&toyota_source, sensors, input, load, released_at);
}
#endif
