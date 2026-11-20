#include "lfj8_h03_cycle.h"

#include "rbm_u340e.h"
#include "rbm_u340e_hydraulic_workspace.h"

int lfj8_h03_cycle_init(Lfj8H03Cycle *cycle, const RbmU340eRangeState *range,
                         uint8_t initial_request_1120)
{
    if (!cycle || !range || range->mode_1114 > 1u) {
        return 0;
    }
    *cycle = (Lfj8H03Cycle){.range = *range, .request_1120 = initial_request_1120};
    rbm_u340e_schedule_finish_init(&cycle->scheduler);
    return 1;
}

static int fast_step(Lfj8H03Cycle *cycle, RbmU340eRuntime *runtime,
                     const RbmU340eRangeInputs *range)
{
    RbmU340eScheduler *schedule = &cycle->scheduler;
    return rbm_u340e_schedule_fast_claim(schedule) &&
        rbm_u340e_schedule_fast_begin(schedule, &runtime->gp) &&
        rbm_u340e_range_fast(&cycle->range, range) &&
        factory_hydraulics_fast_learning(&runtime->gp) &&
        rbm_u340e_schedule_fast_end(schedule, &runtime->gp) &&
        rbm_u340e_schedule_fast_done(schedule);
}

static int main_step(Lfj8H03Cycle *cycle, RbmU340eRuntime *runtime,
                     const Lfj8H03CycleInput *input, const RbmU340eRangeInputs *range,
                     Lfj8H03CycleWorkspace *work, Lfj8H03MainResult *result)
{
    RbmU340eMainEngineInputs engine;
    if (!rbm_u340e_runtime_prepare_engine(runtime, &input->engine, &engine) ||
        !rbm_u340e_runtime_main_coolant(runtime, &engine)) {
        return 0;
    }
    factory_hydraulics_load_main(&runtime->gp);
    if (!rbm_u340e_runtime_main_engine_speed(runtime, &engine) ||
        !rbm_u340e_runtime_main_range(runtime, &cycle->range, range, &work->gear) ||
        !rbm_u340e_runtime_gears_outputs(runtime, &work->gear, &result->shift)) {
        return 0;
    }
    result->gear_4852 = work->gear.b4852;
    result->gear_4848 = work->gear.b4848;
    if (!rbm_u340e_hydraulics_control_main_workspace(&runtime->gp, &work->hydraulics) ||
        !lfj8_h03_torque_demand(&runtime->gp, &result->torque) ||
        !rbm_u340e_runtime_main_range_complete(runtime) ||
        !rbm_u340e_schedule_main_done(&cycle->scheduler)) {
        return 0;
    }
    result->valid = 1u;
    return 1;
}

static int publish_cycle_load(RbmU340eRuntime *runtime, const Lfj8H03CycleLoad *load,
                              uint32_t *command_at)
{
    const uint32_t input_age = load->now_us - *command_at;
    if (input_age >= UINT32_C(0x80000000) ||
        !rbm_u340e_runtime_publish_load(runtime, load->sample, load->now_us, load->max_age_us)) {
        return 0;
    }
    if (load->now_us - load->sample->sampled_at > input_age) {
        *command_at = load->sample->sampled_at;
    }
    return 1;
}

static int secondary_slu(FactoryHydraulics *gp, uint32_t event, uint32_t command_at,
                         const Lfj8H03CycleLoad *load, const Lfj8H03CycleSlu *slu)
{
    const Lfj8H03SluSnapshot *sample = slu->snapshot;
    const uint32_t cycle_age = load->now_us - command_at;
    if (!sample || sample->qualified != 1u || sample->event != event ||
        cycle_age > load->max_age_us) {
        return 0;
    }
    const uint32_t sample_age = load->now_us - sample->sampled_at;
    if (sample_age > load->max_age_us) {
        return 0;
    }

    uint32_t gear, speed, nt, temperature, flags_4834, flags_4829, timer;
    if (!factory_hydraulics_get(gp, -4852, 1u, &gear) ||
        !factory_hydraulics_get(gp, -7200, 2u, &speed) ||
        !factory_hydraulics_get(gp, -7204, 2u, &nt) ||
        !factory_hydraulics_get(gp, -7184, 2u, &temperature) ||
        !factory_hydraulics_get(gp, -4834, 1u, &flags_4834) ||
        !factory_hydraulics_get(gp, -4829, 1u, &flags_4829) ||
        !factory_hydraulics_get(gp, -4735, 1u, &timer)) {
        return 0;
    }
    Lfj8H03SluBaselineInput baseline = {
        .speed_7200 = (uint16_t)speed, .speed_7204 = (uint16_t)nt, .gear = (uint8_t)gear,
        .base_7054 = sample->base_7054, .trim_7066 = sample->trim_7066,
    };
    for (unsigned i = 0; i < sizeof baseline.learning_4616; ++i) {
        baseline.learning_4616[i] = sample->learning_4616[i];
    }
    const Lfj8H03SluSecondaryInput input = {
        .override_7082 = sample->override_7082, .temperature_7184 = (uint16_t)temperature,
        .offset_7028 = sample->offset_7028, .offset_7030 = sample->offset_7030,
        .flags_1636 = sample->flags_1636, .mode_4505 = sample->mode_4505,
        .selector_4544 = sample->selector_4544, .flags_4834 = (uint8_t)flags_4834,
        .flags_4828 = sample->flags_4828, .flags_4827 = sample->flags_4827,
        .flags_4829 = (uint8_t)flags_4829, .flags_4825 = sample->flags_4825,
        .flags_4822 = sample->flags_4822, .qualified = true,
    };
    Lfj8H03SluSecondaryState state = {slu->state->previous_mode_1637, (uint8_t)timer};
    if (!lfj8_h03_slu_secondary_from_baseline(&input, &baseline, &slu->state->baseline,
                                              &state, &slu->output->result)) {
        return 0;
    }
    /* Timer advancement is owned by the FAST GP bank, even without SLU.
     * SECONDARY writes only the donor reset back to the canonical byte. */
    if (state.timer_4735 != timer && !factory_hydraulics_set(gp, -4735, 1u, state.timer_4735)) {
        return 0;
    }
    slu->state->previous_mode_1637 = state.previous_mode_1637;
    slu->output->event = event;
    slu->output->command_at = sample_age > cycle_age ? sample->sampled_at : command_at;
    return 1;
}

/* The legacy cycle roots must keep linking within their protected flash
 * windows. Only the SLU entry point links the numerical SECONDARY stage. */
typedef int (*SluStage)(FactoryHydraulics *, uint32_t, uint32_t,
                        const Lfj8H03CycleLoad *, const Lfj8H03CycleSlu *);

static Lfj8H03CycleResult cycle_tick(Lfj8H03Cycle *cycle, RbmU340eRuntime *runtime,
    const Lfj8H03CycleInput *input, Lfj8H03CycleWorkspace *work, Lfj8H03MainResult *result,
    const Lfj8H03CycleLoad *load, const Lfj8H03CycleSlu *slu, SluStage run_slu)
{
    if (slu && slu->output) {
        *slu->output = (Lfj8H03SluOutput){0};
    }
    if (!result) {
        return LFJ8_H03_CYCLE_FAULT;
    }
    *result = (Lfj8H03MainResult){0};
    if (!cycle || cycle->faulted || !cycle->scheduler.initialized) {
        return LFJ8_H03_CYCLE_FAULT;
    }
    if (input && cycle->have_event && cycle->last_event == input->event) {
        return LFJ8_H03_CYCLE_NO_MAIN;
    }
    if (!runtime || runtime->initialized != 1u || !input || !work ||
        (slu && (!slu->state || !slu->output)) ||
        input->qualified != 1u || input->engine.coherent != 1u ||
        input->selector < RBM_U340E_SELECTOR_P || input->selector > RBM_U340E_SELECTOR_L ||
        (cycle->have_event && input->event - cycle->last_event != 1u)) {
        cycle->faulted = 1u;
        return LFJ8_H03_CYCLE_FAULT;
    }
    uint32_t command_at = input->command_at;
    if (load && !publish_cycle_load(runtime, load, &command_at)) {
        cycle->faulted = 1u;
        return LFJ8_H03_CYCLE_FAULT;
    }
    cycle->last_event = input->event;
    cycle->have_event = 1u;

    RbmU340eScheduler *schedule = &cycle->scheduler;
    if (rbm_u340e_schedule_timer_irq(schedule) != RBM_U340E_IRQ_PRODUCER) {
        cycle->faulted = 1u;
        return LFJ8_H03_CYCLE_FAULT;
    }
    const RbmU340eRelease release = rbm_u340e_schedule_producer_publish(schedule);
    if (!rbm_u340e_schedule_producer_done(schedule)) {
        cycle->faulted = 1u;
        return LFJ8_H03_CYCLE_FAULT;
    }
    RbmU340eRangeInputs range = {
        .selector = input->selector, .range_5722 = input->range_5722,
        .inhibit_5250 = input->inhibit_5250, .request_1120 = cycle->request_1120,
    };
    switch (release) {
    case RBM_U340E_RELEASE_NONE:
        return LFJ8_H03_CYCLE_NO_MAIN;
    case RBM_U340E_RELEASE_FAST:
        if (fast_step(cycle, runtime, &range)) {
            return LFJ8_H03_CYCLE_NO_MAIN;
        }
        break;
    case RBM_U340E_RELEASE_SECONDARY:
        if (!rbm_u340e_schedule_secondary_claim(schedule) ||
            !rbm_u340e_runtime_secondary_load_qualify(runtime, range.inhibit_5250,
                                                     &cycle->request_1120) ||
            (run_slu && !run_slu(&runtime->gp, input->event, command_at, load, slu))) {
            break;
        }
        range.request_1120 = cycle->request_1120;
        const RbmU340eSecondary secondary = rbm_u340e_schedule_secondary_done(schedule);
        if (secondary == RBM_U340E_SECONDARY_DONE) {
            if (slu) {
                slu->output->valid = 1u;
            }
            return LFJ8_H03_CYCLE_NO_MAIN;
        }
        if (secondary == RBM_U340E_SECONDARY_RUN_MAIN &&
            main_step(cycle, runtime, input, &range, work, result)) {
            result->command_at = command_at;
            if (slu) {
                slu->output->valid = 1u;
            }
            return LFJ8_H03_CYCLE_MAIN;
        }
        break;
    default:
        break;
    }

    cycle->faulted = 1u;
    *result = (Lfj8H03MainResult){0};
    if (slu) {
        *slu->output = (Lfj8H03SluOutput){0};
    }
    return LFJ8_H03_CYCLE_FAULT;
}

Lfj8H03CycleResult lfj8_h03_cycle_tick(Lfj8H03Cycle *cycle, RbmU340eRuntime *runtime,
                                      const Lfj8H03CycleInput *input, Lfj8H03CycleWorkspace *work,
                                      Lfj8H03MainResult *result)
{
    return cycle_tick(cycle, runtime, input, work, result, NULL, NULL, NULL);
}

Lfj8H03CycleResult lfj8_h03_cycle_tick_with_load(Lfj8H03Cycle *cycle, RbmU340eRuntime *runtime,
    const Lfj8H03CycleInput *input, Lfj8H03CycleWorkspace *work, Lfj8H03MainResult *result,
    Lfj8H03CycleLoad load)
{
    return cycle_tick(cycle, runtime, input, work, result, &load, NULL, NULL);
}

Lfj8H03CycleResult lfj8_h03_cycle_tick_with_slu(Lfj8H03Cycle *cycle, RbmU340eRuntime *runtime,
    const Lfj8H03CycleInput *input, Lfj8H03CycleWorkspace *work, Lfj8H03MainResult *result,
    Lfj8H03CycleLoad load, Lfj8H03CycleSlu slu)
{
    return cycle_tick(cycle, runtime, input, work, result, &load, &slu, secondary_slu);
}

static int16_t signed_word(uint32_t value)
{
    return (int16_t)((int32_t)value - ((value & 0x8000u) ? 65536 : 0));
}

int lfj8_h03_cycle_slt_inputs(const FactoryHydraulics *gp, FactorySLTInputs *out)
{
    uint32_t selected, limit, override, flags;
    if (!out ||
        !factory_hydraulics_get(gp, 1158, 2u, &selected) ||
        !factory_hydraulics_get(gp, -7138, 2u, &limit) ||
        !factory_hydraulics_get(gp, -7134, 2u, &override) ||
        !factory_hydraulics_get(gp, 1156, 1u, &flags)) {
        return 0;
    }
    *out = (FactorySLTInputs){
        .selected_p1158 = signed_word(selected), .limit_7138 = signed_word(limit),
        .override_7134 = signed_word(override), .flags_p1156 = (uint8_t)flags,
    };
    return 1;
}

int lfj8_h03_cycle_prepare_outputs(Lfj8H03Takeover *takeover, const Lfj8H03MainResult *main,
                                     const Lfj8H03FastOutput *fast,
                                     const Lfj8H03ActuatorCalibration *calibration,
                                     const Lfj8H03OemOutputState *oem, Lfj8H03OperatingPoint operating,
                                     uint32_t generation)
{
    const uint32_t half = UINT32_C(0x80000000);
    if (!main || main->valid != 1u || !fast || fast->valid != 1u || !calibration ||
        main->shift.count > sizeof(main->shift.writes) / sizeof(main->shift.writes[0]) ||
        fast->st.write_pending > 1u ||
        (fast->st.write_pending && fast->st.channel != RBM_U340E_DONOR_CHANNEL_ST)) {
        return lfj8_h03_takeover_prepare_plan(takeover, NULL, generation, 0u);
    }

    const uint32_t advance = fast->command_at - main->command_at;
    if (advance == half) {
        return lfj8_h03_takeover_prepare_plan(takeover, NULL, generation, 0u);
    }
    const uint32_t oldest = advance < half ? main->command_at : fast->command_at;
    RbmU340eHydraulicOutput output;
    output.slt_result = fast->slt;
    output.write_count = main->shift.count;
    for (size_t i = 0; i < main->shift.count; ++i) {
        if (main->shift.writes[i].channel > RBM_U340E_DONOR_CHANNEL_S2) {
            return lfj8_h03_takeover_prepare_plan(takeover, NULL, generation, oldest);
        }
        output.writes[i] = main->shift.writes[i];
    }
    if (fast->st.write_pending) {
        output.writes[output.write_count++] = fast->st;
    }
    Lfj8H03OutputPlan plan;
    const Lfj8H03OutputResult status = lfj8_h03_plan_outputs(&output,
        &calibration->binding, oem, calibration->slt, operating, &plan);
    return lfj8_h03_takeover_prepare_plan(takeover,
        status == LFJ8_H03_OUTPUT_OK ? &plan : NULL, generation, oldest);
}
