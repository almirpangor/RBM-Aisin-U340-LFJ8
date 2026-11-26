#include "lfj8_h03_application_binding.h"
#include "lfj8_h03_input_binding.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_selector_adc.h"

#ifndef RBM_H03_APPLICATION_PROFILE
#error "Use an explicit native H03 application profile"
#else
#include RBM_H03_APPLICATION_PROFILE

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
