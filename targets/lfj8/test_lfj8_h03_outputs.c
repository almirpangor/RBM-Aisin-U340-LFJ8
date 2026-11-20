#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdio.h>

#include "lfj8_h03_outputs.h"

/* Synthetic bench records exercise the contract without assigning real loads. */
static const Lfj8H03SltPoint points[] = {{400u, 800u}, {2200u, 500u}, {4000u, 200u}};
static const Lfj8H03SltCalibration calibration = {
    points, sizeof(points) / sizeof(points[0]), 500, 800, 11000u, 14500u,
};
static const Lfj8H03OutputBinding binding = {
    LFJ8_H03_SHIFT_E, LFJ8_H03_SHIFT_F, LFJ8_H03_SHIFT_D,
};
static const Lfj8H03OperatingPoint operating = {720, 13200u};

static RbmU340eHydraulicOutput proposal(void)
{
    RbmU340eHydraulicOutput request = {.write_count = 0u};
    request.slt_result.selected_7244 = 12800;
    request.slt_result.characteristic_7132 = 12800u;
    request.write_count = 4u;
    request.writes[0] = (FactoryDriverWrite){1u, RBM_U340E_DONOR_CHANNEL_S1, 1u};
    request.writes[1] = (FactoryDriverWrite){1u, RBM_U340E_DONOR_CHANNEL_ST, 0u};
    request.writes[2] = (FactoryDriverWrite){1u, RBM_U340E_DONOR_CHANNEL_S2, 1u};
    request.writes[3] = (FactoryDriverWrite){1u, RBM_U340E_DONOR_CHANNEL_S1, 0u};
    return request;
}

static void assert_empty(const Lfj8H03OutputPlan *plan)
{
    assert(plan->discrete_count == 0u && plan->pressure_mailbox == 0u);
    assert(plan->pressure_binary32 == 0u && plan->pressure_request_ma == 0u);
    assert(plan->toyota_compare == 0u);
    for (size_t i = 0u; i < sizeof(plan->discrete) / sizeof(plan->discrete[0]); ++i) {
        assert(plan->discrete[i].mailbox == 0u && plan->discrete[i].on == 0u);
    }
}

static void test_output_plan(void)
{
    RbmU340eHydraulicOutput request = proposal();
    const Lfj8H03OemOutputState oem = {.current = 1u};
    Lfj8H03OutputPlan plan;

    assert(lfj8_h03_plan_outputs(&request, &binding, &oem, &calibration, operating, &plan) ==
        LFJ8_H03_OUTPUT_OK);
    assert(plan.discrete_count == 4u);
    assert(plan.discrete[0].mailbox == 0x8063D8u && plan.discrete[0].on == 1u);
    assert(plan.discrete[1].mailbox == 0x8063D5u && plan.discrete[1].on == 0u);
    assert(plan.discrete[2].mailbox == 0x8063DBu && plan.discrete[2].on == 1u);
    assert(plan.discrete[3].mailbox == 0x8063D8u && plan.discrete[3].on == 0u);
    assert(plan.pressure_mailbox == 0x80508Cu && plan.pressure_binary32 == 0x3F000000u);
    assert(plan.toyota_compare == 2200u && plan.pressure_request_ma == 500u);

    request.write_count = 0u;
    request.slt_result.characteristic_7132 = 6400u;
    assert(lfj8_h03_plan_outputs(&request, &binding, &oem, &calibration, operating, &plan) ==
        LFJ8_H03_OUTPUT_OK);
    assert(plan.discrete_count == 0u && plan.toyota_compare == 1300u);
    assert(plan.pressure_request_ma == 650u && plan.pressure_binary32 == 0x3F266666u);

    request.slt_result.characteristic_7132 = 0u;
    assert(lfj8_h03_plan_outputs(&request, &binding, &oem, &calibration, operating, &plan) ==
        LFJ8_H03_OUTPUT_OK);
    assert(plan.toyota_compare == 400u && plan.pressure_request_ma == 800u);

    request.slt_result.characteristic_7132 = 25600u;
    assert(lfj8_h03_plan_outputs(&request, &binding, &oem, &calibration, operating, &plan) ==
        LFJ8_H03_OUTPUT_OK);
    assert(plan.toyota_compare == 4000u && plan.pressure_request_ma == 200u);
}

static void test_oem_guards(void)
{
    RbmU340eHydraulicOutput request = proposal();
    Lfj8H03OemOutputState oem = {.current = 1u};
    Lfj8H03OutputPlan plan;

    assert(lfj8_h03_plan_outputs(&request, &binding, &oem, &calibration, operating, &plan) ==
        LFJ8_H03_OUTPUT_OK);
    oem.d_fault = 1u;
    assert(lfj8_h03_plan_outputs(&request, &binding, &oem, &calibration, operating, &plan) ==
        LFJ8_H03_OUTPUT_OEM_OVERRIDE);
    assert_empty(&plan);
    oem.d_fault = 0u;
    oem.service_e = 1u;
    assert(lfj8_h03_plan_outputs(&request, &binding, &oem, &calibration, operating, &plan) ==
        LFJ8_H03_OUTPUT_OEM_OVERRIDE);
    oem.service_e = 0u;
    oem.discrete_inhibit = 1u;
    assert(lfj8_h03_plan_outputs(&request, &binding, &oem, &calibration, operating, &plan) ==
        LFJ8_H03_OUTPUT_OEM_OVERRIDE);

    request.write_count = 0u;
    assert(lfj8_h03_plan_outputs(&request, &binding, &oem, &calibration, operating, &plan) ==
        LFJ8_H03_OUTPUT_OK);
    oem.pressure_fault = 1u;
    assert(lfj8_h03_plan_outputs(&request, &binding, &oem, &calibration, operating, &plan) ==
        LFJ8_H03_OUTPUT_OEM_OVERRIDE);
    oem.pressure_fault = 0u;
    oem.force_fallback_b = 1u;
    assert(lfj8_h03_plan_outputs(&request, &binding, &oem, &calibration, operating, &plan) ==
        LFJ8_H03_OUTPUT_OEM_OVERRIDE);
    assert_empty(&plan);
    oem.current = 0u;
    assert(lfj8_h03_plan_outputs(&request, &binding, &oem, &calibration, operating, &plan) ==
        LFJ8_H03_OUTPUT_INVALID);
}

static void test_invalid_bindings_and_calibration(void)
{
    RbmU340eHydraulicOutput request = proposal();
    const Lfj8H03OemOutputState oem = {.current = 1u};
    Lfj8H03SltCalibration bad_calibration = calibration;
    Lfj8H03OutputBinding bad_binding = binding;
    Lfj8H03OutputPlan plan;
    const Lfj8H03SltPoint duplicate[] = {{400u, 800u}, {2200u, 500u}, {2200u, 600u}};
    const Lfj8H03SltPoint excessive[] = {{400u, 800u}, {4000u, 1001u}};

    bad_binding.st = bad_binding.s1;
    assert(lfj8_h03_plan_outputs(&request, &bad_binding, &oem, &calibration, operating, &plan) ==
        LFJ8_H03_OUTPUT_INVALID);
    request.writes[3].value = 2u;
    assert(lfj8_h03_plan_outputs(&request, &binding, &oem, &calibration, operating, &plan) ==
        LFJ8_H03_OUTPUT_INVALID);
    assert_empty(&plan);
    request = proposal();
    request.writes[3].channel = 2u;
    assert(lfj8_h03_plan_outputs(&request, &binding, &oem, &calibration, operating, &plan) ==
        LFJ8_H03_OUTPUT_INVALID);
    request = proposal();
    request.slt_result.characteristic_7132 = 25601u;
    assert(lfj8_h03_plan_outputs(&request, &binding, &oem, &calibration, operating, &plan) ==
        LFJ8_H03_OUTPUT_INVALID);

    request = proposal();
    assert(lfj8_h03_plan_outputs(&request, &binding, &oem, NULL, operating, &plan) ==
        LFJ8_H03_OUTPUT_OUTSIDE_CALIBRATION);
    bad_calibration.points = duplicate;
    assert(lfj8_h03_plan_outputs(&request, &binding, &oem, &bad_calibration, operating, &plan) ==
        LFJ8_H03_OUTPUT_OUTSIDE_CALIBRATION);
    bad_calibration.points = excessive;
    bad_calibration.point_count = 2u;
    assert(lfj8_h03_plan_outputs(&request, &binding, &oem, &bad_calibration, operating, &plan) ==
        LFJ8_H03_OUTPUT_OUTSIDE_CALIBRATION);

    Lfj8H03OperatingPoint outside = operating;
    outside.atf_tenths_c = 801;
    assert(lfj8_h03_plan_outputs(&request, &binding, &oem, &calibration, outside, &plan) ==
        LFJ8_H03_OUTPUT_OUTSIDE_CALIBRATION);
    outside = operating;
    outside.supply_mv = 10999u;
    assert(lfj8_h03_plan_outputs(&request, &binding, &oem, &calibration, outside, &plan) ==
        LFJ8_H03_OUTPUT_OUTSIDE_CALIBRATION);
    request.slt_result.characteristic_7132 = 25600u;
    bad_calibration = calibration;
    bad_calibration.point_count = 2u;
    assert(lfj8_h03_plan_outputs(&request, &binding, &oem, &bad_calibration, operating, &plan) ==
        LFJ8_H03_OUTPUT_OUTSIDE_CALIBRATION);
    assert_empty(&plan);
}

static void test_pressure_binary32(void)
{
    const RbmU340eHydraulicOutput request = proposal();
    const Lfj8H03OemOutputState oem = {.current = 1u};
    Lfj8H03OutputPlan plan;
    Lfj8H03SltPoint flat[] = {{400u, 0u}, {4000u, 0u}};
    Lfj8H03SltCalibration profile = calibration;
    profile.points = flat;
    profile.point_count = 2u;

    for (uint16_t milliamps = 0; milliamps <= 1000u; ++milliamps) {
        flat[0].lfj8_request_ma = milliamps;
        flat[1].lfj8_request_ma = milliamps;
        const union { float amps; uint32_t bits; } expected = {
            .amps = (float)milliamps / 1000.0f,
        };
        assert(lfj8_h03_plan_outputs(&request, &binding, &oem, &profile, operating, &plan) ==
               LFJ8_H03_OUTPUT_OK);
        assert(plan.pressure_request_ma == milliamps && plan.pressure_binary32 == expected.bits);
    }
}

int main(void)
{
    test_output_plan();
    test_oem_guards();
    test_invalid_bindings_and_calibration();
    test_pressure_binary32();
    puts("LFJ8 H03 output planning checks passed");
    return 0;
}
