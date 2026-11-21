#include "lfj8_h03_application_binding.h"
#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_output_inhibit.h"
#include "lfj8_h03_target_service.h"
#include "lfj8_selector_adc.h"

#ifndef RBM_H03_APPLICATION_PROFILE
#error "Define RBM_H03_APPLICATION_PROFILE as an explicit, qualified profile header"
#else
#include RBM_H03_APPLICATION_PROFILE

#if defined(RBM_H03_PROFILE_OUTPUT_ISOLATION_MASK) || defined(RBM_H03_PROFILE_OUTPUT_PHASE_CLOCK)
#if !defined(RBM_H03_PROFILE_OUTPUT_ISOLATION_MASK) || !defined(RBM_H03_PROFILE_OUTPUT_PHASE_CLOCK)
#error "Native H03 output operations require both the isolation mask and owned phase clock"
#else
/* This profile opts into the commissioned H03 D/E/F and Pressure A path.
 * The mask attests wiring isolation, including TIO9/P97, which stock apply
 * can drive independently and which the software inhibit does not touch. */
_Static_assert(RBM_H03_PROFILE_OUTPUT_ISOLATION_MASK == LFJ8_H03_ALL_SPARE_PWM_ISOLATED,
               "Native H03 outputs require all spare drivers isolated");

static void output_write32(void *context, uint32_t address, uint32_t value)
{
    (void)context;
    *(volatile uint32_t *)(uintptr_t)address = value;
}

static int output_qualified(void *context)
{
    (void)context;
    return lfj8_h03_application_running_locked() &&
        rbm_h03_tml0_1mhz_qualified == 1u && lfj8_h03_sensor_clock_registers_match();
}

static void output_arbitrate(void *context)
{
    (void)context;
    ((void (*)(void))(uintptr_t)UINT32_C(0x0717B8))();
}

static void output_apply(void *context)
{
    (void)context;
    ((void (*)(void))(uintptr_t)UINT32_C(0x046900))();
}

const Lfj8H03TakeoverOps rbm_h03_target_takeover_ops = {
    .io = &lfj8_h03_mmio,
    .write32 = output_write32,
    .clock_ticks = lfj8_h03_tml0ct_m32r,
    .qualified = output_qualified,
    .arbitrate = output_arbitrate,
    .apply = output_apply,
    .inhibit = lfj8_h03_output_inhibit_locked,
    .isolated_pwm_mask = RBM_H03_PROFILE_OUTPUT_ISOLATION_MASK,
    .phase_clock = &RBM_H03_PROFILE_OUTPUT_PHASE_CLOCK,
};
#endif
#endif

static int initialize_target(void *context)
{
    const Lfj8RegisterIo *const io = rbm_h03_target_takeover_ops.io;
    const uint32_t saved = io->enter(context);
    const int owned = rbm_h03_target_ram_owned(context) == 1;
    if (owned) {
        lfj8_selector_adc_init(&rbm_h03_selector_adc_state);
    }
    io->leave(context, saved);
    return owned ? rbm_h03_target_initialize(context) : RBM_U340E_STARTUP_UNQUALIFIED;
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
    .engine = &rbm_h03_target_engine,
    .ram_owned = rbm_h03_target_ram_owned,
    .clock_ready = rbm_h03_target_clock_ready,
    .initialize = initialize_target,
#ifdef RBM_H03_PROFILE_CAN_SERVICE_CONFIG
    .stop_service_locked = lfj8_h03_target_service_stop_locked,
#endif
    .read_adaptation = RBM_H03_PROFILE_READ_ADAPTATION,
    .take_toyota = rbm_h03_target_take_toyota,
    .service_phase = rbm_h03_target_service_phase,
};
#endif
