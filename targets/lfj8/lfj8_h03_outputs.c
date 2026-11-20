#include "lfj8_h03_outputs.h"

enum {
    LFJ8_H03_MAX_Q8 = 25600,
    LFJ8_H03_COMPARE_MIN = 400,
    LFJ8_H03_COMPARE_MAX = 4000,
    LFJ8_H03_LPS_MAX_MA = 1000,
    LFJ8_H03_D_BLOCK = 1 << LFJ8_H03_SHIFT_D,
    LFJ8_H03_E_BLOCK = 1 << LFJ8_H03_SHIFT_E,
    LFJ8_H03_F_BLOCK = 1 << LFJ8_H03_SHIFT_F,
    LFJ8_H03_PRESSURE_BLOCK = 1 << 3,
};

static const uint32_t strategy_mailbox[] = {
    UINT32_C(0x8063D5), UINT32_C(0x8063D8), UINT32_C(0x8063DB),
};

static uint8_t blocked_channels(const Lfj8H03OemOutputState *oem)
{
    if (oem->force_zero_a || oem->force_zero_b || oem->force_fallback_a ||
        oem->force_fallback_b) {
        return LFJ8_H03_D_BLOCK | LFJ8_H03_E_BLOCK | LFJ8_H03_F_BLOCK |
            LFJ8_H03_PRESSURE_BLOCK;
    }
    return (uint8_t)(
        ((oem->d_fault || oem->service_d || oem->discrete_inhibit) ? LFJ8_H03_D_BLOCK : 0) |
        ((oem->e_fault || oem->service_e || oem->discrete_inhibit) ? LFJ8_H03_E_BLOCK : 0) |
        ((oem->f_fault || oem->service_f || oem->discrete_inhibit) ? LFJ8_H03_F_BLOCK : 0) |
        ((oem->pressure_fault || oem->service_pressure) ? LFJ8_H03_PRESSURE_BLOCK : 0));
}

static int binding_is_valid(const Lfj8H03OutputBinding *binding)
{
    return (unsigned)binding->s1 <= LFJ8_H03_SHIFT_F &&
        (unsigned)binding->s2 <= LFJ8_H03_SHIFT_F &&
        (unsigned)binding->st <= LFJ8_H03_SHIFT_F &&
        binding->s1 != binding->s2 && binding->s1 != binding->st && binding->s2 != binding->st;
}

static int pressure_for_compare(const Lfj8H03SltCalibration *calibration,
    Lfj8H03OperatingPoint operating, uint16_t compare, uint16_t *request_ma)
{
    if (!calibration || !calibration->points || calibration->point_count < 2u ||
        calibration->point_count > (size_t)(LFJ8_H03_COMPARE_MAX - LFJ8_H03_COMPARE_MIN + 1) ||
        operating.atf_tenths_c < calibration->min_atf_tenths_c ||
        operating.atf_tenths_c > calibration->max_atf_tenths_c ||
        operating.supply_mv < calibration->min_supply_mv ||
        operating.supply_mv > calibration->max_supply_mv || operating.supply_mv == 0u) {
        return 0;
    }

    const Lfj8H03SltPoint *points = calibration->points;
    const size_t last = calibration->point_count - 1u;
    if (compare < points[0].toyota_compare || compare > points[last].toyota_compare ||
        points[0].toyota_compare < LFJ8_H03_COMPARE_MIN ||
        points[last].toyota_compare > LFJ8_H03_COMPARE_MAX ||
        points[0].lfj8_request_ma > LFJ8_H03_LPS_MAX_MA) {
        return 0;
    }

    size_t upper = 1u;
    for (size_t i = 1u; i <= last; ++i) {
        if (points[i].toyota_compare <= points[i - 1u].toyota_compare ||
            points[i].lfj8_request_ma > LFJ8_H03_LPS_MAX_MA) {
            return 0;
        }
        if (points[i].toyota_compare < compare) {
            upper = i + 1u;
        }
    }

    const Lfj8H03SltPoint low = points[upper - 1u];
    const Lfj8H03SltPoint high = points[upper];
    const uint32_t width = (uint32_t)high.toyota_compare - low.toyota_compare;
    const uint32_t position = (uint32_t)compare - low.toyota_compare;
    const uint32_t weighted = low.lfj8_request_ma * (width - position) +
        high.lfj8_request_ma * position;
    *request_ma = (uint16_t)((weighted + width / 2u) / width);
    return 1;
}

static void clear_plan(Lfj8H03OutputPlan *plan)
{
    for (size_t i = 0; i < sizeof(plan->discrete) / sizeof(plan->discrete[0]); ++i) {
        plan->discrete[i].mailbox = 0u;
        plan->discrete[i].on = 0u;
    }
    plan->discrete_count = 0u;
    plan->pressure_mailbox = 0u;
    plan->pressure_binary32 = 0u;
    plan->pressure_request_ma = 0u;
    plan->toyota_compare = 0u;
}

static uint32_t amps_binary32(uint16_t milliamps)
{
    if (milliamps == 0u) {
        return 0u;
    }
    uint32_t significand = milliamps;
    uint32_t exponent = 127u;
    while (significand < 1000u) {
        significand <<= 1;
        --exponent;
    }
    /* Encode significand / 1000, now in [1, 2). Cancel 8 from the
     * denominator and round the resulting /125 without a half-way case. */
    const uint32_t mantissa = ((significand << 20) + 62u) / 125u;
    return (exponent << 23) | (mantissa & UINT32_C(0x7fffff));
}

int lfj8_h03_output_plan_resolve(const Lfj8H03OutputPlan *plan, uint8_t before, uint8_t *after)
{
    if (!plan || !after || before > 7u ||
        plan->pressure_mailbox != UINT32_C(0x80508C) ||
        plan->pressure_request_ma > LFJ8_H03_LPS_MAX_MA ||
        plan->pressure_binary32 != amps_binary32(plan->pressure_request_ma) ||
        plan->toyota_compare < LFJ8_H03_COMPARE_MIN || plan->toyota_compare > LFJ8_H03_COMPARE_MAX ||
        plan->discrete_count > sizeof(plan->discrete) / sizeof(plan->discrete[0])) {
        return 0;
    }
    size_t previous_transition = 0;
    uint8_t levels = before;
    uint8_t changed = 0;
    for (size_t i = 0; i < plan->discrete_count; ++i) {
        const Lfj8H03DiscreteCommand command = plan->discrete[i];
        size_t channel = 0;
        while (channel < sizeof(strategy_mailbox) / sizeof(strategy_mailbox[0]) &&
               strategy_mailbox[channel] != command.mailbox) {
            ++channel;
        }
        if (channel == sizeof(strategy_mailbox) / sizeof(strategy_mailbox[0]) || command.on > 1u) {
            return 0;
        }
        const unsigned bit = 1u << channel;
        if ((levels & bit) == (command.on ? bit : 0u)) {
            continue;
        }
        if (channel < previous_transition || (changed & bit) != 0u) {
            return 0;
        }
        changed |= (uint8_t)bit;
        levels ^= (uint8_t)bit;
        previous_transition = channel;
    }
    *after = levels;
    return 1;
}

int lfj8_h03_output_plan_matches(const Lfj8H03OutputPlan *plan, uint8_t before, uint8_t after)
{
    uint8_t resolved;
    return lfj8_h03_output_plan_resolve(plan, before, &resolved) && resolved == after;
}

Lfj8H03OutputResult lfj8_h03_plan_outputs(const RbmU340eHydraulicOutput *request,
    const Lfj8H03OutputBinding *binding, const Lfj8H03OemOutputState *oem,
    const Lfj8H03SltCalibration *calibration, Lfj8H03OperatingPoint operating,
    Lfj8H03OutputPlan *plan)
{
    uint8_t resolved_channel[sizeof(plan->discrete) / sizeof(plan->discrete[0])];
    uint8_t affected = LFJ8_H03_PRESSURE_BLOCK;

    if (!plan) {
        return LFJ8_H03_OUTPUT_INVALID;
    }
    clear_plan(plan);
    if (!request || !binding || !oem || oem->current != 1u || !binding_is_valid(binding) ||
        request->write_count > sizeof(resolved_channel) ||
        request->slt_result.selected_7244 < 0 ||
        request->slt_result.characteristic_7132 > LFJ8_H03_MAX_Q8) {
        return LFJ8_H03_OUTPUT_INVALID;
    }

    for (size_t i = 0; i < request->write_count; ++i) {
        const FactoryDriverWrite write = request->writes[i];
        Lfj8H03ShiftOutput channel;

        if (write.write_pending != 1u || write.value > 1u) {
            return LFJ8_H03_OUTPUT_INVALID;
        }
        switch (write.channel) {
        case RBM_U340E_DONOR_CHANNEL_S1: channel = binding->s1; break;
        case RBM_U340E_DONOR_CHANNEL_S2: channel = binding->s2; break;
        case RBM_U340E_DONOR_CHANNEL_ST: channel = binding->st; break;
        default: return LFJ8_H03_OUTPUT_INVALID;
        }
        resolved_channel[i] = (uint8_t)channel;
        affected |= (uint8_t)(1u << (unsigned)channel);
    }

    if ((blocked_channels(oem) & affected) != 0u) {
        return LFJ8_H03_OUTPUT_OEM_OVERRIDE;
    }

    const uint16_t toyota_compare = factory_driver_count(request->slt_result.characteristic_7132);
    uint16_t pressure_request_ma;
    if (!pressure_for_compare(calibration, operating, toyota_compare, &pressure_request_ma)) {
        return LFJ8_H03_OUTPUT_OUTSIDE_CALIBRATION;
    }

    for (size_t i = 0; i < request->write_count; ++i) {
        plan->discrete[i].mailbox = strategy_mailbox[resolved_channel[i]];
        plan->discrete[i].on = request->writes[i].value;
    }
    plan->discrete_count = request->write_count;
    plan->pressure_mailbox = UINT32_C(0x80508C);
    plan->pressure_binary32 = amps_binary32(pressure_request_ma);
    plan->pressure_request_ma = pressure_request_ma;
    plan->toyota_compare = toyota_compare;
    return LFJ8_H03_OUTPUT_OK;
}
