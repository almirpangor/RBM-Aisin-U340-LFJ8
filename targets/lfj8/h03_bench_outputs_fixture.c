/* Simulator-only ownership and storage. The output provider, hooks and MMIO
 * used below are the production objects. */
#include "bench_output_profile.h"
#include "lfj8_h03_application.h"

#define REG8(address) (*(volatile uint8_t *)(uintptr_t)(address))
#define REG16(address) (*(volatile uint16_t *)(uintptr_t)(address))
#define REG32(address) (*(volatile uint32_t *)(uintptr_t)(address))

extern const Lfj8H03TakeoverOps rbm_h03_target_takeover_ops;
extern void h03_stock_phase3(void);
extern void h03_stock_phase2(void);
extern int rbm_h03_strategy_callback(void);

Lfj8H03Application rbm_h03_application;
volatile Lfj8H03PhaseClock rbm_h03_bench_phase_clock;
static Lfj8H03Takeover takeover;
static Lfj8H03MainResult main_result;
static RbmU340eRuntime runtime;
static int owned = 1;
static unsigned service_stops;

static void stop_service(void)
{
    ++service_stops;
}

int rbm_h03_sensor_clock_rebase(int qualified)
{
    (void)qualified;
    return 1;
}

static int ram_owned(void *context)
{
    (void)context;
    return owned;
}

const Lfj8H03ApplicationBinding rbm_h03_application_binding = {
    .takeover_ops = &rbm_h03_target_takeover_ops,
    .phase_config = {4000u, 6000u, 3000u, 12000u},
    .takeover = &takeover,
    .ram_owned = ram_owned,
    .stop_service_locked = stop_service,
    .main = &main_result,
    .runtime = &runtime,
};

static void seed_outputs(void)
{
    REG8(0x800703) = 0xf5u;
    REG8(0x80070A) = 0xf3u;
    REG8(0x80074A) = 0xa1u;
    REG16(0x8048CC) = 1000u;
    REG16(0x800344) = 1999u;
    REG16(0x800346) = 999u;
    REG8(0x800709) = 0xa5u;
    REG8(0x800749) = 0xb1u;
    REG16(0x8048CE) = 66u;
    REG16(0x800394) = 183u;
    REG16(0x800396) = 65u;
    REG32(0x80508C) = 0x3f800000u;
    REG32(0x805094) = 0x3f800000u;
    REG32(0x8060F0) = 0x3e800000u;
    for (uint32_t addr = 0x8063D5; addr <= 0x8063DB; addr += 3u) {
        REG8(addr) = 1u;
        REG8(addr + 2u) = 1u;
    }
}

static int revoked(void)
{
    return !takeover.pending && REG8(0x800703) == 0x15u &&
        REG8(0x80070A) == 0xf2u && REG8(0x80074A) == 0xa0u &&
        REG16(0x8048CC) == 1u && REG16(0x800344) == 2998u && !REG16(0x800346) &&
        REG8(0x800709) == 0xa4u && REG8(0x800749) == 0xb0u &&
        REG16(0x8048CE) == 1u && REG16(0x800394) == 248u && !REG16(0x800396) &&
        !REG32(0x80508C) && !REG32(0x805094) && !REG32(0x8060F0) &&
        !REG8(0x8063D5) && !REG8(0x8063D7) && !REG8(0x8063D8) &&
        !REG8(0x8063DA) && !REG8(0x8063DB) && !REG8(0x8063DD);
}

static int take_release(uint32_t at)
{
    Lfj8H03PhaseEvent event;
    REG32(0x8003E0) = at;
    rbm_h03_phase_release_callback(at);
    return lfj8_h03_takeover_take_phase(&takeover, &event) == LFJ8_H03_PHASE_EVENT &&
        event.released_at == at;
}

int main(void)
{
    const Lfj8H03ApplicationBinding *const binding = &rbm_h03_application_binding;
    const Lfj8H03TakeoverOps *const ops = binding->takeover_ops;
    const Lfj8H03OutputPlan command = {
        .discrete = {{0x8063D5, 1u}, {0x8063D8, 1u}, {0x8063DB, 1u}},
        .discrete_count = 3u, .pressure_mailbox = 0x80508C,
        .pressure_binary32 = 0x3f800000u, .pressure_request_ma = 1000u,
        .toyota_compare = 400u,
    };
    Lfj8H03BenchOutputSnapshot observation = {.captured_at = UINT32_MAX};
    REG32(0x809F9C) = 0x809F9Cu;
    REG32(0x805084) = 0x41400000u;
    REG32(0x805028) = 0x42a00000u;
    REG16(0x80621A) = 3u;
    REG32(0x8003E0) = 5000u;
    if (lfj8_h03_bench_output_snapshot(&observation) ||
        observation.captured_at != UINT32_MAX) {
        return 1;
    }
    if (ops->apply || ops->arbitrate || ops->write32 || ops->qualified ||
        ops->isolated_pwm_mask || ops->phase_clock != &rbm_h03_bench_phase_clock ||
        !lfj8_h03_phase_startup(&takeover, ops, &binding->phase_config)) {
        return 2;
    }
    rbm_h03_application.running = 1u;
    if (!take_release(10000u)) {
        return 3;
    }

    seed_outputs();
    REG8(0x80070D) = 0xabu;
    REG16(0x804BC0) = (682u << 6) | 0x3fu;
    if (!lfj8_h03_bench_output_snapshot(&observation) ||
        observation.captured_at != 10000u || observation.pressure_sense_counts != 682u ||
        observation.shift_p3 != 0xe0u || observation.shift_feedback_p13 != 0x0au ||
        observation.pressure_control != 3u || observation.tio9_control != 3u ||
        observation.pressure_reload1 != 1999u || observation.pressure_reload0 != 999u ||
        observation.tio9_reload1 != 183u || observation.tio9_reload0 != 65u ||
        REG8(0x800703) != 0xf5u || REG32(0x805094) != 0x3f800000u) {
        return 4;
    }
    if (!lfj8_h03_output_plan_matches(&command, 0u, 7u) ||
        lfj8_h03_takeover_prepare_plan(&takeover, &command, 1u, 10000u) || !revoked()) {
        return 5;
    }

    seed_outputs();
    h03_stock_phase3();
    if (!revoked()) {
        return 6;
    }
    if (!take_release(15000u)) {
        return 7;
    }
    seed_outputs();
    h03_stock_phase2();
    if (!revoked() || rbm_h03_application.running != 1u || service_stops) {
        return 8;
    }

    owned = 0;
    observation.captured_at = UINT32_MAX;
    seed_outputs();
    takeover.pending = 2u;
    if (rbm_h03_strategy_callback() != RBM_H03_HOOK_HANDLED || rbm_h03_commit_callback() != RBM_H03_HOOK_HANDLED ||
        lfj8_h03_bench_output_snapshot(&observation) ||
        observation.captured_at != UINT32_MAX ||
        REG8(0x800703) != 0xf5u || REG8(0x800749) != 0xb1u || takeover.pending != 2u) {
        return 9;
    }
    return 0;
}
