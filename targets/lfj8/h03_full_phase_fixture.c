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
static const Lfj8H03OutputPlan request = {
    .discrete = {{.mailbox = 0x8063D5, .on = 1}, {.mailbox = 0x8063DB, .on = 1}},
    .discrete_count = 2,
    .pressure_mailbox = 0x80508C,
    .pressure_binary32 = 0x3F000000,
    .pressure_request_ma = 500,
    .toyota_compare = 2200,
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
    prepared = lfj8_h03_takeover_prepare(&takeover, &request, 5u, 1u, command_at);
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

    CHECK(lfj8_h03_takeover_init(&takeover, &operations, SAMPLE_AGE), 10);

    if (scenario == SCENARIO_COMBINED_ENTRY) {
        h03_stock_combined();
    } else {
        h03_stock_phase3();
        CHECK(RAM8(P3DATA) == initial_p3 && RAM16(TIO4RL0) == initial_reload, 11);
        if (scenario != SCENARIO_STARTUP_SKIP) {
            CHECK(prepared && strategy_callbacks == 1u && arbiter_calls == 1u, 12);
            CHECK(RAM8(0x8063D7) == 1u && RAM8(0x8063DA) == 0u &&
                  RAM8(0x8063DD) == 1u && RAM32(0x805094) == UINT32_C(0x3F000000), 13);
        }
        RAM32(TML0CT) = command_at + 5000u;
        switch (scenario) {
        case SCENARIO_TIMEOUT: RAM32(TML0CT) = command_at + SAMPLE_AGE; break;
        case SCENARIO_LATE_FAULT: RAM8(0x806356) = 1; break;
        case SCENARIO_FINAL_CHANGED: RAM8(0x8063DA) = 1; break;
        case SCENARIO_AUTHORITY_LOST: permitted = 0; break;
        default: break;
        }
        h03_stock_phase2();
    }

    CHECK(RAM32(OEM_CRITICAL_STACK) == OEM_CRITICAL_STACK, 14);
    if (scenario == SCENARIO_STARTUP_SKIP) {
        CHECK(strategy_callbacks == 0u && commit_callbacks == 0u &&
              arbiter_calls == 0u && apply_calls == 0u && inhibit_calls == 0u, 15);
    } else {
        CHECK(strategy_callbacks == 1u && commit_callbacks == 1u && arbiter_calls == 1u, 16);
        if (scenario == SCENARIO_NORMAL || scenario == SCENARIO_REPEAT ||
            scenario == SCENARIO_COMBINED_ENTRY) {
            CHECK(applied && apply_calls == 1u && inhibit_calls == 0u, 17);
            CHECK(RAM8(P3DATA) == (initial_p3 | 0xA0u), 18);
            /* The timer stores interval minus one in each reload register. */
            CHECK(RAM16(TIO4RL0) == 2499u && RAM16(TIO4RL1) == 499u &&
                  (RAM8(P10SEL) & 1u), 19);
            if (scenario == SCENARIO_REPEAT) {
                h03_stock_phase2();
                CHECK(!applied && commit_callbacks == 2u && apply_calls == 1u &&
                      inhibit_calls == 1u, 20);
                CHECK(RAM8(P3DATA) == (initial_p3 | 0xA0u) && RAM16(TIO4RL0) == 2499u, 21);
            }
            return 0;
        }
        CHECK(!applied && apply_calls == 0u && inhibit_calls == 1u, 22);
    }
    CHECK(RAM8(P3DATA) == initial_p3 && RAM16(TIO4RL0) == initial_reload, 23);
    return 0;
}
