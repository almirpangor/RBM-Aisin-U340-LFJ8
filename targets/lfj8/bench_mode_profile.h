#ifndef RBM_LFJ8_H03_BENCH_MODE_PROFILE_H
#define RBM_LFJ8_H03_BENCH_MODE_PROFILE_H

#include "lfj8_h03_input_binding.h"

/* H03 engineering settings for bench commissioning. The application profile
 * binds this selector and one startup object to its existing owned ADC,
 * range, button and proposal fields. Independent range and load providers
 * are required in both configurations. */
extern const RbmU340eSelectorProfile lfj8_h03_bench_selector;
extern const Lfj8H03InputStartup lfj8_h03_bench_selector_startup;
extern const Lfj8H03InputStartup lfj8_h03_bench_manual_startup;

/* Include from RBM_H03_APPLICATION_PROFILE after declaring the owned
 * objects and defining the macros below. DRIVER_READ has the signature of
 * Lfj8H03ToyotaInputCapture.read and receives the native NULL context. It
 * supplies an independent P/N contact as the normalized GP-5722.2 bit.
 * Selecting manual operation additionally requires an explicit P1 map and
 * a positive, qualified shift expiration in TML0 microseconds. */
#ifdef RBM_H03_BENCH_DRIVER_READ
#include "lfj8_h03_application_binding.h"
#include "lfj8_h03_mmio.h"

#if !defined(RBM_H03_BENCH_RANGE_CONTROL) || !defined(RBM_H03_BENCH_BUTTON_FILTER) || \
    !defined(RBM_H03_BENCH_INPUT_PROPOSAL) || !defined(RBM_H03_BENCH_RANGE_LIMITS)
#error "The H03 bench mode profile requires owned range, button and proposal state and independent input limits"
#endif

#if defined(RBM_H03_BENCH_BUTTON_MAP) != defined(RBM_H03_BENCH_MANUAL_MAX_AGE_US)
#error "Manual commissioning requires both a qualified P1 map and shift age"
#endif

#ifdef RBM_H03_BENCH_BUTTON_MAP
_Static_assert(RBM_H03_BENCH_MANUAL_MAX_AGE_US > 0u &&
               RBM_H03_BENCH_MANUAL_MAX_AGE_US < UINT32_C(0x80000000), "Invalid manual shift age");
#define RBM_H03_PROFILE_TOYOTA_INPUT_STARTUP lfj8_h03_bench_manual_startup
#else
#define RBM_H03_PROFILE_TOYOTA_INPUT_STARTUP lfj8_h03_bench_selector_startup
#endif

static const Lfj8H03InputBinding lfj8_h03_bench_input_binding = {
    .adc = &rbm_h03_selector_adc_state,
    .control = &RBM_H03_BENCH_RANGE_CONTROL,
    .button_filter = &RBM_H03_BENCH_BUTTON_FILTER,
    .io = &lfj8_h03_mmio,
    .range_limits = &RBM_H03_BENCH_RANGE_LIMITS,
    .selector_profile = &lfj8_h03_bench_selector,
    .require_pn_agreement = 1u,
#ifdef RBM_H03_BENCH_BUTTON_MAP
    .p1_button_map = &RBM_H03_BENCH_BUTTON_MAP,
    .manual_max_age_us = RBM_H03_BENCH_MANUAL_MAX_AGE_US,
#else
    .selector_only = 1u,
#endif
};

static const Lfj8H03ToyotaInputCapture lfj8_h03_bench_capture = {
    .binding = &lfj8_h03_bench_input_binding,
    .proposal = &RBM_H03_BENCH_INPUT_PROPOSAL,
    .ram_owned = rbm_h03_target_ram_owned,
    .read = RBM_H03_BENCH_DRIVER_READ,
};

#define RBM_H03_PROFILE_TOYOTA_INPUT_CAPTURE lfj8_h03_bench_capture
#include "lfj8_h03_toyota_input_profile.h"
#endif
#endif
