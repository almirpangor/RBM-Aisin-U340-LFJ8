#include "lfj8_h03_application_binding.h"
#include "lfj8_h03_input_binding.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_selector_adc.h"
#include "bench_sensor_profile.h"

#ifndef RBM_H03_APPLICATION_PROFILE
#define RBM_H03_BENCH_PROFILE_API_ONLY 1
#include "bench_application_profile.h"
#else
#include RBM_H03_APPLICATION_PROFILE
#endif

#ifndef RBM_H03_BENCH_PROFILE_API_ONLY
static const Lfj8H03InputBinding *native_input_binding(void)
{
    const Lfj8H03ToyotaInputCapture *const capture = &rbm_h03_bench_native_input_capture;
    const Lfj8H03InputBinding *const binding = capture->binding;
    return binding && binding->io == &lfj8_h03_mmio &&
        binding->adc == &rbm_h03_selector_adc_state &&
        (binding->p1_button_map || binding->selector_only) &&
        capture->proposal && capture->read && capture->ram_owned &&
        capture->ram_owned(capture->platform) == 1 ? binding : NULL;
}

/* target_platform invokes reset/sample while holding the shared H03 lock.
 * The capture entry acquires that same exclusion in the existing adapter.
 * No second selector, CAN owner, clock or input workspace is allocated. */
int rbm_h03_bench_profile_reset_inputs(void)
{
    const Lfj8H03InputBinding *const binding = native_input_binding();
    return binding && lfj8_h03_input_startup(binding, &rbm_h03_bench_native_input_startup);
}

int rbm_h03_bench_profile_sample_inputs(uint32_t now, uint8_t previous_gear)
{
    const Lfj8H03InputBinding *const binding = native_input_binding();
    return binding && lfj8_h03_input_capture(binding, NULL, now) &&
        (!previous_gear || binding->control->manual_gear == previous_gear);
}

int rbm_h03_bench_profile_capture(void *context, const Lfj8H03SensorSnapshot *sensors,
    uint32_t due_at, Lfj8H03CycleInput *input, Lfj8H03CycleLoad *load)
{
    /* target_platform supplies the native MMIO context. The existing capture
     * adapter owns exclusion and validates native producers under that lock;
     * do not sample retained state here before acquiring it. */
    const Lfj8H03InputBinding *const binding = rbm_h03_bench_native_input_capture.binding;
    if (context != lfj8_h03_mmio.context || !binding || binding->io != &lfj8_h03_mmio ||
        binding->adc != &rbm_h03_selector_adc_state) {
        return 0;
    }
    return lfj8_h03_input_capture_toyota((void *)&rbm_h03_bench_native_input_capture,
                                       sensors, due_at, input, load);
}
#endif

#define H03_AN2_RAM UINT32_C(0x804BC6)
#define H03_TML0CT UINT32_C(0x8003E0)
#define H03_PRS1 UINT32_C(0x800203)
#define H03_TM0 UINT32_C(0x8003EB)
#define H03_TM1 UINT32_C(0x800FEB)

_Static_assert(sizeof(Lfj8H03BenchLocalRaw) == 16u, "Raw commissioning ABI");

int rbm_h03_bench_raw_local_snapshot(Lfj8H03BenchLocalRaw *out)
{
    const Lfj8RegisterIo *const io = &lfj8_h03_mmio;
    if (!out || !io->enter || !io->leave || !io->read8 || !io->read16 || !io->read32) {
        return 0;
    }
    Lfj8H03BenchLocalRaw value = {0};
    const uint32_t saved = io->enter(io->context);
    value.first_tml0 = io->read32(io->context, H03_TML0CT);
    value.prs1 = io->read8(io->context, H03_PRS1);
    value.tml0_mode = io->read8(io->context, H03_TM0);
    value.tml1_mode = io->read8(io->context, H03_TM1);
    value.an2_raw = io->read16(io->context, H03_AN2_RAM);
    value.p1data = io->read8(io->context, LFJ8_H03_P1DATA_ADDRESS);
    const int stable = value.an2_raw == io->read16(io->context, H03_AN2_RAM) &&
        value.p1data == io->read8(io->context, LFJ8_H03_P1DATA_ADDRESS) &&
        value.prs1 == io->read8(io->context, H03_PRS1) &&
        value.tml0_mode == io->read8(io->context, H03_TM0) &&
        value.tml1_mode == io->read8(io->context, H03_TM1);
    value.last_tml0 = io->read32(io->context, H03_TML0CT);
    const int valid = stable && value.last_tml0 - value.first_tml0 <= LFJ8_H03_BENCH_MAX_READ_SPAN_TICKS;
    io->leave(io->context, saved);
    if (!valid) {
        return 0;
    }
    value.flags = (uint8_t)((value.an2_raw <= 1023u ? LFJ8_H03_BENCH_AN2_FITS_10_BITS : 0u) |
        (value.prs1 == 9u && value.tml0_mode == 1u && value.tml1_mode == 0x31u
            ? LFJ8_H03_BENCH_CLOCK_REGISTERS_MATCH_OEM : 0u) |
        (value.first_tml0 != value.last_tml0 ? LFJ8_H03_BENCH_TML0_MOVED : 0u));
    *out = value;
    return 1;
}
