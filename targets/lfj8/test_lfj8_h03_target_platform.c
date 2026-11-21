/* Board-input stand-ins for the M32R simulator. The platform, release clock,
 * application binding and foreground wrapper are the production sources. */
#include "lfj8_h03_target_platform.h"
#include "lfj8_h03_application_binding.h"
#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_input_binding.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_sensor_target.h"
#include "lfj8_h03_target_service.h"
#include "lfj8_selector_adc.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>

#define MMIO8(address) (*(volatile uint8_t *)(uintptr_t)(address))
#define TML0CT (*(volatile uint32_t *)(uintptr_t)0x8003e0u)
#define TML1CT (*(volatile uint32_t *)(uintptr_t)0x800fe0u)

Lfj8H03Application rbm_h03_application;
Lfj8H03ToyotaRelease rbm_h03_toyota_release_state;
Lfj8H03Takeover rbm_h03_takeover_state;
Lfj8H03Cycle rbm_h03_cycle_state;
RbmU340eRuntime rbm_h03_runtime_state;
Lfj8H03CycleWorkspace rbm_h03_cycle_workspace;
Lfj8H03MainResult rbm_h03_main_result;
Lfj8H03CycleInput rbm_h03_cycle_input;
Lfj8H03SensorTarget rbm_h03_sensor_state;
volatile Lfj8H03Atf rbm_h03_atf_state;
volatile Lfj8SelectorAdc rbm_h03_selector_adc_state;
volatile uint8_t rbm_h03_tml0_1mhz_qualified;
const Lfj8H03SensorFeedConfig rbm_h03_sensor_config = {200u, 200u, 200u, 0u};
FactoryGearState rbm_h03_target_startup_gear = {
    .driver5302 = {1, 1}, .u7184 = 20000, .u7164 = 26000, .u7186 = 3072,
    .periods = {65535, 65535, 65535, 65535, 65535, 65535},
};
FactoryHydraulics rbm_h03_target_startup_gp;

static volatile Lfj8H03PhaseClock phase_clock;
static Lfj8H03EngineRx engine_rx;
static Ta2005EngineQualifier engine_qualifier;
static CheryDtcState engine_dtc;
static Lfj8H03CanOwner engine_owner;
static RbmU340eQualifiedLoadFeed sample;
static unsigned stock_startups, input_starts, captures, stock_updates, services, inhibits;
static uint32_t last_due;
static int owned = 1, clock_ready = 1, inputs_ready = 1, capture_ready = 1;
static int revoke_at_start;
static int can_ready = 1, can_prepared, fail_after_prepare;
static unsigned can_starts, can_live_stops, can_stops;
static uint8_t clock_at_last_live_stop;

#ifdef RBM_H03_TEST_MANUAL_PROFILE
enum {
    PHASE_TICKS = 8u, TOYOTA_TICKS = 64u,
    PORT_IDLE = 8u, PORT_UP = PORT_IDLE | 64u, PORT_BOTH = PORT_UP | 32u,
};
static Lfj8RangeControl manual_control;
static Lfj8ButtonFilter manual_buttons;
static Lfj8H03InputProposal manual_proposal;
static Lfj8H03RangeInputs manual_range;
static RbmU340eInput manual_driver;
static unsigned mains;
static uint16_t an2 = 665u;
static uint8_t button_port = PORT_IDLE;

/* Synthetic inputs and timing confined to this simulator profile. */
static const Lfj8H03ButtonMap manual_pins = {{
    {LFJ8_H03_BUTTON_P1, 8u, 1u}, {LFJ8_H03_BUTTON_P1, 64u, 0u},
    {LFJ8_H03_BUTTON_P1, 32u, 0u}, {0},
}};
static const Lfj8H03RangeAgeLimits manual_limits = {{16u, 16u, 16u, 16u}, 16u};
static const Lfj8H03InputBinding manual_binding = {
    .adc = &rbm_h03_selector_adc_state, .control = &manual_control, .button_filter = &manual_buttons,
    .io = &lfj8_h03_mmio, .range_limits = &manual_limits, .p1_button_map = &manual_pins,
    .manual_max_age_us = 32768u,
};
#endif

const Lfj8H03TargetServiceConfig test_can_service_config = {
    .can13 = {.bit_time_us = 2u},
};

static int irq_enabled(void)
{
    uint32_t psw;
    __asm__ volatile ("mvfc %0,psw" : "=r"(psw) : : "memory");
    return (psw & 0x40u) != 0u;
}

int rbm_h03_target_ram_owned(void *context)
{
    assert(!context && !irq_enabled());
    return owned;
}

int rbm_h03_target_clock_ready(void *context)
{
    assert(!context && !irq_enabled() && owned);
    return clock_ready && !(fail_after_prepare && can_prepared);
}

bool lfj8_h03_target_service_prepare_locked(const Lfj8H03TargetServiceConfig *config)
{
    assert(config == &test_can_service_config && !irq_enabled() && owned && clock_ready);
    assert(!rbm_h03_application.running && !rbm_h03_tml0_1mhz_qualified && !can_prepared);
    ++can_starts;
    can_prepared = can_ready;
    return can_prepared != 0;
}

void lfj8_h03_target_service_stop_locked(void)
{
    assert(!irq_enabled() && owned && !rbm_h03_application.running);
    ++can_stops;
    if (can_prepared) {
        clock_at_last_live_stop = rbm_h03_tml0_1mhz_qualified;
        ++can_live_stops;
    }
    can_prepared = 0;
}

int test_initialize_inputs(void *context)
{
    assert(!context && irq_enabled() && stock_startups == 1u && !rbm_h03_application.running);
    assert(rbm_h03_selector_adc_state.pending_event == LFJ8_SELECTOR_ADC_NONE);
    ++input_starts;
#ifdef RBM_H03_TEST_MANUAL_PROFILE
    static const RbmU340ePolicy policy = {
        .manual_selectors = 1u << RBM_U340E_SELECTOR_D,
        .initial_mode = RBM_U340E_TIPTRONIC, .initial_overdrive_enabled = 1u,
    };
    assert(lfj8_range_control_init(&manual_control, &policy, 24u));
    assert(lfj8_button_filter_init(&manual_buttons, PHASE_TICKS, 24u));
#endif
    if (revoke_at_start) {
        owned = 0;
    }
    return inputs_ready;
}

int test_capture_inputs(void *context, const Lfj8H03SensorSnapshot *sensors, uint32_t due_at,
                        Lfj8H03CycleInput *input, Lfj8H03CycleLoad *load)
{
    assert(!context && irq_enabled() && stock_updates == services + 1u);
    assert(sensors->capture.now_tml0 == TML0CT && input == &rbm_h03_cycle_input);
    ++captures;
    last_due = due_at;
    *input = (Lfj8H03CycleInput){
        .event = UINT32_MAX, .selector = RBM_U340E_SELECTOR_N, .range_5722 = 5u, .qualified = 1u,
        .command_at = due_at - 1u,
    };
    sample = (RbmU340eQualifiedLoadFeed){.coherent = 1u, .sampled_at = due_at - 2u};
    *load = (Lfj8H03CycleLoad){.sample = &sample, .now_us = TML0CT, .max_age_us = 5u};
    return capture_ready;
}

#ifdef RBM_H03_TEST_MANUAL_PROFILE
static int read_manual_inputs(void *context, const Lfj8H03SensorSnapshot *sensors, uint32_t due_at,
    Lfj8H03CycleInput *input, Lfj8H03CycleLoad *load, Lfj8H03InputSources *sources)
{
    const int ready = test_capture_inputs(context, sensors, due_at, input, load);
    const uint8_t range = an2 == 665u ? 5u : 1u;
    for (unsigned bit = 0; bit < 4u; ++bit) {
        manual_range.range_5722[bit] =
            (Lfj8H03RangeBit){due_at - 3u, sensors->epoch, (uint8_t)((range >> bit) & 1u), 1u};
    }
    manual_range.inhibit_5250_2 = (Lfj8H03RangeBit){due_at - 2u, sensors->epoch, 0u, 1u};
    load->max_age_us = 8u;
    sources->driver = &manual_driver;
    sources->range = &manual_range;
    return ready;
}

const Lfj8H03ToyotaInputCapture test_input_capture = {
    .binding = &manual_binding, .proposal = &manual_proposal,
    .ram_owned = rbm_h03_target_ram_owned, .read = read_manual_inputs,
};
#endif

static int engine_context(void *context, const Lfj8H03SensorSnapshot *sensors,
    Ta2005EngineQualificationContext *engine, bool *history, uint32_t *oldest)
{
    assert(!context && !irq_enabled() && sensors->capture.now_tml0 == TML0CT);
    *engine = (Ta2005EngineQualificationContext){.coherent = 1u, .fallback_fa7b = 137u};
    *history = true;
    *oldest = TML0CT;
    return 1;
}

const Lfj8H03ApplicationEngine rbm_h03_target_engine = {
    .target = {.rx = &engine_rx, .qualifier = &engine_qualifier, .dtc = &engine_dtc,
               .can_owner = &engine_owner, .io = &lfj8_h03_mmio, .now_us = rbm_h03_atf_now_us,
               .bit_time_us = 2u},
    .max_age_ticks = 20u, .max_poll_gap_us = 32u, .context_for_task2 = engine_context,
};

void rbm_h03_application_foreground_hook(void);
void rbm_h03_phase_startup_hook(void);
void rbm_h03_phase_release_hook(void);

void h03_stock_startup_record(void)
{
    assert(irq_enabled());
    ++stock_startups;
}

void h03_stock_phase_release(void)
{
    assert(!irq_enabled());
}

void h03_stock_foreground_inputs(void)
{
    assert(irq_enabled());
    ++stock_updates;
#ifdef RBM_H03_TEST_MANUAL_PROFILE
    MMIO8(LFJ8_H03_P1DATA_ADDRESS) = button_port;
    const uint32_t saved = lfj8_h03_mmio.enter(NULL);
    rbm_h03_selector_adc_capture(an2);
    lfj8_h03_mmio.leave(NULL, saved);
#endif
}

void rbm_h03_target_service_phase(void *context, const Lfj8H03PhaseEvent *phase,
    const Lfj8H03SensorSnapshot *sensors, const Lfj8H03MainResult *main)
{
    assert(!context && irq_enabled() && can_prepared && sensors->capture.now_tml0 == phase->released_at);
    ++services;
#ifdef RBM_H03_TEST_MANUAL_PROFILE
    if (main) {
        assert(main == &rbm_h03_main_result && main->valid && main->command_at == last_due - 3u);
        ++mains;
    }
#else
    (void)main;
#endif
}

static void inhibit(void *context)
{
    assert(!context && !irq_enabled());
    ++inhibits;
}

static int refuse_output(void *context)
{
    (void)context;
    return 0;
}

static void unexpected_output(void *context)
{
    (void)context;
    assert(0);
}

static void unexpected_write(void *context, uint32_t address, uint32_t value)
{
    (void)address;
    (void)value;
    unexpected_output(context);
}

const Lfj8H03TakeoverOps rbm_h03_target_takeover_ops = {
    .io = &lfj8_h03_mmio, .clock_ticks = lfj8_h03_tml0ct_m32r, .phase_clock = &phase_clock,
    .write32 = unexpected_write, .qualified = refuse_output,
    .arbitrate = unexpected_output, .apply = unexpected_output, .inhibit = inhibit,
    .isolated_pwm_mask = LFJ8_H03_ALL_SPARE_PWM_ISOLATED,
};

static void startup(uint32_t at)
{
    stock_startups = stock_updates = services = 0u;
    TML0CT = at;
    rbm_h03_selector_adc_state.pending_event = LFJ8_SELECTOR_ADC_OVERRUN;
    rbm_h03_phase_startup_hook();
    assert(irq_enabled());
}

static void foreground(uint32_t at)
{
    TML0CT = at;
    TML1CT = at;
    const uint32_t saved = lfj8_h03_mmio.enter(NULL);
    rbm_h03_phase_release_hook();
    assert(!irq_enabled());
    lfj8_h03_mmio.leave(NULL, saved);
    rbm_h03_application_foreground_hook();
    assert(irq_enabled());
}

static void assert_faulted(void)
{
    assert(!rbm_h03_application.running && !rbm_h03_runtime_state.initialized);
    assert(!rbm_h03_takeover_state.pending && !rbm_h03_main_result.valid && phase_clock.faulted);
    assert(rbm_h03_cycle_state.faulted && !rbm_h03_tml0_1mhz_qualified && inhibits > 0u);
    assert(!can_prepared && clock_at_last_live_stop == 1u);
}

#ifdef RBM_H03_TEST_MANUAL_PROFILE
static void next_manual_release(uint32_t *at)
{
    for (unsigned i = 0; i < TOYOTA_TICKS / PHASE_TICKS; ++i) {
        *at += PHASE_TICKS;
        foreground(*at);
        if (!rbm_h03_application.running) {
            fprintf(stderr, "at=%lu captures=%u services=%u mains=%u selector=%u armed=%u release=%u now=%lu have=%u input=%u\n",
                (unsigned long)*at, captures, services, mains, manual_control.selector, manual_buttons.armed,
                rbm_h03_toyota_release_state.status, (unsigned long)rbm_h03_toyota_release_state.last_observed,
                rbm_h03_cycle_state.have_event, rbm_h03_cycle_input.qualified);
        }
        assert(rbm_h03_application.running);
    }
    assert(last_due == *at && rbm_h03_cycle_input.engine.coherent == 1u);
}

static void next_manual_main(uint32_t *at)
{
    const unsigned before = mains;
    for (unsigned i = 0; i < 17u && mains == before; ++i) {
        next_manual_release(at);
    }
    assert(mains == before + 1u);
}

static void expect_shift(uint32_t target, unsigned s2)
{
    const Lfj8H03MainResult *const result = &rbm_h03_main_result;
    uint32_t requested;
    assert(factory_hydraulics_get(&rbm_h03_runtime_state.gp, -4854, 1u, &requested));
    assert(requested == target && result->shift.count == 2u);
    assert(result->shift.writes[0].channel == 0u && result->shift.writes[0].value == 1u);
    assert(result->shift.writes[1].channel == 1u && result->shift.writes[1].value == s2);
}

static int test_manual_profile(void)
{
    uint32_t at = UINT32_MAX - 31u;
    manual_driver = (RbmU340eInput){.actual_gear = 1u, .allowed_gears = 15u};
    startup(at);
    assert(rbm_h03_application.running && !manual_buttons.armed);
    next_manual_release(&at);
    assert(captures == 1u && services == TOYOTA_TICKS / PHASE_TICKS && manual_buttons.armed);
    assert(rbm_h03_cycle_state.last_event == 0u && rbm_h03_cycle_input.selector == RBM_U340E_SELECTOR_N);
    next_manual_main(&at);
    next_manual_main(&at);

    an2 = 500u; /* D */
    assert(factory_hydraulics_set(&rbm_h03_runtime_state.gp, -7154, 2u, 6400u));
    for (unsigned i = 0; i < 130u; ++i) {
        next_manual_main(&at);
    }
    assert(factory_hydraulics_set(&rbm_h03_runtime_state.gp, -4548, 1u, 19u));
    assert(factory_hydraulics_set(&rbm_h03_runtime_state.gp, -4549, 1u, 19u));
    next_manual_main(&at);
    expect_shift(0u, 1u);

    button_port = PORT_UP;
    next_manual_release(&at);
    assert(rbm_h03_cycle_input.requested_gear == 2u && manual_proposal.driver.requested_gear == 2u);
    button_port = PORT_IDLE;
    manual_driver.shifting = 1u;
    next_manual_release(&at);
    assert(rbm_h03_cycle_input.requested_gear == 2u && !manual_proposal.driver.requested_gear);
    for (unsigned i = 0; i < 12u; ++i) {
        next_manual_main(&at);
        assert(rbm_h03_cycle_input.requested_gear == 2u);
    }
    expect_shift(1u, 0u);

    manual_driver.actual_gear = 2u;
    next_manual_release(&at);
    assert(rbm_h03_cycle_input.requested_gear == 2u); /* Target observed, shift still in progress. */
    manual_driver.shifting = 0u;
    next_manual_release(&at);
    assert(!rbm_h03_cycle_input.requested_gear && !manual_control.manual_gear);
    assert(factory_hydraulics_set(&rbm_h03_runtime_state.gp, -4548, 1u, 17u));
    assert(factory_hydraulics_set(&rbm_h03_runtime_state.gp, -4549, 1u, 17u));
    next_manual_main(&at);
    expect_shift(0u, 1u);

    manual_driver.actual_gear = 1u;
    button_port = PORT_UP;
    next_manual_release(&at);
    assert(rbm_h03_cycle_input.requested_gear == 2u);
    const unsigned before_conflict = captures;
    button_port = PORT_BOTH;
    foreground(at += PHASE_TICKS);
    assert(rbm_h03_cycle_input.requested_gear == 2u); /* Chord still debouncing. */
    foreground(at += PHASE_TICKS);
    assert(!rbm_h03_cycle_input.requested_gear && !manual_control.manual_gear);
    assert(captures == before_conflict && rbm_h03_application.running);
    for (unsigned i = 2; i < TOYOTA_TICKS / PHASE_TICKS; ++i) {
        foreground(at += PHASE_TICKS);
    }
    assert(manual_proposal.driver.conflicting_buttons && !rbm_h03_cycle_input.requested_gear);
    button_port = PORT_IDLE;
    next_manual_release(&at);
    assert(!rbm_h03_cycle_input.requested_gear);

    button_port = PORT_UP;
    next_manual_main(&at);
    assert(rbm_h03_cycle_input.requested_gear == 2u && rbm_h03_main_result.valid);
    const unsigned before = services;
    const unsigned captured = captures;
    const unsigned inhibited = inhibits;
    an2 = UINT16_MAX;
    foreground(at += PHASE_TICKS); /* No Toyota event due, but invalid AN2 revokes output. */
    assert(rbm_h03_application.running && captures == captured && services == before + 1u);
    assert(!rbm_h03_cycle_input.requested_gear && !manual_control.manual_gear && !manual_buttons.armed);
    assert(!rbm_h03_takeover_state.pending && !rbm_h03_main_result.valid && inhibits == inhibited + 1u);
    for (unsigned i = 1; i < TOYOTA_TICKS / PHASE_TICKS; ++i) {
        foreground(at += PHASE_TICKS);
    }
    assert_faulted();
    assert(captures == captured + 1u && services == before + TOYOTA_TICKS / PHASE_TICKS - 1u);

    an2 = 500u;
    startup(at);
    assert(!manual_control.manual_gear && !manual_buttons.armed);
    for (unsigned i = 0; i < TOYOTA_TICKS / PHASE_TICKS; ++i) {
        foreground(at += PHASE_TICKS); /* Held UP never establishes the new baseline. */
    }
    assert_faulted();
    assert(!manual_control.manual_gear && captures == captured + 2u);
    puts("H03 manual profile: native foreground, Toyota hold, MAIN S1/S2 and revocation PASS");
    return 0;
}
#endif

int main(void)
{
    __asm__ volatile ("setpsw #0x40" ::: "memory", "cc");
    MMIO8(0x800203) = 9u;
    MMIO8(0x8003eb) = 0x01u;
    MMIO8(0x800feb) = 0x31u;
    assert(factory_hydraulics_set(&rbm_h03_target_startup_gp, -7184, 2u, 20000u));
    assert(factory_hydraulics_set(&rbm_h03_target_startup_gp, -7164, 2u, 26000u));
    assert(factory_hydraulics_set(&rbm_h03_target_startup_gp, -7186, 2u, 3072u));
    _Static_assert(sizeof(Lfj8H03ToyotaRelease) == 16u, "Toyota release RAM inventory");

#ifdef RBM_H03_TEST_MANUAL_PROFILE
    return test_manual_profile();
#endif

    rbm_h03_toyota_release_state.status = UINT8_MAX;
    owned = 0;
    startup(100u);
    assert(!can_stops && !can_starts);
    owned = 1;
    clock_ready = 0;
    startup(100u);
    assert(!input_starts && rbm_h03_toyota_release_state.status == UINT8_MAX);
    assert(rbm_h03_selector_adc_state.pending_event == LFJ8_SELECTOR_ADC_OVERRUN);

    clock_ready = 1;
    inputs_ready = 0;
    startup(100u);
    assert(input_starts == 1u && !rbm_h03_application.running);
    assert(rbm_h03_toyota_release_state.status == UINT8_MAX);
    inputs_ready = revoke_at_start = 1;
    startup(100u);
    assert(input_starts == 2u && !owned && !rbm_h03_application.running);
    assert(rbm_h03_toyota_release_state.status == UINT8_MAX);
    owned = 1;
    revoke_at_start = 0;

    can_ready = 0;
    startup(100u);
    assert(input_starts == 3u && can_starts == 1u && !can_prepared && !rbm_h03_application.running);
    assert(rbm_h03_toyota_release_state.status == UINT8_MAX);
    can_ready = 1;
    fail_after_prepare = 1;
    startup(100u);
    assert(input_starts == 4u && can_starts == 2u && can_live_stops == 1u);
    assert(!can_prepared && !rbm_h03_application.running && clock_at_last_live_stop == 0u);
    fail_after_prepare = 0;

    const uint32_t anchor = UINT32_MAX - 11u;
    startup(anchor);
    assert(rbm_h03_application.running && input_starts == 5u && can_starts == 3u);
    assert(!rbm_h03_target_initialize(NULL) && input_starts == 5u);
    assert(!rbm_h03_target_initialize(&owned) && input_starts == 5u);
    foreground(anchor + 8u);
    assert(!captures && services == 1u);
    foreground(anchor + 17u);
    assert(captures == 1u && services == 2u && last_due == anchor + 16u);
    assert(rbm_h03_cycle_state.have_event && rbm_h03_cycle_state.last_event == 0u);
    assert(rbm_h03_cycle_input.command_at == last_due - 1u && sample.sampled_at == last_due - 2u);
    assert(rbm_h03_application.last_toyota_at == last_due);

    startup(100u); /* Warm restart: reanchor and discard the previous sequence. */
    assert(rbm_h03_application.running && input_starts == 6u && can_starts == 4u);
    assert(can_live_stops == 2u && clock_at_last_live_stop == 1u);
    foreground(108u);
    foreground(116u);
    assert(captures == 2u && services == 2u && last_due == 116u);
    assert(rbm_h03_cycle_state.last_event == 0u);

    startup(200u);
    foreground(208u);
    capture_ready = 0;
    foreground(216u);
    assert_faulted();
    assert(captures == 3u && services == 1u);

    startup(300u);
    foreground(308u);
    foreground(319u); /* Phase arrives in range, Toyota release window has expired. */
    assert_faulted();
    assert(rbm_h03_toyota_release_state.last_observed == 319u);
    assert(captures == 3u && services == 1u);

    startup(400u);
    foreground(408u);
    TML0CT = 421u; /* No release or output phase when the watchdog expires. */
    rbm_h03_phase_wait_callback();
    assert_faulted();
    assert(rbm_h03_toyota_release_state.last_observed == 408u);
    assert(captures == 3u && services == 1u && irq_enabled());
    assert(can_live_stops == 6u);

    uint32_t fast_filter;
    assert(factory_hydraulics_set(&rbm_h03_target_startup_gp, 1492, 2u, 0x5a5au));
    inputs_ready = RBM_U340E_STARTUP_PREPARED;
    startup(500u);
    assert(rbm_h03_application.running && can_prepared);
    assert(factory_hydraulics_get(&rbm_h03_runtime_state.gp, 1492, 2u, &fast_filter));
    assert(fast_filter == 0x5a5au);

    inputs_ready = RBM_U340E_STARTUP_S01_COLD;
    startup(600u);
    assert(rbm_h03_application.running && can_prepared && rbm_h03_runtime_state.initialized);
    assert(factory_hydraulics_get(&rbm_h03_runtime_state.gp, 1492, 2u, &fast_filter));
    assert(fast_filter == 0u);
    assert(factory_hydraulics_get(&rbm_h03_target_startup_gp, 1492, 2u, &fast_filter));
    assert(fast_filter == 0x5a5au);

    inputs_ready = 3; /* An unsupported startup kind must not prepare CAN. */
    const unsigned starts = can_starts;
    startup(700u);
    assert(!rbm_h03_application.running && !can_prepared && !rbm_h03_runtime_state.initialized);
    assert(can_starts == starts && !rbm_h03_tml0_1mhz_qualified);
    puts("H03 target platform: native startup, CAN service lifecycle, Toyota rollover and inhibition PASS");
    return 0;
}
