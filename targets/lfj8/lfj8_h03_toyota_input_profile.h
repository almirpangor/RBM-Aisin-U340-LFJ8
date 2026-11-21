#ifndef RBM_LFJ8_H03_TOYOTA_INPUT_PROFILE_H
#define RBM_LFJ8_H03_TOYOTA_INPUT_PROFILE_H

#include "lfj8_h03_input_binding.h"
#include "lfj8_h03_mmio.h"

/* Include from the qualified application profile after declaring its owned
 * Lfj8H03ToyotaInputCapture and naming it with this macro. The platform keeps
 * the native MMIO context for RAM and clock checks. */
#ifndef RBM_H03_PROFILE_TOYOTA_INPUT_CAPTURE
#error "Name the qualified Lfj8H03ToyotaInputCapture in RBM_H03_PROFILE_TOYOTA_INPUT_CAPTURE"
#endif

static inline int lfj8_h03_profile_sample_toyota_inputs(uint32_t now, uint8_t requested_gear)
{
    const Lfj8H03ToyotaInputCapture *const capture = &RBM_H03_PROFILE_TOYOTA_INPUT_CAPTURE;
    const Lfj8H03InputBinding *const binding = capture->binding;
    return binding && binding->io == &lfj8_h03_mmio && binding->p1_button_map &&
        capture->ram_owned && capture->ram_owned(capture->platform) == 1 &&
        lfj8_h03_input_capture(binding, NULL, now) &&
        (!requested_gear || binding->control->manual_gear == requested_gear);
}

static inline int lfj8_h03_profile_capture_toyota(void *context,
    const Lfj8H03SensorSnapshot *sensors, uint32_t due_at,
    Lfj8H03CycleInput *input, Lfj8H03CycleLoad *load)
{
    (void)context;
    return lfj8_h03_input_capture_toyota((void *)&RBM_H03_PROFILE_TOYOTA_INPUT_CAPTURE,
                                        sensors, due_at, input, load);
}

#define RBM_H03_PROFILE_SAMPLE_TOYOTA_INPUTS lfj8_h03_profile_sample_toyota_inputs
#define RBM_H03_PROFILE_CAPTURE_TOYOTA lfj8_h03_profile_capture_toyota

#endif
