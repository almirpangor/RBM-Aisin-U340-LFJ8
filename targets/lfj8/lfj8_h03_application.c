#include "lfj8_h03_application.h"
#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_sensor_target.h"

#define SERIAL_HALF_RANGE UINT32_C(0x80000000)

static const Lfj8H03ApplicationBinding *const binding = &rbm_h03_application_binding;
static Lfj8H03Application *const app = &rbm_h03_application;

static int owns_ram(const Lfj8RegisterIo *io)
{
    return binding->ram_owned(io->context) == 1;
}

int lfj8_h03_application_running_locked(void)
{
    return owns_ram(binding->takeover_ops->io) && app->running == 1u;
}

static int initialize_engine_locked(const Lfj8RegisterIo *io)
{
    const Lfj8H03ApplicationEngine *const engine = binding->engine;
    if (!engine) {
        return 1;
    }
    const Lfj8H03EngineFeedTarget *const target = &engine->target;
    return target->io == io && target->rx && target->qualifier && target->dtc &&
        target->can_owner && target->now_us && engine->context_for_task2 &&
        lfj8_h03_engine_feed_target_init(target, engine->max_age_ticks, engine->max_poll_gap_us);
}

static void close_gate_locked(const Lfj8RegisterIo *io)
{
    app->running = 0u;
    app->adaptation_status = RBM_U340E_ADAPTATION_INVALID;
    rbm_h03_sensor_clock_rebase(0);
    binding->takeover->ops = NULL;
    binding->takeover->pending = 0u;
    binding->main->valid = 0u;
    binding->runtime->initialized = 0u;
    binding->takeover_ops->inhibit(io->context);
}

void rbm_h03_application_cold_gate(void)
{
    const Lfj8RegisterIo *const io = binding->takeover_ops->io;
    const uint32_t saved = io->enter(io->context);
    if (owns_ram(io)) {
        close_gate_locked(io);
    }
    io->leave(io->context, saved);
}

void rbm_h03_phase_startup_callback(void)
{
    const Lfj8H03TakeoverOps *const ops = binding->takeover_ops;
    const Lfj8RegisterIo *const io = ops->io;
    void *const context = io->context;
    uint32_t saved = io->enter(context);
    const int owned = owns_ram(io);
    if (owned) {
        close_gate_locked(io);
    }
    const int clock_ready = owned && binding->clock_ready && binding->clock_ready(context) == 1;
    io->leave(context, saved);

    if (!clock_ready || !binding->toyota_max_period_ticks ||
        binding->toyota_max_period_ticks >= SERIAL_HALF_RANGE ||
        !binding->initialize || !binding->take_toyota || !binding->service_phase ||
        binding->initialize(context) != 1 ||
        !lfj8_h03_cycle_init(binding->cycle, &binding->startup_range, binding->startup_request_1120) ||
        !rbm_u340e_runtime_init(binding->runtime, binding->startup_gear, binding->startup_gp)) {
        return;
    }

    const FactoryAdaptRead read_adaptation = binding->read_adaptation;
    const uint8_t *slot0 = NULL;
    const uint8_t *slot1 = NULL;
    if (read_adaptation) {
        slot0 = read_adaptation(context, 0u);
        slot1 = read_adaptation(context, 1u);
    }
    const RbmU340eAdaptationResult restored = rbm_u340e_runtime_restore_adaptation(
        binding->runtime, rbm_u340e_s01_adaptation_baseline(), slot0, slot1);
    if (restored == RBM_U340E_ADAPTATION_INVALID) {
        binding->runtime->initialized = 0u;
        return;
    }

    saved = io->enter(context);
    if (owns_ram(io)) {
        if (binding->clock_ready(context) == 1 &&
            initialize_engine_locked(io) &&
            rbm_h03_sensor_clock_rebase(1) &&
            lfj8_h03_phase_startup(binding->takeover, ops, &binding->phase_config)) {
            app->last_toyota_at = ops->phase_clock->latest.released_at;
            app->adaptation_status = (uint8_t)restored;
            app->running = 1u;
        } else {
            rbm_h03_sensor_clock_rebase(0);
            binding->runtime->initialized = 0u;
        }
    }
    io->leave(context, saved);
}

void rbm_h03_phase_release_callback(uint32_t released_at)
{
    const Lfj8H03TakeoverOps *const ops = binding->takeover_ops;
    const Lfj8RegisterIo *const io = ops->io;
    const uint32_t saved = io->enter(io->context);
    if (lfj8_h03_application_running_locked()) {
        lfj8_h03_phase_clock_release(ops->phase_clock, released_at);
    }
    io->leave(io->context, saved);
}

static void fault_locked(void)
{
    app->running = 0u;
    app->adaptation_status = RBM_U340E_ADAPTATION_INVALID;
    rbm_h03_sensor_clock_rebase(0);
    binding->takeover_ops->phase_clock->faulted = 1u;
    binding->cycle->faulted = 1u;
    binding->runtime->initialized = 0u;
    binding->main->valid = 0u;
    lfj8_h03_takeover_revoke_locked(binding->takeover);
}

static Lfj8H03PhaseResult check_locked(Lfj8H03PhaseEvent *event)
{
    if (!lfj8_h03_application_running_locked()) {
        return LFJ8_H03_PHASE_FAULT;
    }
    const Lfj8H03TakeoverOps *const ops = binding->takeover_ops;
    void *const context = ops->io->context;
    const uint32_t now = ops->clock_ticks(context);
    if (rbm_h03_tml0_1mhz_qualified != 1u || binding->clock_ready(context) != 1 ||
        now - app->last_toyota_at > binding->toyota_max_period_ticks) {
        fault_locked();
        return LFJ8_H03_PHASE_FAULT;
    }
    const Lfj8H03PhaseResult status = event
        ? lfj8_h03_phase_clock_take(ops->phase_clock, now, event)
        : lfj8_h03_phase_clock_check(ops->phase_clock, now);
    if (status == LFJ8_H03_PHASE_FAULT) {
        fault_locked();
    }
    return status;
}

void rbm_h03_phase_wait_callback(void)
{
    const Lfj8RegisterIo *const io = binding->takeover_ops->io;
    const uint32_t saved = io->enter(io->context);
    check_locked(NULL);
    io->leave(io->context, saved);
}

static int prepare_engine(const Lfj8H03ApplicationEngine *engine,
                          const Lfj8H03SensorSnapshot *sensors)
{
    const Lfj8RegisterIo *const io = engine->target.io;
    void *const context = io->context;
    Lfj8H03CycleInput *const input = binding->input;
    Ta2005EngineQualificationContext qualified = {0};
    uint32_t oldest_us = 0u;
    bool inhibit_history = true;
    int ready = 0;
    const uint32_t saved = io->enter(context);
    if (lfj8_h03_application_running_locked() &&
        engine->context_for_task2(context, sensors, &qualified, &inhibit_history, &oldest_us) == 1 &&
        qualified.coherent == 1u) {
        const uint32_t now = binding->takeover_ops->clock_ticks(context);
        const uint32_t engine_age = now - oldest_us;
        const uint32_t input_age = now - input->command_at;
        if (engine_age < SERIAL_HALF_RANGE && input_age < SERIAL_HALF_RANGE) {
            const unsigned events = lfj8_h03_engine_feed_target_task2(&engine->target,
                &qualified, inhibit_history, &input->engine, NULL);
            if (engine_age > input_age) {
                input->command_at = oldest_us;
            }
            ready = (events & TA2005_ENGINE_EVALUATED) != 0u;
        }
    }
    io->leave(context, saved);
    return ready;
}

static Lfj8H03CycleResult run_toyota(void *context, const Lfj8H03SensorSnapshot *sensors)
{
    Lfj8H03CycleLoad load = {0};
    uint32_t released_at = app->last_toyota_at;
    const Lfj8H03ToyotaEvent result = binding->take_toyota(
        context, sensors, binding->input, &load, &released_at);
    if (result == LFJ8_H03_TOYOTA_WAIT) {
        return LFJ8_H03_CYCLE_NO_MAIN;
    }
    if (result != LFJ8_H03_TOYOTA_EVENT) {
        return LFJ8_H03_CYCLE_FAULT;
    }
    if (binding->cycle->have_event && binding->cycle->last_event == binding->input->event) {
        return released_at == app->last_toyota_at ? LFJ8_H03_CYCLE_NO_MAIN : LFJ8_H03_CYCLE_FAULT;
    }
    const uint32_t now = binding->takeover_ops->clock_ticks(context);
    const uint32_t interval = released_at - app->last_toyota_at;
    if (!interval || interval > binding->toyota_max_period_ticks ||
        now - released_at > binding->toyota_max_period_ticks) {
        return LFJ8_H03_CYCLE_FAULT;
    }
    if (binding->engine &&
        ((binding->cycle->have_event && binding->input->event != binding->cycle->last_event + 1u) ||
         binding->input->qualified != 1u || !prepare_engine(binding->engine, sensors))) {
        return LFJ8_H03_CYCLE_FAULT;
    }
    const Lfj8H03CycleResult status = lfj8_h03_cycle_tick_with_load(
        binding->cycle, binding->runtime, binding->input, binding->workspace, binding->main, load);
    if (status != LFJ8_H03_CYCLE_FAULT) {
        app->last_toyota_at = released_at;
    }
    return status;
}

void rbm_h03_application_foreground_callback(void)
{
    const Lfj8H03TakeoverOps *const ops = binding->takeover_ops;
    const Lfj8RegisterIo *const io = ops->io;
    void *const context = io->context;
    Lfj8H03PhaseEvent phase;
    Lfj8H03SensorSnapshot sensors;
    uint32_t saved = io->enter(context);
    const Lfj8H03PhaseResult status = check_locked(&phase);
    if (status != LFJ8_H03_PHASE_EVENT) {
        io->leave(context, saved);
        return;
    }
    /* No independent standstill input is bound yet. An absent pulse is not zero speed. */
    if (rbm_h03_sensor_foreground(0, &sensors) != LFJ8_H03_SENSOR_SNAPSHOT) {
        fault_locked();
        io->leave(context, saved);
        return;
    }
    if (binding->engine) {
        lfj8_h03_engine_feed_target_poll(&binding->engine->target);
    }
    io->leave(context, saved);

    const Lfj8H03CycleResult result = run_toyota(context, &sensors);
    saved = io->enter(context);
    if (lfj8_h03_application_running_locked() &&
        (result == LFJ8_H03_CYCLE_FAULT || ops->phase_clock->latest.sequence != phase.sequence)) {
        fault_locked();
    }
    const int running = check_locked(NULL) != LFJ8_H03_PHASE_FAULT;
    io->leave(context, saved);
    if (running) {
        binding->service_phase(context, &phase, &sensors,
                               result == LFJ8_H03_CYCLE_MAIN ? binding->main : NULL);
    }
}
