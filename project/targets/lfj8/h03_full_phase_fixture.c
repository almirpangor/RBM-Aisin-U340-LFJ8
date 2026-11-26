#include <stdint.h>

#include "h03_native_hooks.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_takeover.h"
#include "lfj8_h03_cycle.h"

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
    SCENARIO_MONITOR_OPEN,
    SCENARIO_MONITOR_PENDING_COPY,
    SCENARIO_FLASH_OVERLAY,
    SCENARIO_DONOR_MAIN_TO_OUTPUT,
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
static Lfj8H03MainResult main_result;
static Lfj8H03FastOutput fast_result;
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
static const Lfj8H03SltPoint lifecycle_points[] = {{400, 500}, {4000, 500}};
static const Lfj8H03SltCalibration lifecycle_fixture_calibration = {
    lifecycle_points, sizeof lifecycle_points / sizeof lifecycle_points[0], 500, 800, 11000, 14500,
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
    const Lfj8H03OemOutputState oem = {.current = 1};
    const Lfj8H03OperatingPoint operating = {720, 13200};
    if (H03_PHASE_SCENARIO == SCENARIO_DONOR_MAIN_TO_OUTPUT) {
        const Lfj8H03ActuatorCalibration fixture = {
            .binding = {LFJ8_H03_SHIFT_D, LFJ8_H03_SHIFT_E, LFJ8_H03_SHIFT_F},
            .slt = &lifecycle_fixture_calibration,
        };
        prepared = lfj8_h03_cycle_prepare_outputs(&takeover, &main_result, &fast_result,
                                                   &fixture, &oem, operating, 1u);
        return RBM_H03_HOOK_HANDLED;
    }
    RbmU340eOutputState driver_state;
    RbmU340eHydraulicOutput request;
    Lfj8H03OutputPlan plan;
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

static int donor_main_fixture(void)
{
    static RbmU340eRuntime runtime;
    static Lfj8H03CycleWorkspace workspace;
    static FactoryHydraulics startup_gp;
    static const FactoryGearState gear = {
        .driver5302 = {1, 1}, .u7184 = 20000u, .u7164 = 26000u, .u7186 = 3072u,
        .periods = {65535, 65535, 65535, 65535, 65535, 65535},
    };
    const RbmU340eRangeState range = {0};
    Lfj8H03Cycle cycle;
    Lfj8H03CycleInput input = {
        .engine = {.fa62 = 9600, .f9b8 = 137, .coherent = 1},
        .command_at = command_at, .selector = RBM_U340E_SELECTOR_N,
        .range_5722 = 5u, .qualified = 1u,
    };
    CHECK(factory_hydraulics_set(&startup_gp, -7184, 2u, gear.u7184) &&
          factory_hydraulics_set(&startup_gp, -7164, 2u, gear.u7164) &&
          factory_hydraulics_set(&startup_gp, -7186, 2u, gear.u7186) &&
          rbm_u340e_runtime_init(&runtime, &gear, &startup_gp) &&
          lfj8_h03_cycle_init(&cycle, &range, 0u), 30);
    unsigned main_calls = 0;
    while (input.event < 42u && main_calls < 3u) {
        ++input.event;
        const Lfj8H03CycleResult status =
            lfj8_h03_cycle_tick(&cycle, &runtime, &input, &workspace, &main_result);
        CHECK(status != LFJ8_H03_CYCLE_FAULT, 31);
        if (status == LFJ8_H03_CYCLE_MAIN && ++main_calls == 2u) {
            input.selector = RBM_U340E_SELECTOR_D;
            input.range_5722 = 1u;
        }
    }
    CHECK(main_calls == 3u && main_result.gear_4848 == 1u && main_result.shift.count == 2u &&
          main_result.shift.writes[0].value == 1u && main_result.shift.writes[1].value == 0u, 32);
    FactorySLTInputs slt_input;
    FactoryPressureCorrection pressure = {0};
    FactorySTOutputState st = {0};
    FactoryDriverBatch batch;
    FactoryDriverState driver = {.state_5302 = 1u};
    CHECK(lfj8_h03_cycle_slt_inputs(&runtime.gp, &slt_input) &&
          factory_slt_correction_step(&pressure, &slt_input, &fast_result.slt) &&
          factory_st_output(&st, 1, &batch) && batch.count == 1u &&
          factory_driver_dispatch(&driver, batch.commands[0].mode, batch.commands[0].channel,
                                  &fast_result.st), 33);
    fast_result.command_at = command_at;
    fast_result.valid = 1u;
    h03_stock_phase3();
    CHECK(prepared && arbiter_calls == 1u && strategy_callbacks == 1u && !inhibit_calls &&
          RAM8(0x8063D7) == 1u && RAM8(0x8063DA) == 0u && RAM8(0x8063DD) == 0u, 34);
    RAM32(TML0CT) = command_at + 5000u;
    h03_stock_phase2();
    CHECK(applied && apply_calls == 1u && commit_callbacks == 1u && !inhibit_calls &&
          RAM8(P3DATA) == 0x93u && RAM16(TIO4RL0) == 2499u && RAM16(TIO4RL1) == 499u, 35);
    return 0;
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
    RAM8(0x8007E2) = 0;
    RAM8(0x808580) = 0;
    RAM32(0x808DA4) = 0;
    RAM32(0x808DA8) = 0;
    RAM16(STARTUP_COUNT) = scenario == SCENARIO_STARTUP_SKIP ? 2u : 3u;
    RAM8(P3DATA) = initial_p3;
    RAM16(TIO4RL0) = initial_reload;
    RAM32(TML0CT) = UINT32_MAX - 1000u;
    command_at = RAM32(TML0CT);
    permitted = 1;

    const int invalid_prepare = scenario == SCENARIO_NO_CALIBRATION || scenario == SCENARIO_WRONG_ORDER;
    CHECK(lfj8_h03_takeover_init(&takeover, &operations, SAMPLE_AGE), 10);
    if (scenario == SCENARIO_DONOR_MAIN_TO_OUTPUT) {
        return donor_main_fixture();
    }

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
        case SCENARIO_MONITOR_OPEN: RAM8(0x808580) = 0x20; break;
        case SCENARIO_MONITOR_PENDING_COPY:
            RAM8(0x808580) = 0x10;
            RAM32(0x808DA8) = 257;
            break;
        case SCENARIO_FLASH_OVERLAY: RAM8(0x8007E2) = 1; break;
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
