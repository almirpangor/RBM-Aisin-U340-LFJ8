/* Simulator storage and platform inputs for the native output binding. */
#include "lfj8_h03_application_binding.h"
#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_selector_adc.h"

#define REG8(address) (*(volatile uint8_t *)(uintptr_t)(address))
#define REG16(address) (*(volatile uint16_t *)(uintptr_t)(address))
#define REG32(address) (*(volatile uint32_t *)(uintptr_t)(address))

Lfj8H03Application rbm_h03_application;
Lfj8H03Takeover rbm_h03_takeover_state;
Lfj8H03Cycle rbm_h03_cycle_state;
RbmU340eRuntime rbm_h03_runtime_state;
Lfj8H03CycleWorkspace rbm_h03_cycle_workspace;
Lfj8H03MainResult rbm_h03_main_result;
Lfj8H03CycleInput rbm_h03_cycle_input;
FactoryGearState rbm_h03_target_startup_gear;
FactoryHydraulics rbm_h03_target_startup_gp;
const Lfj8H03ApplicationEngine rbm_h03_target_engine = {.max_age_ticks = 0u};
volatile Lfj8SelectorAdc rbm_h03_selector_adc_state;
volatile Lfj8H03PhaseClock fixture_phase_clock;
volatile uint8_t rbm_h03_tml0_1mhz_qualified;

static int owned;

extern void h03_stock_commit_caller(void);
extern void h03_stock_phase2(void);

int rbm_h03_target_ram_owned(void *context)
{
    (void)context;
    return owned;
}

int rbm_h03_target_clock_ready(void *context)
{
    (void)context;
    return 0;
}

int rbm_h03_target_initialize(void *context)
{
    (void)context;
    return 0;
}

Lfj8H03ToyotaEvent rbm_h03_target_take_toyota(void *context, const Lfj8H03SensorSnapshot *sensors,
    Lfj8H03CycleInput *input, Lfj8H03CycleLoad *load, uint32_t *released_at)
{
    (void)context; (void)sensors; (void)input; (void)load; (void)released_at;
    return LFJ8_H03_TOYOTA_WAIT;
}

void rbm_h03_target_service_phase(void *context, const Lfj8H03PhaseEvent *phase,
    const Lfj8H03SensorSnapshot *sensors, const Lfj8H03MainResult *main)
{
    (void)context; (void)phase; (void)sensors; (void)main;
}

enum {
    P3DATA = 0x800703,
    P9DATA = 0x800709,
    P9SEL = 0x800749,
    P10DATA = 0x80070A,
    P10SEL = 0x80074A,
    TIO4RL1 = 0x800344,
    TIO4RL0 = 0x800346,
    TIO9RL1 = 0x800394,
    TIO9RL0 = 0x800396,
    TIO9_WIDTH = 0x8048CE,
    TIO9_PROPOSAL = 0x8060F0,
    TIO9_ROM_PROPOSAL = 0x0199C0,
    TML0CT = 0x8003E0,
    TML0CR = 0x8003EB,
    SHIFT_D_PROPOSAL = 0x8063D5,
    SHIFT_D_FINAL = 0x8063D7,
    PRESSURE_PROPOSAL = 0x80508C,
    PRESSURE_FINAL = 0x805094,
    PRESSURE_WIDTH = 0x8048CC,
    FLASH_CONTROL = 0x8007E2,
    ONE_AMP = 0x3F800000,
};

static const Lfj8H03OutputPlan plan = {
    .discrete = {{SHIFT_D_PROPOSAL, 1u}},
    .discrete_count = 1u,
    .pressure_mailbox = PRESSURE_PROPOSAL,
    .pressure_binary32 = ONE_AMP,
    .pressure_request_ma = 1000u,
    .toyota_compare = 400u,
};

static void seed_tio9(void)
{
    REG8(P9DATA) = 0xa5u;
    REG8(P9SEL) = 0xb1u;
    REG16(TIO9_WIDTH) = 66u;
    REG16(TIO9RL1) = 183u;
    REG16(TIO9RL0) = 65u;
    REG32(TIO9_PROPOSAL) = REG32(TIO9_ROM_PROPOSAL);
}

static void seed_latched_outputs(void)
{
    REG8(P3DATA) = 0x95u;
    REG8(P10DATA) = 0xf3u;
    REG8(P10SEL) = 0xa1u;
    REG16(PRESSURE_WIDTH) = 1000u;
    REG16(TIO4RL1) = 1999u;
    REG16(TIO4RL0) = 999u;
    REG32(PRESSURE_PROPOSAL) = ONE_AMP;
    REG32(PRESSURE_FINAL) = ONE_AMP;
    seed_tio9();
}

static int tio9_revoked(void)
{
    return REG8(P9DATA) == 0xa4u && REG8(P9SEL) == 0xb0u &&
        REG16(TIO9_WIDTH) == 1u && REG16(TIO9RL1) == 248u && REG16(TIO9RL0) == 0u &&
        REG32(TIO9_PROPOSAL) == 0u;
}

static int outputs_revoked(void)
{
    return !rbm_h03_takeover_state.pending && REG8(P3DATA) == 0x15u &&
        REG8(P10DATA) == 0xf2u && REG8(P10SEL) == 0xa0u &&
        REG16(PRESSURE_WIDTH) == 1u && REG16(TIO4RL1) == 2998u && REG16(TIO4RL0) == 0u &&
        !REG8(SHIFT_D_PROPOSAL) && !REG8(SHIFT_D_FINAL) &&
        !REG32(PRESSURE_PROPOSAL) && !REG32(PRESSURE_FINAL) && tio9_revoked();
}

static int take_release(uint32_t generation)
{
    Lfj8H03PhaseEvent event;
    const uint32_t now = REG32(TML0CT);
    rbm_h03_phase_release_callback(now);
    return lfj8_h03_takeover_take_phase(&rbm_h03_takeover_state, &event) == LFJ8_H03_PHASE_EVENT &&
        event.sequence == generation && event.released_at == now;
}

static int advance_release(void)
{
    REG32(TML0CT) += 10u; /* Fixture cadence within the profile's 8–12 tick window. */
    return take_release(fixture_phase_clock.latest.sequence + 1u);
}

static int stage_output(Lfj8H03Takeover *state, uint32_t generation)
{
    return advance_release() &&
        lfj8_h03_takeover_prepare_plan(state, &plan, generation, REG32(TML0CT));
}

int main(void)
{
    const Lfj8H03ApplicationBinding *const binding = &rbm_h03_application_binding;
    const Lfj8H03TakeoverOps *const ops = binding->takeover_ops;
    Lfj8H03Takeover *const state = binding->takeover;
    REG32(0x809F9C) = 0x809F9Cu; /* OEM critical-section stack. */
    REG32(0x805084) = 0x41400000u; /* OEM VBAT binary32 12 V. */
    REG16(0x80621A) = 3u; /* Completed OEM startup. */
    REG8(P3DATA) = 0x15u;
    REG8(P10DATA) = 0xf2u;
    REG8(P10SEL) = 0xa0u;
    REG8(0x800203) = 9u;
    REG8(TML0CR) = 1u;
    REG8(0x800FEB) = 0x31u;
    REG32(TML0CT) = UINT32_MAX - 5u;
    if (ops != &rbm_h03_target_takeover_ops || ops->io != &lfj8_h03_mmio ||
        ops->phase_clock != &fixture_phase_clock || ops->qualified(NULL)) {
        return 1;
    }

    owned = 1;
    state->pending = 1u;
    seed_latched_outputs();
    h03_stock_commit_caller();
    if (!outputs_revoked()) {
        return 14;
    }
    if (!lfj8_h03_phase_startup(state, ops, &binding->phase_config)) {
        return 1;
    }
    /* The logical command serial and the H03 release serial are independent.
     * The first pair of phases runs across the H03 release serial's rollover. */
    fixture_phase_clock.latest.sequence = UINT32_MAX - 1u;
    fixture_phase_clock.consumed = UINT32_MAX - 1u;
    rbm_h03_application.running = 1u;
    rbm_h03_tml0_1mhz_qualified = 1u;
    REG32(TML0CT) = 2u; /* Same timebase and release continue across wrap. */
    if (!take_release(UINT32_MAX) ||
        !lfj8_h03_takeover_prepare_plan(state, &plan, 1u, 2u) ||
        REG8(P3DATA) != 0x15u || REG8(P10SEL) != 0xa0u ||
        REG8(SHIFT_D_PROPOSAL) != 1u || REG8(SHIFT_D_FINAL) != 1u ||
        REG32(PRESSURE_PROPOSAL) != ONE_AMP || REG32(PRESSURE_FINAL) != ONE_AMP) {
        return 2;
    }
    if (!advance_release() || fixture_phase_clock.latest.sequence != 0u) {
        return 3;
    }
    /* The OEM phase produces the TIO9 proposal before the commit call. */
    REG32(0x805028) = 0x42a00000u; /* 80 C, an H03 interpolation knot. */
    h03_stock_phase2();
    const uint16_t tio9_width = REG16(TIO9_WIDTH);
    if (state->pending || REG8(P3DATA) != 0x95u ||
        REG8(P10SEL) != 0xa1u || REG16(PRESSURE_WIDTH) != 1000u ||
        REG16(TIO4RL1) != 1999u || REG16(TIO4RL0) != 999u ||
        REG8(P9SEL) != 0xb1u || tio9_width < 3u || tio9_width > 248u ||
        REG16(TIO9RL1) != 249u - tio9_width || REG16(TIO9RL0) != tio9_width - 1u ||
        !REG32(TIO9_PROPOSAL)) {
        return 3;
    }
    h03_stock_commit_caller();
    if (!outputs_revoked()) {
        return 13;
    }

    if (!stage_output(state, 2u) || !advance_release()) {
        return 4;
    }
    seed_tio9();
    REG8(TML0CR) = 0u;
    h03_stock_commit_caller();
    if (!outputs_revoked()) {
        return 5;
    }
    REG8(TML0CR) = 1u;
    h03_stock_commit_caller();
    if (!outputs_revoked()) {
        return 6;
    }

    if (!stage_output(state, 3u) || !advance_release()) {
        return 7;
    }
    seed_latched_outputs();
    REG8(FLASH_CONTROL) = 1u;
    h03_stock_commit_caller();
    if (!outputs_revoked()) {
        return 8;
    }
    REG8(FLASH_CONTROL) = 0u;

    if (!stage_output(state, 4u) || !advance_release()) {
        return 9;
    }
    seed_latched_outputs();
    rbm_h03_application.running = 0u;
    h03_stock_commit_caller();
    if (!outputs_revoked()) {
        return 10;
    }
    rbm_h03_application.running = 1u;
    if (!stage_output(state, 5u) || !advance_release()) {
        return 11;
    }
    seed_tio9();
    owned = 0;
    h03_stock_commit_caller();
    if (ops->qualified(NULL) || !state->pending || state->generation != 5u ||
        REG8(P3DATA) != 0x15u || REG8(P10SEL) != 0xa0u ||
        REG32(PRESSURE_FINAL) != ONE_AMP || REG8(P9DATA) != 0xa5u || REG8(P9SEL) != 0xb1u ||
        REG16(TIO9_WIDTH) != 66u || REG16(TIO9RL1) != 183u || REG16(TIO9RL0) != 65u ||
        REG32(TIO9_PROPOSAL) != REG32(TIO9_ROM_PROPOSAL)) {
        return 11;
    }
    owned = 1;
    if (!advance_release()) {
        return 12;
    }
    h03_stock_commit_caller();
    if (!outputs_revoked()) {
        return 12;
    }
    if (!stage_output(state, 6u)) {
        return 15;
    }
    h03_stock_commit_caller();
    if (!outputs_revoked()) {
        return 15;
    }
    if (!stage_output(state, 7u)) {
        return 16;
    }
    REG32(TML0CT) += 10u;
    rbm_h03_phase_release_callback(REG32(TML0CT));
    h03_stock_commit_caller();
    if (!outputs_revoked() || fixture_phase_clock.latest.sequence == fixture_phase_clock.consumed) {
        return 16;
    }
    return 0;
}
