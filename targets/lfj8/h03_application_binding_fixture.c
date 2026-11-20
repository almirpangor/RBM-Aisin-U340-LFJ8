/* Supplies platform objects only for the binding test in the M32R simulator. */
#include "lfj8_h03_application_binding.h"
#include "lfj8_bridge.h"
#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_sensor_target.h"
#include "lfj8_selector_adc.h"

#include <assert.h>
#include <stdio.h>

#define MMIO8(address) (*(volatile uint8_t *)(uintptr_t)(address))
#define MMIO32(address) (*(volatile uint32_t *)(uintptr_t)(address))

Lfj8H03Application rbm_h03_application = {.running = 1u};
Lfj8H03Takeover rbm_h03_takeover_state = {.pending = 1u};
Lfj8H03Cycle rbm_h03_cycle_state;
RbmU340eRuntime rbm_h03_runtime_state;
Lfj8H03CycleWorkspace rbm_h03_cycle_workspace;
Lfj8H03MainResult rbm_h03_main_result = {.valid = 1u};
Lfj8H03CycleInput rbm_h03_cycle_input;
FactoryGearState rbm_h03_target_startup_gear = {
    .driver5302 = {1, 1}, .u7184 = 20000, .u7164 = 26000, .u7186 = 3072,
    .periods = {65535, 65535, 65535, 65535, 65535, 65535},
};
FactoryHydraulics rbm_h03_target_startup_gp;
volatile Lfj8SelectorAdc rbm_h03_selector_adc_state = {
    .pending_event = LFJ8_SELECTOR_ADC_VALUE, .pending_us = 42u, .pending_raw = 500u,
};
Lfj8H03SensorTarget rbm_h03_sensor_state;
volatile Lfj8H03Atf rbm_h03_atf_state;
volatile uint8_t rbm_h03_tml0_1mhz_qualified;

static volatile Lfj8H03PhaseClock phase_clock;
static int owned;
static unsigned initialize_calls, inhibit_calls, stock_updates, take_calls, service_calls;
static const Lfj8H03SensorSnapshot *phase_sensors;
static Lfj8H03EngineRx engine_rx;
static Ta2005EngineQualifier engine_qualifier;
static CheryDtcState engine_dtc;
static Lfj8H03CanOwner engine_owner;

static int engine_context(void *context, const Lfj8H03SensorSnapshot *sensors,
    Ta2005EngineQualificationContext *engine, bool *history, uint32_t *oldest)
{
    (void)context; (void)sensors; (void)engine; (void)history; (void)oldest;
    /* This fixture holds Toyota WAIT; a qualification step here is a bug. */
    assert(0);
    return 0;
}

const Lfj8H03ApplicationEngine rbm_h03_target_engine = {
    .target = {.rx = &engine_rx, .qualifier = &engine_qualifier, .dtc = &engine_dtc,
               .can_owner = &engine_owner, .io = &lfj8_h03_mmio, .now_us = rbm_h03_atf_now_us},
    .max_age_ticks = 20u, .max_poll_gap_us = 32u, .context_for_task2 = engine_context,
};

void rbm_h03_application_foreground_hook(void);

int rbm_h03_target_ram_owned(void *context)
{
    (void)context;
    return owned;
}

int rbm_h03_target_initialize(void *context)
{
    (void)context;
    ++initialize_calls;
    assert(!rbm_h03_application.running && !rbm_h03_takeover_state.pending);
    assert(rbm_h03_selector_adc_state.pending_event == LFJ8_SELECTOR_ADC_NONE);
    assert(!rbm_h03_selector_adc_state.pending_us && rbm_h03_selector_adc_state.pending_raw == UINT16_MAX);
    return factory_hydraulics_set(&rbm_h03_target_startup_gp, -7184, 2u, rbm_h03_target_startup_gear.u7184) &&
           factory_hydraulics_set(&rbm_h03_target_startup_gp, -7164, 2u, rbm_h03_target_startup_gear.u7164) &&
           factory_hydraulics_set(&rbm_h03_target_startup_gp, -7186, 2u, rbm_h03_target_startup_gear.u7186);
}

/* The native foreground wrapper calls this modeled OEM input producer first. */
void h03_stock_foreground_inputs(void)
{
    ++stock_updates;
}

Lfj8H03ToyotaEvent rbm_h03_target_take_toyota(void *context, const Lfj8H03SensorSnapshot *sensors,
    Lfj8H03CycleInput *input, Lfj8H03CycleLoad *load, uint32_t *released_at)
{
    (void)context;
    (void)load;
    (void)released_at;
    ++take_calls;
    assert(stock_updates == take_calls);
    assert(input == &rbm_h03_cycle_input);
    assert(sensors->capture.now_tml0 == MMIO32(0x8003e0));
    assert(sensors->capture.vss.state == LFJ8_VSS_UNAVAILABLE);
    phase_sensors = sensors;
    return LFJ8_H03_TOYOTA_WAIT;
}

void rbm_h03_target_service_phase(void *context, const Lfj8H03PhaseEvent *phase,
    const Lfj8H03SensorSnapshot *sensors, const Lfj8H03MainResult *main)
{
    (void)context;
    ++service_calls;
    assert(service_calls == take_calls && sensors == phase_sensors && main == NULL);
    assert(phase->released_at == sensors->capture.now_tml0);
    phase_sensors = NULL;
}

static void inhibit(void *context)
{
    (void)context;
    ++inhibit_calls;
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

int main(void)
{
    const Lfj8H03ApplicationBinding *const binding = &rbm_h03_application_binding;
    assert(binding->takeover == &rbm_h03_takeover_state && binding->cycle == &rbm_h03_cycle_state);
    assert(binding->runtime == &rbm_h03_runtime_state && binding->workspace == &rbm_h03_cycle_workspace);
    assert(binding->main == &rbm_h03_main_result && binding->input == &rbm_h03_cycle_input);
    assert(binding->takeover_ops == &rbm_h03_target_takeover_ops);
    assert(binding->engine == &rbm_h03_target_engine);

    rbm_h03_application_cold_gate();
    rbm_h03_phase_startup_callback();
    assert(rbm_h03_application.running && rbm_h03_takeover_state.pending && rbm_h03_main_result.valid);
    assert(!initialize_calls && !inhibit_calls && rbm_h03_selector_adc_state.pending_us == 42u);

    owned = 1;
    rbm_h03_application_cold_gate();
    rbm_h03_phase_startup_callback();
    assert(!rbm_h03_application.running && !rbm_h03_takeover_state.pending && !rbm_h03_main_result.valid);
    assert(!initialize_calls && inhibit_calls == 2u && rbm_h03_selector_adc_state.pending_us == 42u);

    const struct {
        uint32_t address;
        uint8_t expected;
    } clocks[] = {{0x800203, 9u}, {0x8003eb, 0x01u}, {0x800feb, 0x31u}};
    for (unsigned i = 0; i < sizeof clocks / sizeof clocks[0]; ++i) {
        MMIO8(clocks[i].address) = clocks[i].expected;
    }
    for (unsigned i = 0; i < sizeof clocks / sizeof clocks[0]; ++i) {
        MMIO8(clocks[i].address) = 0u;
        rbm_h03_phase_startup_callback();
        assert(!initialize_calls && !rbm_h03_application.running && !rbm_h03_tml0_1mhz_qualified);
        MMIO8(clocks[i].address) = clocks[i].expected;
    }
    MMIO32(0x8003e0) = UINT32_MAX - 3u;
    rbm_h03_phase_startup_callback();
    assert(rbm_h03_application.running && rbm_h03_runtime_state.initialized && initialize_calls == 1u);
    assert(rbm_h03_takeover_state.ops == &rbm_h03_target_takeover_ops && rbm_h03_tml0_1mhz_qualified);
    assert(engine_rx.generation_source == &engine_owner.setup_generation);

    for (unsigned attempt = 0; attempt < 2; ++attempt) {
        MMIO32(0x8003e0) += 8u;
        rbm_h03_phase_release_callback(MMIO32(0x8003e0));
        rbm_h03_application_foreground_hook();
        assert(service_calls == attempt + 1u);
        if (!attempt) {
            rbm_h03_selector_adc_state.pending_event = LFJ8_SELECTOR_ADC_OVERRUN;
            rbm_h03_selector_adc_state.pending_us = MMIO32(0x8003e0);
            const uint32_t epoch = rbm_h03_sensor_state.feed.epoch;
            rbm_h03_phase_startup_callback();
            assert(rbm_h03_application.running && initialize_calls == 2u);
            assert(rbm_h03_sensor_state.feed.epoch != epoch);
        }
    }

    const uint32_t old_epoch = rbm_h03_sensor_state.feed.epoch;
    rbm_h03_sensor_state.s51.primed = 1u;
    MMIO8(0x800feb) = 0u;
    rbm_h03_phase_wait_callback();
    assert(!rbm_h03_application.running && !rbm_h03_runtime_state.initialized && !rbm_h03_tml0_1mhz_qualified);
    assert(!rbm_h03_sensor_state.s51.primed && rbm_h03_sensor_state.feed.epoch != old_epoch);
    MMIO8(0x800feb) = 0x31u;
    rbm_h03_phase_wait_callback();
    assert(!rbm_h03_application.running);

    MMIO32(0x8003e0) = 104u;
    rbm_h03_phase_startup_callback();
    assert(rbm_h03_application.running && initialize_calls == 3u);
    MMIO32(0x8003e0) = 0u;
    rbm_h03_phase_wait_callback();
    assert(!rbm_h03_application.running && !rbm_h03_tml0_1mhz_qualified);

    rbm_h03_phase_startup_callback();
    assert(rbm_h03_application.running && initialize_calls == 4u);
    MMIO32(0x8003e0) += 13u;
    rbm_h03_phase_wait_callback();
    assert(!rbm_h03_application.running && !rbm_h03_runtime_state.initialized && !rbm_h03_tml0_1mhz_qualified);
    assert(!rbm_h03_takeover_state.pending && service_calls == 2u);
    puts("H03 native binding: RAM and timer refusal, epoch revocation, wrap, restart, foreground and expiry PASS");
    return 0;
}
