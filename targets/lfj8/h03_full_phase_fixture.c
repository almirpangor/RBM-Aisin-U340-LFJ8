#include <stdint.h>

#include "h03_native_hooks.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_takeover.h"

#define RAM8(addr) (*(volatile uint8_t *)(uintptr_t)(addr))
#define RAM16(addr) (*(volatile uint16_t *)(uintptr_t)(addr))
#define RAM32(addr) (*(volatile uint32_t *)(uintptr_t)(addr))
#define CHECK(condition, code) do { if (!(condition)) return (code); } while (0)

enum {
    SCENARIO_NORMAL,
    SCENARIO_TIMEOUT,
    SCENARIO_LATE_FAULT,
    SCENARIO_FINAL_CHANGED,
    SCENARIO_AUTHORITY_LOST,
    SCENARIO_REPEAT,
    SCENARIO_STARTUP_SKIP,
    SCENARIO_COMBINED_ENTRY,
    SCENARIO_P3_CHANGED,
    SCENARIO_NO_CALIBRATION,
    SCENARIO_WRONG_ORDER,
};

enum {
    TML0CT = 0x8003E0,
    P3DATA = 0x800703,
    P10SEL = 0x80074A,
    TIO4RL0 = 0x800344,
    TIO4RL1 = 0x800346,
    STARTUP_COUNT = 0x80621A,
    OEM_CRITICAL_STACK = 0x809F9C,
    SAMPLE_AGE = 9000,
};

extern void h03_stock_phase3(void);
extern void h03_stock_phase2(void);
extern void h03_stock_combined(void);
extern void h03_stock_arbiter(void);
extern void h03_stock_commit(void);

static Lfj8H03Takeover takeover;
static uint32_t command_at;
static uint8_t permitted;
static unsigned arbiter_calls, apply_calls, inhibit_calls, strategy_callbacks, commit_callbacks;
static int prepared, applied;
static Lfj8H03OutputResult plan_status;
static uint16_t toyota_compare;
static const FactoryDriverState drivers[3] = {
    {.state_5302 = 1}, {.state_5302 = 1}, {.state_5302 = 1},
};
static const RbmU340eHydraulicInput donor = {
    .qualified = 1u,
    .slt_inputs = {.selected_p1158 = 5120, .limit_7138 = 25600},
};
/* Test-only points, selected so the independently checked Toyota compare 652
 * reaches exactly 500 mA. They represent no real solenoid calibration. */
static const Lfj8H03SltPoint points[] = {{400, 800}, {652, 500}, {4000, 200}};
static const Lfj8H03SltCalibration calibration = {
    points, sizeof points / sizeof points[0], 500, 800, 11000, 14500,
};

static void write_word(void *context, uint32_t address, uint32_t value)
{
    (void)context;
    RAM32(address) = value;
}

static uint32_t clock_ticks(void *context)
{
    return lfj8_h03_mmio.read32(context, TML0CT);
}

static int qualified(void *context)
{
    (void)context;
    return permitted;
}

static void arbitrate(void *context)
{
    (void)context;
    ++arbiter_calls;
    h03_stock_arbiter();
}

static void apply(void *context)
{
    (void)context;
    ++apply_calls;
    h03_stock_commit();
}

static void inhibit(void *context)
{
    /* Observe the request at the fixture boundary. No physical inhibit is
     * claimed and the model does not alter or clear the OEM driver state. */
    (void)context;
    ++inhibit_calls;
}

int rbm_h03_strategy_callback(void)
{
    ++strategy_callbacks;
    RbmU340eOutputState driver_state;
    RbmU340eHydraulicOutput request;
    Lfj8H03OutputPlan plan;
    const Lfj8H03OemOutputState oem = {.current = 1};
    const Lfj8H03OperatingPoint operating = {720, 13200};
    const Lfj8H03OutputBinding binding = H03_PHASE_SCENARIO == SCENARIO_WRONG_ORDER ?
        (Lfj8H03OutputBinding){LFJ8_H03_SHIFT_E, LFJ8_H03_SHIFT_D, LFJ8_H03_SHIFT_F} :
        (Lfj8H03OutputBinding){LFJ8_H03_SHIFT_D, LFJ8_H03_SHIFT_E, LFJ8_H03_SHIFT_F};
    const Lfj8H03SltCalibration *curve = H03_PHASE_SCENARIO == SCENARIO_NO_CALIBRATION ?
        NULL : &calibration;
    plan_status = LFJ8_H03_OUTPUT_INVALID;
    if (rbm_u340e_outputs_init(&driver_state, drivers) &&
        rbm_u340e_outputs_step(&driver_state, &donor, &request)) {
        plan_status = lfj8_h03_plan_outputs(&request, &binding, &oem, curve, operating, &plan);
    }
    if (plan_status == LFJ8_H03_OUTPUT_OK) {
        toyota_compare = plan.toyota_compare;
        prepared = lfj8_h03_takeover_prepare(&takeover, &plan, 3u, 1u, command_at);
    } else {
        prepared = lfj8_h03_takeover_prepare(&takeover, NULL, 3u, 1u, command_at);
    }
    return RBM_H03_HOOK_HANDLED;
}

int rbm_h03_commit_callback(void)
{
    ++commit_callbacks;
    applied = lfj8_h03_takeover_apply(&takeover, 1u);
    return RBM_H03_HOOK_HANDLED;
}

int h03_phase_fixture(void)
{
    static const Lfj8H03TakeoverOps operations = {
        .io = &lfj8_h03_mmio, .write32 = write_word, .clock_ticks = clock_ticks,
        .qualified = qualified, .arbitrate = arbitrate, .apply = apply, .inhibit = inhibit,
        .isolated_pwm_mask = LFJ8_H03_ALL_SPARE_PWM_ISOLATED,
    };
    const unsigned scenario = H03_PHASE_SCENARIO;
    const uint8_t initial_p3 = 0x13;
    const uint16_t initial_reload = 0x4444;

    RAM32(OEM_CRITICAL_STACK) = OEM_CRITICAL_STACK;
    RAM16(STARTUP_COUNT) = scenario == SCENARIO_STARTUP_SKIP ? 2u : 3u;
    RAM8(P3DATA) = initial_p3;
    RAM16(TIO4RL0) = initial_reload;
    RAM32(TML0CT) = UINT32_MAX - 1000u;
    command_at = RAM32(TML0CT);
    permitted = 1;

    const int invalid_prepare = scenario == SCENARIO_NO_CALIBRATION || scenario == SCENARIO_WRONG_ORDER;
    CHECK(lfj8_h03_takeover_init(&takeover, &operations, SAMPLE_AGE), 10);

    if (scenario == SCENARIO_COMBINED_ENTRY) {
        h03_stock_combined();
    } else {
        h03_stock_phase3();
        CHECK(RAM8(P3DATA) == initial_p3 && RAM16(TIO4RL0) == initial_reload, 11);
        if (scenario != SCENARIO_STARTUP_SKIP && !invalid_prepare) {
            CHECK(prepared && strategy_callbacks == 1u && arbiter_calls == 1u, 12);
            CHECK(plan_status == LFJ8_H03_OUTPUT_OK && toyota_compare == 652u &&
                  RAM8(0x8063D7) == 1u && RAM8(0x8063DA) == 1u &&
                  RAM8(0x8063DD) == 0u && RAM32(0x805094) == UINT32_C(0x3F000000), 13);
        }
        RAM32(TML0CT) = command_at + 5000u;
        switch (scenario) {
        case SCENARIO_TIMEOUT: RAM32(TML0CT) = command_at + SAMPLE_AGE; break;
        case SCENARIO_LATE_FAULT: RAM8(0x806356) = 1; break;
        case SCENARIO_FINAL_CHANGED: RAM8(0x8063DA) ^= 1u; break;
        case SCENARIO_AUTHORITY_LOST: permitted = 0; break;
        case SCENARIO_P3_CHANGED: RAM8(P3DATA) ^= 0x20u; break;
        default: break;
        }
        h03_stock_phase2();
    }

    CHECK(RAM32(OEM_CRITICAL_STACK) == OEM_CRITICAL_STACK, 14);
    if (scenario == SCENARIO_STARTUP_SKIP) {
        CHECK(strategy_callbacks == 0u && commit_callbacks == 0u &&
              arbiter_calls == 0u && apply_calls == 0u && inhibit_calls == 0u, 15);
    } else if (invalid_prepare) {
        const Lfj8H03OutputResult expected = scenario == SCENARIO_NO_CALIBRATION ?
            LFJ8_H03_OUTPUT_OUTSIDE_CALIBRATION : LFJ8_H03_OUTPUT_OK;
        CHECK(plan_status == expected && !prepared && !applied && strategy_callbacks == 1u &&
              commit_callbacks == 1u && arbiter_calls == 0u && apply_calls == 0u &&
              inhibit_calls == 2u, 24);
    } else {
        CHECK(strategy_callbacks == 1u && commit_callbacks == 1u && arbiter_calls == 1u, 16);
        if (scenario == SCENARIO_NORMAL || scenario == SCENARIO_REPEAT ||
            scenario == SCENARIO_COMBINED_ENTRY) {
            CHECK(applied && apply_calls == 1u && inhibit_calls == 0u, 17);
            CHECK(RAM8(P3DATA) == (initial_p3 | 0xC0u), 18);
            /* The timer stores interval minus one in each reload register. */
            CHECK(RAM16(TIO4RL0) == 2499u && RAM16(TIO4RL1) == 499u &&
                  (RAM8(P10SEL) & 1u), 19);
            if (scenario == SCENARIO_REPEAT) {
                h03_stock_phase2();
                CHECK(!applied && commit_callbacks == 2u && apply_calls == 1u &&
                      inhibit_calls == 1u, 20);
                CHECK(RAM8(P3DATA) == (initial_p3 | 0xC0u) && RAM16(TIO4RL0) == 2499u, 21);
            }
            return 0;
        }
        CHECK(!applied && apply_calls == 0u && inhibit_calls == 1u, 22);
    }
    const uint8_t untouched_p3 = scenario == SCENARIO_P3_CHANGED ?
        (uint8_t)(initial_p3 ^ 0x20u) : initial_p3;
    CHECK(RAM8(P3DATA) == untouched_p3 && RAM16(TIO4RL0) == initial_reload, 23);
    return 0;
}
