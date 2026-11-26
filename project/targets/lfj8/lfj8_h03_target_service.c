#include "lfj8_h03_target_service.h"
#include "lfj8_h03_application_binding.h"
#include "lfj8_h03_atf_feed.h"
#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_can_monitor_startup.h"
#include "lfj8_h03_can_owner.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_sensor_target.h"

/* Aliases of communication/ and workspace/ fields in lfj8_h03_storage.h. */
extern Lfj8H03TargetService rbm_h03_can_service;
extern Lfj8H03DtcTarget rbm_h03_dtc_target;
extern Lfj8H03Can13 rbm_h03_can13;
extern Lfj8H03Can13Input rbm_h03_can13_input;
extern Lfj8CheryTxInputs rbm_h03_tx_input;
extern Lfj8TorqueInput rbm_h03_torque_input;

extern void h03_can13_tx_gate(void);
extern void rbm_h03_dtc_rx_hook(void);
extern void rbm_h03_dtc_rx_dispatch_hook(void);

static const Lfj8RegisterIo *const io = &lfj8_h03_mmio;

static bool redirect_installed(uint32_t site, void (*hook)(void), uint32_t opcode)
{
    const uint32_t target = (uint32_t)(uintptr_t)hook;
    const uint32_t offset = ((target - site) / 4u) & UINT32_C(0x00ffffff);
    return target % 4u == 0u && io->read32(io->context, site) == (opcode | offset);
}

static bool can_redirects_installed(void)
{
    return redirect_installed(0x00c34cu, h03_can13_tx_gate, 0xff000000u) &&
        redirect_installed(0x001534u, rbm_h03_dtc_rx_hook, 0xff000000u) &&
        redirect_installed(0x004738u, rbm_h03_dtc_rx_dispatch_hook, 0xfe000000u);
}

void lfj8_h03_target_service_stop_locked(void)
{
    lfj8_h03_dtc_native_unbind();
    rbm_h03_can_monitor_retire_tx13_locked();
    rbm_h03_can_service = (Lfj8H03TargetService){.config = NULL};
}

bool lfj8_h03_target_service_prepare_locked(const Lfj8H03TargetServiceConfig *config)
{
    if (h03_can_owner.grant) {
        return false;
    }
    lfj8_h03_target_service_stop_locked();
    const Lfj8H03ApplicationEngine *const engine = rbm_h03_application_binding.engine;
    /* Reject an unusable profile before the platform opens the phase gate.
     * Dynamic clock qualification and IRQ binding still run in start_locked. */
    if (!config || !lfj8_h03_dtc_t6_config_valid(&config->t6) ||
        !lfj8_h03_dtc_rx_clock_span_valid(config->max_clock_span_us,
            config->can13.diagnostic_receive_age_bits, config->can13.bit_time_us) ||
        (config->atf_diagnostic && !lfj8_h03_dtc_atf_config_valid(config->atf_diagnostic)) ||
        (config->status_from_t6 && (config->can13.period_1ae_us || config->can13.period_300_us)) ||
        !can_redirects_installed() || !h03_can_owner.initialized ||
        !engine || !engine->target.dtc || engine->target.io != io ||
        engine->target.can_owner != &h03_can_owner ||
        engine->target.now_us != rbm_h03_atf_now_us ||
        !lfj8_h03_can13_init(&rbm_h03_can13, &config->can13, 0u)) {
        return false;
    }
    rbm_h03_can_service.config = config;
    rbm_h03_can_service.start_pending = true;
    return true;
}

static bool start_locked(Lfj8H03TargetService *service, uint32_t sensor_epoch)
{
    const Lfj8H03TargetServiceConfig *const config = service->config;
    service->start_pending = false;
    service->sensor_epoch = sensor_epoch;
    if (!lfj8_h03_dtc_native_start_t6(&service->t6, &config->t6, config->initial_t6_tick,
                                    config->status_from_t6) ||
        !lfj8_h03_dtc_native_bind(&rbm_h03_dtc_target, &rbm_h03_can13, config->max_clock_span_us) ||
        (config->atf_diagnostic &&
         !lfj8_h03_dtc_target_enable_atf(&rbm_h03_dtc_target, config->atf_diagnostic))) {
        lfj8_h03_target_service_stop_locked();
        return false;
    }
    return true;
}

static void prepare_inputs(void *context, const Lfj8H03TargetServiceConfig *config,
                           const Lfj8H03SensorSnapshot *sensors, const Lfj8H03MainResult *main,
                           uint32_t now, Lfj8H03Can13Input *input)
{
    if (config->status) {
        Lfj8CheryTxInputs *const status = &rbm_h03_tx_input;
        *status = (Lfj8CheryTxInputs){.s51_capture = NULL};
        if (config->status(context, sensors, main, status)) {
            status->s51_capture = &sensors->capture;
            status->stopped = 0u;
            lfj8_h03_atf_feed(sensors->atf_valid == 1u ? &sensors->atf : NULL,
                              now, rbm_h03_sensor_config.atf_max_age_us, NULL, NULL, status);
            input->vehicle = config->vehicle;
            input->status = status;
        }
    }
    if (config->torque && config->torque_calibration) {
        Lfj8TorqueInput *const torque = &rbm_h03_torque_input;
        *torque = (Lfj8TorqueInput){.permitted = false};
        if (config->torque(context, sensors, main, torque)) {
            input->torque = torque;
        }
    }
}

void rbm_h03_target_service_phase(void *context, const Lfj8H03PhaseEvent *phase,
    const Lfj8H03SensorSnapshot *sensors, const Lfj8H03MainResult *main)
{
    const uint32_t saved = io->enter(io->context);
    if (!lfj8_h03_application_running_locked()) {
        io->leave(io->context, saved);
        return;
    }

    Lfj8H03TargetService *const service = &rbm_h03_can_service;
    const Lfj8H03TargetServiceConfig *const config = service->config;
    const uint32_t sensor_epoch = rbm_h03_sensor_state.feed.epoch;
    const bool clock_ready = lfj8_h03_sensor_clock_ready_locked() == 1;
    const bool same_epoch = clock_ready && sensors && sensors->epoch == sensor_epoch;
    if (!config || (service->start_pending && (!same_epoch || !start_locked(service, sensor_epoch)))) {
        io->leave(io->context, saved);
        return;
    }
    if (!clock_ready || service->sensor_epoch != sensor_epoch) {
        /* An old clock epoch cannot timestamp RX or update live DTC state. */
        lfj8_h03_target_service_stop_locked();
        io->leave(io->context, saved);
        return;
    }

    Lfj8H03Can13Input *const input = &rbm_h03_can13_input;
    *input = (Lfj8H03Can13Input){
        .dtc = rbm_h03_application_binding.engine->target.dtc,
        .torque_calibration = config->torque_calibration,
    };
    const bool ready = h03_can_owner.setup_permitted && same_epoch;
    if (ready) {
        const volatile Lfj8H03PhaseClock *const phase_clock =
            rbm_h03_application_binding.takeover_ops->phase_clock;
        const uint32_t now = lfj8_h03_tml0ct_m32r(io->context);
        if (phase && !phase_clock->faulted && phase_clock->consumed == phase->sequence &&
            phase_clock->latest.sequence == phase->sequence &&
            now - phase->released_at <= phase_clock->max_age) {
            prepare_inputs(context, config, sensors, main && main->valid ? main : NULL, now, input);
        }
    }
    lfj8_h03_dtc_native_poll_t6(&rbm_h03_dtc_target, input, ready, &service->t6);
    rbm_h03_can_monitor_retire_tx13_locked();
    if (input->status) {
        rbm_h03_tx_input.s51_capture = NULL;
    }
    input->status = NULL;
    input->torque = NULL;
    io->leave(io->context, saved);
}
