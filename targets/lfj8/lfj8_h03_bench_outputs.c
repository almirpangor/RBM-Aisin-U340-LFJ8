#include "bench_output_profile.h"

#include "lfj8_h03_application.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_output_inhibit.h"

#define REG8(address) (*(volatile const uint8_t *)(uintptr_t)(address))
#define REG16(address) (*(volatile const uint16_t *)(uintptr_t)(address))

/* This provider is selected instead of the commissioned actuator provider.
 * No electrical isolation or load calibration is presumed. The normal
 * application can run its startup, Toyota cycle and CAN with outputs revoked. */
const Lfj8H03TakeoverOps rbm_h03_target_takeover_ops = {
    .io = &lfj8_h03_mmio,
    .clock_ticks = lfj8_h03_tml0ct_m32r,
    .inhibit = lfj8_h03_output_inhibit_locked,
    .phase_clock = &rbm_h03_bench_phase_clock,
};

int lfj8_h03_bench_output_snapshot(Lfj8H03BenchOutputSnapshot *snapshot)
{
    if (!snapshot) {
        return 0;
    }
    const Lfj8RegisterIo *const io = &lfj8_h03_mmio;
    const uint32_t saved = io->enter(io->context);
    const int running = lfj8_h03_application_running_locked();
    if (running) {
        snapshot->captured_at = lfj8_h03_tml0ct_m32r(io->context);
        snapshot->pressure_sense_counts = REG16(0x804BC0) >> 6;
        snapshot->pressure_reload1 = REG16(0x800344);
        snapshot->pressure_reload0 = REG16(0x800346);
        snapshot->tio9_reload1 = REG16(0x800394);
        snapshot->tio9_reload0 = REG16(0x800396);
        snapshot->shift_p3 = REG8(0x800703) & 0xe0u;
        snapshot->shift_feedback_p13 = REG8(0x80070D) & 0x0eu;
        snapshot->pressure_control = (REG8(0x80070A) & 1u) | ((REG8(0x80074A) & 1u) << 1);
        snapshot->tio9_control = (REG8(0x800709) & 1u) | ((REG8(0x800749) & 1u) << 1);
    }
    io->leave(io->context, saved);
    return running;
}
