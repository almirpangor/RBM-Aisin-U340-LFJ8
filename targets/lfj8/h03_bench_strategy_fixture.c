/* CPU fixture inputs only. The strategy and apply callbacks are production code. */
#include "lfj8_h03_application.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_target_strategy.h"

#define BYTE(address) (*(volatile uint8_t *)(uintptr_t)(address))
#define HALF(address) (*(volatile uint16_t *)(uintptr_t)(address))
#define WORD(address) (*(volatile uint32_t *)(uintptr_t)(address))
#define CHECK(condition, code) do { if (!(condition)) return (code); } while (0)
#define CLOCK_ADDRESS 0x8003E0u
#define CASE RBM_BENCH_STRATEGY_CASE

enum {
    ADJACENT_WRAP, COMBINED, MISSING_SNAPSHOT, UNOWNED, UNCONSUMED,
    MONITOR_OPEN, REPEAT, RESTART
};

void h03_stock_phase3(void);
void h03_stock_phase2(void);
void h03_stock_combined(void);
void h03_stock_arbiter(void);
void h03_stock_commit(void);

Lfj8H03Application rbm_h03_application;
Lfj8H03FastOutput rbm_h03_fast_output;
static Lfj8H03MainResult main_result;
static Lfj8H03Takeover takeover;
static Lfj8H03PhaseClock phase;
static unsigned snapshots, arbitrations, applications, inhibits;
static int owned;

static int ram_owned(void *context)
{
    (void)context;
    return owned;
}

static int qualified(void *context)
{
    (void)context;
    return 1;
}

static void write32(void *context, uint32_t address, uint32_t value)
{
    (void)context;
    WORD(address) = value;
}

static void arbitrate(void *context)
{
    (void)context;
    ++arbitrations;
    h03_stock_arbiter();
}

static void apply(void *context)
{
    (void)context;
    ++applications;
    h03_stock_commit();
}

static void inhibit(void *context)
{
    (void)context;
    ++inhibits;
}

static const Lfj8H03TakeoverOps operations = {
    .io = &lfj8_h03_mmio, .write32 = write32, .clock_ticks = lfj8_h03_tml0ct_m32r,
    .qualified = qualified, .arbitrate = arbitrate, .apply = apply, .inhibit = inhibit,
    .isolated_pwm_mask = LFJ8_H03_ALL_SPARE_PWM_ISOLATED, .phase_clock = &phase,
};

const Lfj8H03ApplicationBinding rbm_h03_application_binding = {
    .takeover_ops = &operations, .takeover = &takeover, .main = &main_result,
    .ram_owned = ram_owned,
};

int rbm_h03_target_strategy_snapshot(void *context, uint32_t sequence, Lfj8H03StrategySnapshot *out)
{
    (void)context;
    ++snapshots;
    if (CASE == MISSING_SNAPSHOT || sequence != UINT32_MAX) {
        return 0;
    }
    static const Lfj8H03SltPoint points[] = {{400, 500}, {4000, 500}};
    static const Lfj8H03SltCalibration slt = {points, 2u, 500, 800, 11000u, 14500u};
    static const Lfj8H03ActuatorCalibration calibration = {
        .binding = {LFJ8_H03_SHIFT_D, LFJ8_H03_SHIFT_E, LFJ8_H03_SHIFT_F}, .slt = &slt,
    };
    *out = (Lfj8H03StrategySnapshot){
        .actuators = &calibration, .oem = {.current = 1u}, .operating = {720, 13200u},
    };
    return 1;
}

int h03_phase_fixture(void)
{
    WORD(0x809F9C) = 0x809F9C;
    HALF(0x80621A) = 3u;
    HALF(0x800344) = 0x4444u;
    BYTE(0x800703) = 0x13u;
    const uint32_t start = UINT32_MAX - 1000u;
    WORD(CLOCK_ADDRESS) = start;
    phase = (Lfj8H03PhaseClock){
        .latest = {UINT32_MAX, start}, .consumed = UINT32_MAX, .have_release = 1u, .max_age = 8000u,
    };
    CHECK(lfj8_h03_takeover_init(&takeover, &operations, 9000u), 10);
    owned = 1;
    rbm_h03_application.running = 1u;
    main_result.command_at = rbm_h03_fast_output.command_at = start;
    main_result.valid = rbm_h03_fast_output.valid = 1u;
    main_result.shift.writes[0] = (FactoryDriverWrite){
        .channel = RBM_U340E_DONOR_CHANNEL_S1, .write_pending = 1u, .value = 1u,
    };
    main_result.shift.count = 1u;
    FactoryPressureCorrection pressure = {0};
    const FactorySLTInputs input = {.selected_p1158 = 5120, .limit_7138 = 25600};
    CHECK(factory_slt_correction_step(&pressure, &input, &rbm_h03_fast_output.slt), 11);
    if (CASE == COMBINED) {
        h03_stock_combined();
        CHECK(snapshots == 1u && arbitrations == 1u && applications == 0u &&
              inhibits == 1u && !takeover.pending, 12);
    } else {
        if (CASE == UNOWNED) {
            owned = 0;
            takeover.pending = 0xA5u;
        }
        if (CASE == UNCONSUMED) {
            --phase.consumed;
        }
        h03_stock_phase3();
        CHECK(BYTE(0x800703) == 0x13u && HALF(0x800344) == 0x4444u, 13);
        WORD(CLOCK_ADDRESS) = start + 5000u;
        phase.latest = (Lfj8H03PhaseEvent){0u, WORD(CLOCK_ADDRESS)};
        phase.consumed = 0u;
        if (CASE == MONITOR_OPEN) {
            BYTE(0x808580) = 0x20u;
        } else if (CASE == RESTART) {
            CHECK(takeover.pending && lfj8_h03_takeover_init(&takeover, &operations, 9000u), 14);
            rbm_h03_application.running = 0u;
        }
        h03_stock_phase2();
        if (CASE == ADJACENT_WRAP || CASE == REPEAT) {
            CHECK(snapshots == 1u && arbitrations == 1u && applications == 1u && !inhibits &&
                  BYTE(0x800703) == 0x93u && HALF(0x800344) == 2499u &&
                  HALF(0x800346) == 499u && !takeover.pending, 15);
            if (CASE == REPEAT) {
                h03_stock_phase2();
                CHECK(applications == 1u && inhibits == 1u && !takeover.pending, 16);
            }
            return 0;
        }
        CHECK(applications == 0u, 17);
        if (CASE == UNOWNED) {
            CHECK(!snapshots && !arbitrations && !inhibits && takeover.pending == 0xA5u, 18);
        } else if (CASE == MONITOR_OPEN || CASE == RESTART) {
            CHECK(snapshots == 1u && arbitrations == 1u && inhibits == 1u && !takeover.pending, 19);
        } else {
            CHECK(snapshots == (CASE == MISSING_SNAPSHOT) && !arbitrations &&
                  inhibits == 2u && !takeover.pending, 20);
        }
    }
    CHECK(BYTE(0x800703) == 0x13u && HALF(0x800344) == 0x4444u &&
          WORD(0x809F9C) == 0x809F9C, 21);
    return 0;
}
