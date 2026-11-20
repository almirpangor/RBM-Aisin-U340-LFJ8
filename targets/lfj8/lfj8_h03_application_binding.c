#include "lfj8_h03_application_binding.h"
#include "lfj8_selector_adc.h"

#ifndef RBM_H03_APPLICATION_PROFILE
#error "Define RBM_H03_APPLICATION_PROFILE as an explicit, qualified profile header"
#else
#include RBM_H03_APPLICATION_PROFILE

static int initialize_target(void *context)
{
    const Lfj8RegisterIo *const io = rbm_h03_target_takeover_ops.io;
    const uint32_t saved = io->enter(context);
    const int owned = rbm_h03_target_ram_owned(context) == 1;
    if (owned) {
        lfj8_selector_adc_init(&rbm_h03_selector_adc_state);
    }
    io->leave(context, saved);
    return owned && rbm_h03_target_initialize(context) == 1;
}

const Lfj8H03ApplicationBinding rbm_h03_application_binding = {
    .takeover_ops = &rbm_h03_target_takeover_ops,
    .phase_config = RBM_H03_PROFILE_PHASE_CONFIG,
    .takeover = &rbm_h03_takeover_state,
    .cycle = &rbm_h03_cycle_state,
    .runtime = &rbm_h03_runtime_state,
    .workspace = &rbm_h03_cycle_workspace,
    .main = &rbm_h03_main_result,
    .input = &rbm_h03_cycle_input,
    .startup_gear = &rbm_h03_target_startup_gear,
    .startup_gp = &rbm_h03_target_startup_gp,
    .startup_range = RBM_H03_PROFILE_STARTUP_RANGE,
    .toyota_max_period_ticks = RBM_H03_PROFILE_TOYOTA_MAX_PERIOD_TICKS,
    .startup_request_1120 = RBM_H03_PROFILE_STARTUP_REQUEST_1120,
    .ram_owned = rbm_h03_target_ram_owned,
    .clock_ready = rbm_h03_target_clock_ready,
    .initialize = initialize_target,
    .read_adaptation = RBM_H03_PROFILE_READ_ADAPTATION,
    .take_toyota = rbm_h03_target_take_toyota,
    .service_phase = rbm_h03_target_service_phase,
};
#endif
