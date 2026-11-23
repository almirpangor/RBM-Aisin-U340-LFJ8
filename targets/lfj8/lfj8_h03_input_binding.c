#include "lfj8_h03_input_binding.h"

#define HALF_CLOCK UINT32_C(0x80000000)
#define SHIFT_BUTTONS (RBM_U340E_BUTTON_UP | RBM_U340E_BUTTON_DOWN)

int lfj8_h03_input_startup(const Lfj8H03InputBinding *binding, const Lfj8H03InputStartup *startup)
{
    return binding && startup && binding->selector_only <= 1u && binding->require_pn_agreement <= 1u &&
        (!binding->selector_only || (!binding->p1_button_map &&
          startup->policy.initial_mode == RBM_U340E_AUTO && !startup->policy.manual_selectors)) &&
        rbm_u340e_selector_profile_valid(binding->selector_profile) &&
        lfj8_range_control_init(binding->control, &startup->policy, startup->selector_max_age_us) &&
        lfj8_button_filter_init(binding->button_filter, startup->button_debounce_us, startup->button_max_age_us);
}

static int valid_binding(const Lfj8H03InputBinding *binding)
{
    return binding && binding->adc && binding->control && binding->button_filter &&
        binding->selector_only <= 1u && binding->require_pn_agreement <= 1u &&
        !(binding->selector_only && binding->p1_button_map) &&
        binding->control->controller.initialized == 1u &&
        binding->control->max_age_us && binding->button_filter->max_age_us &&
        binding->io && binding->io->enter && binding->io->leave;
}

static int captures_ready(const Lfj8H03InputBinding *binding, uint32_t now_us)
{
    const Lfj8RangeControl *control = binding->control;
    const Lfj8ButtonFilter *buttons = binding->button_filter;
    return control->selector != RBM_U340E_SELECTOR_UNKNOWN &&
        now_us - control->last_sample_us < control->max_age_us &&
        (binding->selector_only || (buttons->armed &&
         now_us - buttons->last_sample_us < buttons->max_age_us));
}

int lfj8_h03_input_capture(const Lfj8H03InputBinding *binding, const Lfj8ButtonReading *buttons,
                          uint32_t now_us)
{
    if (!valid_binding(binding)) {
        return 0;
    }

    Lfj8RangeControl *control = binding->control;
    Lfj8ButtonFilter *filter = binding->button_filter;
    const Lfj8SelectorAdcReading reading = lfj8_selector_adc_take(binding->adc, binding->io);
    lfj8_range_control_sample_selector_profile(control, reading, now_us, binding->selector_profile);
    if (control->selector == RBM_U340E_SELECTOR_UNKNOWN || binding->selector_only) {
        lfj8_range_control_disarm_buttons(control, filter);
        return !buttons && binding->selector_only && captures_ready(binding, now_us);
    }

    Lfj8ButtonReading from_adc;
    if (binding->p1_button_map) {
        if (buttons || (reading.event != LFJ8_SELECTOR_ADC_NONE &&
            !lfj8_h03_button_decode_p1(binding->p1_button_map, &reading, &from_adc))) {
            lfj8_range_control_disarm_buttons(control, filter);
            return 0;
        }
        if (reading.event != LFJ8_SELECTOR_ADC_NONE) {
            buttons = &from_adc;
        }
    }
    lfj8_range_control_sample_buttons(control, filter, buttons, now_us);
    if ((filter->stable & SHIFT_BUTTONS) == SHIFT_BUTTONS ||
        (control->manual_gear && (now_us - control->manual_started_us >= binding->manual_max_age_us ||
            (filter->stable & RBM_U340E_BUTTON_MODE &&
             !(control->controller.previous_buttons & RBM_U340E_BUTTON_MODE))))) {
        control->manual_gear = 0;
    }
    return captures_ready(binding, now_us);
}

static uint8_t manual_target(const Lfj8H03InputBinding *binding, const Lfj8H03InputSources *sources,
                             const RbmU340eOutput *driver)
{
    Lfj8RangeControl *const control = binding->control;
    if (!binding->manual_max_age_us || binding->manual_max_age_us >= HALF_CLOCK ||
        driver->mode != RBM_U340E_TIPTRONIC || driver->conflicting_buttons ||
        !(control->controller.policy.manual_selectors & (1u << control->selector))) {
        control->manual_gear = 0;
        return 0;
    }
    if (driver->requested_gear) {
        control->manual_gear = driver->requested_gear;
        control->manual_selector = control->selector;
        control->manual_generation = sources->generation;
        control->manual_started_us = sources->now_us;
    }
    const unsigned gear = control->manual_gear;
    if (gear) {
        const RbmU340eInput *const state = sources->driver;
        const unsigned actual = state->actual_gear;
        const int od_blocks_fourth = gear == 4u && !driver->overdrive_enabled &&
            (control->controller.policy.overdrive_limit_modes & RBM_U340E_OVERDRIVE_TIPTRONIC);
        if (control->manual_selector != control->selector || od_blocks_fourth ||
            !(state->allowed_gears & (1u << (gear - 1u))) ||
            sources->now_us - control->manual_started_us >= binding->manual_max_age_us ||
            (!state->shifting && (actual == gear || !actual)) ||
            (actual && (actual + 1u < gear || gear + 1u < actual))) {
            control->manual_gear = 0;
        }
    }
    return control->manual_gear;
}

static int propose_captured(const Lfj8H03InputBinding *binding,
    const Lfj8H03InputSources *sources, Lfj8H03InputProposal *out, int engine_after_take)
{
    if (!out) {
        return 0;
    }
    *out = (Lfj8H03InputProposal){0};
    if (!valid_binding(binding)) {
        return 0;
    }

    Lfj8RangeControl *control = binding->control;
    Lfj8ButtonFilter *buttons = binding->button_filter;
    Lfj8H03RangeSnapshot range;
    if (!sources || !sources->cycle || (!binding->selector_only && !sources->driver) ||
        ((binding->p1_button_map || binding->selector_only) && sources->buttons) ||
        sources->cycle->qualified != 1 || (!engine_after_take && sources->cycle->engine.coherent != 1) ||
        sources->now_us - sources->cycle->command_at >= HALF_CLOCK ||
        (control->manual_gear && control->manual_generation != sources->generation) ||
        !lfj8_h03_range_snapshot(sources->range, binding->range_limits, sources->generation,
                                 sources->now_us, &range)) {
        lfj8_range_control_disarm_buttons(control, buttons);
        return 0;
    }

    const uint32_t now = sources->now_us;
    const int selector_in_pn = control->selector == RBM_U340E_SELECTOR_P ||
                               control->selector == RBM_U340E_SELECTOR_N;
    if (binding->require_pn_agreement && selector_in_pn != !!(range.range_5722 & (1u << 2))) {
        lfj8_range_control_disarm_buttons(control, buttons);
        return 0;
    }
    if (!captures_ready(binding, now)) {
        control->manual_gear = 0;
        if (buttons->armed) {
            lfj8_range_control_disarm_buttons(control, buttons);
        }
        return 0;
    }
    if (binding->selector_only) {
        out->driver.mode = control->controller.mode;
        out->driver.overdrive_enabled = control->controller.overdrive_enabled;
    } else {
        const Lfj8SelectorAdcReading idle = {.event = LFJ8_SELECTOR_ADC_NONE};
        if (!lfj8_range_control_step_with_buttons(control, idle, buttons, NULL,
                                                  now, sources->driver, &out->driver)) {
            out->driver = (RbmU340eOutput){0};
            return 0;
        }
    }
    /* The H03 application does not route the deferred auxiliary relays. */
    out->driver.relay_mask = 0;

    out->cycle = *sources->cycle;
    out->cycle.requested_gear = binding->selector_only ? 0u : manual_target(binding, sources, &out->driver);
    out->cycle.selector = control->selector;
    out->cycle.range_5722 = range.range_5722;
    out->cycle.inhibit_5250 = range.inhibit_5250;
    const uint32_t captures[] = {control->last_sample_us, range.oldest_us,
        binding->selector_only ? control->last_sample_us : buttons->last_sample_us};
    for (unsigned i = 0; i < sizeof captures / sizeof captures[0]; ++i) {
        if (now - captures[i] > now - out->cycle.command_at) {
            out->cycle.command_at = captures[i];
        }
    }
    return 1;
}

int lfj8_h03_input_propose_captured(const Lfj8H03InputBinding *binding,
    const Lfj8H03InputSources *sources, Lfj8H03InputProposal *out)
{
    return propose_captured(binding, sources, out, 0);
}

int lfj8_h03_input_propose(const Lfj8H03InputBinding *binding, const Lfj8H03InputSources *sources,
                           Lfj8H03InputProposal *out)
{
    if (out && sources) {
        lfj8_h03_input_capture(binding, sources->buttons, sources->now_us);
    }
    return lfj8_h03_input_propose_captured(binding, sources, out);
}

int lfj8_h03_input_capture_toyota(void *context, const Lfj8H03SensorSnapshot *sensors,
                                  uint32_t due_at, Lfj8H03CycleInput *input,
                                  Lfj8H03CycleLoad *load)
{
    const Lfj8H03ToyotaInputCapture *const capture = context;
    if (!capture || !capture->binding || !capture->proposal || !capture->ram_owned ||
        !capture->read || !sensors || !input || !load) {
        return 0;
    }
    const Lfj8H03InputBinding *const binding = capture->binding;
    const Lfj8RegisterIo *const io = binding->io;
    if (!io || !io->enter || !io->leave ||
        (!binding->selector_only &&
         (!binding->manual_max_age_us || binding->manual_max_age_us >= HALF_CLOCK))) {
        return 0;
    }

    Lfj8H03InputSources sources = {0};
    const RbmU340eQualifiedEngineFeed engine = input->engine;
    const int captured = capture->read(capture->platform, sensors, due_at, input, load, &sources);
    input->engine = engine;
    const uint32_t saved = io->enter(io->context);
    int ready = 0;
    if (capture->ram_owned(capture->platform) == 1 && valid_binding(binding)) {
        input->requested_gear = 0u;
        if (captured == 1 && !sources.buttons) {
            sources.cycle = input;
            sources.now_us = load->now_us;
            sources.generation = sensors->epoch;
            ready = propose_captured(binding, &sources, capture->proposal, 1);
            if (ready) {
                *input = capture->proposal->cycle;
            }
        } else {
            lfj8_range_control_disarm_buttons(binding->control, binding->button_filter);
        }
    }
    io->leave(io->context, saved);
    return ready;
}
