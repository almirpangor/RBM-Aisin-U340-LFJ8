#include "panel_pulse.h"

#undef NDEBUG
#include <assert.h>
#include <stddef.h>
#include <stdio.h>

typedef struct {
    uint32_t value;
    bool readable;
    bool writable;
    uint32_t write_count;
} TestStorage;

static bool read_coefficient(void *context, uint32_t *value) {
    TestStorage *storage = context;
    if (!storage->readable) {
        return false;
    }
    *value = storage->value;
    return true;
}

static bool write_coefficient(void *context, uint32_t value) {
    TestStorage *storage = context;
    storage->write_count++;
    if (!storage->writable) {
        return false;
    }
    storage->value = value;
    storage->readable = true;
    return true;
}

static void expect_output(PanelOutput output, PanelOutputStatus status,
                          uint32_t period_field, uint32_t width_field) {
    assert(output.status == status);
    assert(output.period_field == period_field);
    assert(output.width_field == width_field);
}

int main(void) {
    PanelPulseConfig config = {
        .timer_hz = 1000000,
        .minimum_pulses_per_km = 5000,
        .maximum_pulses_per_km = 7000,
        .high_permille = 500,
        .period_field_bits = 16,
        .period_encoding = PANEL_PERIOD_TICKS_MINUS_ONE,
        .width_encoding = PANEL_WIDTH_HIGH_TICKS,
    };
    PanelPulse pulse = {0};
    assert(!panel_pulse_init(&pulse, NULL));
    expect_output(panel_pulse_plan(&pulse, 4000, true), PANEL_OUTPUT_UNCONFIGURED, 0, 0);
    assert(panel_pulse_init(&pulse, &config));

    /* Nominal panel reference at 40, 80 and 120 km/h. */
    expect_output(panel_pulse_plan(&pulse, 4000, true), PANEL_OUTPUT_ACTIVE, 14999, 7500);
    expect_output(panel_pulse_plan(&pulse, 8000, true), PANEL_OUTPUT_ACTIVE, 7499, 3750);
    expect_output(panel_pulse_plan(&pulse, 12000, true), PANEL_OUTPUT_ACTIVE, 4999, 2500);
    expect_output(panel_pulse_plan(&pulse, 0, true), PANEL_OUTPUT_STOPPED, 0, 0);
    expect_output(panel_pulse_plan(&pulse, 0, false), PANEL_OUTPUT_UNAVAILABLE, 0, 0);
    expect_output(panel_pulse_plan(&pulse, 6000, false), PANEL_OUTPUT_UNAVAILABLE, 0, 0);
    expect_output(panel_pulse_plan(&pulse, PANEL_SPEED_UNAVAILABLE, true),
                  PANEL_OUTPUT_UNAVAILABLE, 0, 0);
    expect_output(panel_pulse_plan(&pulse, 1, true), PANEL_OUTPUT_OUT_OF_RANGE, 0, 0);
    expect_output(panel_pulse_plan(&pulse, 915, true), PANEL_OUTPUT_OUT_OF_RANGE, 0, 0);
    expect_output(panel_pulse_plan(&pulse, 916, true), PANEL_OUTPUT_ACTIVE, 65501, 32751);

    TestStorage medium = {0, false, true, 0};
    PanelCoefficientStorage storage = {&medium, read_coefficient, write_coefficient};
    assert(!panel_pulse_load_coefficient(&pulse, &storage));
    assert(!panel_pulse_store_coefficient(&pulse, &storage, 4999));
    assert(medium.write_count == 0);
    assert(panel_pulse_store_coefficient(&pulse, &storage, 6250));
    assert(medium.value == 6250 && medium.write_count == 1);
    expect_output(panel_pulse_plan(&pulse, 6000, true), PANEL_OUTPUT_ACTIVE, 9599, 4800);

    PanelPulse restarted;
    assert(panel_pulse_init(&restarted, &config));
    assert(restarted.pulses_per_km == 6000);
    assert(panel_pulse_load_coefficient(&restarted, &storage));
    assert(restarted.pulses_per_km == 6250);
    medium.writable = false;
    assert(!panel_pulse_store_coefficient(&restarted, &storage, 6800));
    assert(restarted.pulses_per_km == 6250 && medium.value == 6250);
    medium.value = 7001;
    assert(!panel_pulse_load_coefficient(&restarted, &storage));
    assert(restarted.pulses_per_km == 6250);

    /* Hold both edges after conversion to the alternate driver fields. */
    config.timer_hz = 1000500;
    config.high_permille = 300;
    config.period_encoding = PANEL_PERIOD_TICKS;
    config.width_encoding = PANEL_WIDTH_LOW_TICKS;
    assert(panel_pulse_init(&pulse, &config));
    expect_output(panel_pulse_plan(&pulse, 6000, true), PANEL_OUTPUT_ACTIVE, 10005, 7003);

    config.timer_hz = 100;
    assert(panel_pulse_init(&pulse, &config));
    expect_output(panel_pulse_plan(&pulse, 6000, true), PANEL_OUTPUT_OUT_OF_RANGE, 0, 0);
    config.high_permille = 999;
    assert(panel_pulse_init(&pulse, &config));
    expect_output(panel_pulse_plan(&pulse, 3000, true), PANEL_OUTPUT_ACTIVE, 2, 1);
    config.high_permille = 1;
    assert(panel_pulse_init(&pulse, &config));
    expect_output(panel_pulse_plan(&pulse, 3000, true), PANEL_OUTPUT_ACTIVE, 2, 1);

    config.timer_hz = UINT32_C(1) << 30;
    config.period_field_bits = 32;
    config.high_permille = 500;
    config.period_encoding = PANEL_PERIOD_TICKS_MINUS_ONE;
    assert(panel_pulse_init(&pulse, &config));
    expect_output(panel_pulse_plan(&pulse, 15, true), PANEL_OUTPUT_ACTIVE, UINT32_MAX,
                  UINT32_C(1) << 31);
    config.period_encoding = PANEL_PERIOD_TICKS;
    assert(panel_pulse_init(&pulse, &config));
    expect_output(panel_pulse_plan(&pulse, 15, true), PANEL_OUTPUT_OUT_OF_RANGE, 0, 0);

    config.high_permille = 1000;
    assert(!panel_pulse_init(&pulse, &config));
    assert(!panel_pulse_store_coefficient(&pulse, NULL, 6000));
    puts("PASS panel pulse nominal, range, timing, state, and storage");
    return 0;
}
