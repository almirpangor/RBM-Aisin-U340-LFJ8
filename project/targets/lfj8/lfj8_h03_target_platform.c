#include "lfj8_h03_target_platform.h"

#include "lfj8_h03_application_binding.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_target_service.h"

#ifndef RBM_H03_APPLICATION_PROFILE
#error "Define RBM_H03_APPLICATION_PROFILE as an explicit, qualified profile header"
#else
#include RBM_H03_APPLICATION_PROFILE
#ifndef RBM_H03_PROFILE_CAN_SERVICE_CONFIG
#error "Define RBM_H03_PROFILE_CAN_SERVICE_CONFIG as an explicit, qualified CAN service object"
#endif
#if defined(RBM_H03_PROFILE_TOYOTA_INPUT_STARTUP) && !defined(RBM_H03_PROFILE_RESET_TOYOTA_INPUTS)
#error "Include lfj8_h03_toyota_input_profile.h after defining the native input startup profile"
#endif

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
        return RBM_U340E_STARTUP_UNQUALIFIED;
    }
    const Lfj8RegisterIo *const io = &lfj8_h03_mmio;
    uint32_t saved = io->enter(context);
    int allowed = startup_allowed_locked(context);
    io->leave(context, saved);
    if (!allowed) {
        return RBM_U340E_STARTUP_UNQUALIFIED;
    }
    const int kind = RBM_H03_PROFILE_INITIALIZE_INPUTS(context);
    if (kind != RBM_U340E_STARTUP_PREPARED && kind != RBM_U340E_STARTUP_S01_COLD) {
        return RBM_U340E_STARTUP_UNQUALIFIED;
    }

    saved = io->enter(context);
    allowed = startup_allowed_locked(context);
#ifdef RBM_H03_PROFILE_RESET_TOYOTA_INPUTS
    if (allowed) {
        allowed = RBM_H03_PROFILE_RESET_TOYOTA_INPUTS();
    }
#endif
    if (allowed &&
        lfj8_h03_target_service_prepare_locked(&RBM_H03_PROFILE_CAN_SERVICE_CONFIG)) {
        lfj8_h03_toyota_source_reset(toyota_source.release);
    } else {
        allowed = 0;
    }
    io->leave(context, saved);
    return allowed ? kind : RBM_U340E_STARTUP_UNQUALIFIED;
}

Lfj8H03ToyotaEvent rbm_h03_target_take_toyota(void *context, const Lfj8H03SensorSnapshot *sensors,
    Lfj8H03CycleInput *input, Lfj8H03CycleLoad *load, uint32_t *released_at)
{
    if (!native_io(context) || !input) {
        return LFJ8_H03_TOYOTA_FAULT;
    }
#ifdef RBM_H03_PROFILE_SAMPLE_TOYOTA_INPUTS
    const Lfj8RegisterIo *const io = &lfj8_h03_mmio;
    const uint32_t saved = io->enter(context);
    const int ready = lfj8_h03_application_running_locked() && rbm_h03_target_clock_ready(context) == 1;
    if (ready) {
        const uint32_t now = lfj8_h03_tml0ct_m32r(context);
        const int have_event = rbm_h03_cycle_state.have_event;
        const uint8_t previous_gear = have_event ? input->requested_gear : 0u;
        if (!RBM_H03_PROFILE_SAMPLE_TOYOTA_INPUTS(now, previous_gear) && have_event) {
            /* Withdraw any old command while the selector/buttons settle.
             * The capture callback decides admission on the next release. */
            input->requested_gear = 0u;
            rbm_h03_main_result.valid = 0u;
            lfj8_h03_takeover_revoke_locked(&rbm_h03_takeover_state);
        }
    }
    io->leave(context, saved);
    if (!ready) {
        return LFJ8_H03_TOYOTA_FAULT;
    }
#endif
    /* Native H03 I/O has a NULL context. The source owns its descriptor and
     * passes that same platform context to the clock, RAM and input providers. */
    return lfj8_h03_toyota_source_take((void *)&toyota_source, sensors, input, load, released_at);
}
#endif
