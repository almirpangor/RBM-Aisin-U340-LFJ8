#include "panel_pulse.h"

#include <stddef.h>

static bool config_is_valid(const PanelPulseConfig *config) {
    return config->timer_hz > 0 && config->minimum_pulses_per_km > 0 &&
           config->minimum_pulses_per_km <= PANEL_PULSES_PER_KM_NOMINAL &&
           config->maximum_pulses_per_km >= PANEL_PULSES_PER_KM_NOMINAL &&
           config->high_permille > 0 && config->high_permille < 1000 &&
           config->period_field_bits > 0 && config->period_field_bits <= 32 &&
           (config->period_encoding == PANEL_PERIOD_TICKS_MINUS_ONE ||
            (config->period_encoding == PANEL_PERIOD_TICKS && config->period_field_bits >= 2)) &&
           (config->width_encoding == PANEL_WIDTH_HIGH_TICKS ||
            config->width_encoding == PANEL_WIDTH_LOW_TICKS);
}

static bool coefficient_is_valid(const PanelPulse *pulse, uint32_t pulses_per_km) {
    return pulses_per_km >= pulse->config.minimum_pulses_per_km &&
           pulses_per_km <= pulse->config.maximum_pulses_per_km;
}

bool panel_pulse_init(PanelPulse *pulse, const PanelPulseConfig *config) {
    if (pulse == NULL || config == NULL || !config_is_valid(config)) {
        return false;
    }
    pulse->config = *config;
    pulse->pulses_per_km = PANEL_PULSES_PER_KM_NOMINAL;
    return true;
}

bool panel_pulse_load_coefficient(PanelPulse *pulse, const PanelCoefficientStorage *storage) {
    uint32_t value = 0;
    if (pulse == NULL || !config_is_valid(&pulse->config) || storage == NULL ||
        storage->read == NULL || !storage->read(storage->context, &value) ||
        !coefficient_is_valid(pulse, value)) {
        return false;
    }
    pulse->pulses_per_km = value;
    return true;
}

bool panel_pulse_store_coefficient(PanelPulse *pulse, const PanelCoefficientStorage *storage,
                                   uint32_t pulses_per_km) {
    if (pulse == NULL || !config_is_valid(&pulse->config) || storage == NULL ||
        storage->write == NULL || !coefficient_is_valid(pulse, pulses_per_km) ||
        !storage->write(storage->context, pulses_per_km)) {
        return false;
    }
    pulse->pulses_per_km = pulses_per_km;
    return true;
}

PanelOutput panel_pulse_plan(const PanelPulse *pulse, uint16_t speed_raw, bool fresh) {
    if (pulse == NULL || !config_is_valid(&pulse->config) ||
        !coefficient_is_valid(pulse, pulse->pulses_per_km)) {
        return (PanelOutput){PANEL_OUTPUT_UNCONFIGURED, 0, 0};
    }
    if (!fresh || speed_raw == PANEL_SPEED_UNAVAILABLE) {
        return (PanelOutput){PANEL_OUTPUT_UNAVAILABLE, 0, 0};
    }
    if (speed_raw == 0) {
        return (PanelOutput){PANEL_OUTPUT_STOPPED, 0, 0};
    }

    const PanelPulseConfig *config = &pulse->config;
    const uint64_t pulses_per_360000_seconds = (uint64_t)speed_raw * pulse->pulses_per_km;
    const uint64_t tick_numerator = (uint64_t)config->timer_hz * UINT64_C(360000);
    const uint64_t cycle_ticks =
        (tick_numerator + pulses_per_360000_seconds / 2) / pulses_per_360000_seconds;
    const uint64_t period_bias = config->period_encoding == PANEL_PERIOD_TICKS_MINUS_ONE;
    const uint64_t max_cycle_ticks = (UINT64_C(1) << config->period_field_bits) - 1 + period_bias;
    if (cycle_ticks < 2 || cycle_ticks > max_cycle_ticks) {
        return (PanelOutput){PANEL_OUTPUT_OUT_OF_RANGE, 0, 0};
    }

    uint64_t high_ticks = (cycle_ticks * config->high_permille + 500) / 1000;
    if (high_ticks == 0) {
        high_ticks = 1;
    }
    if (high_ticks >= cycle_ticks) {
        high_ticks = cycle_ticks - 1;
    }
    const uint64_t width = config->width_encoding == PANEL_WIDTH_HIGH_TICKS
        ? high_ticks : cycle_ticks - high_ticks;
    return (PanelOutput){PANEL_OUTPUT_ACTIVE, (uint32_t)(cycle_ticks - period_bias), (uint32_t)width};
}
