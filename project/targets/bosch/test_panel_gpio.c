#include "panel_gpio.h"

#include <assert.h>
#include <stdio.h>

int main(void) {
    const PanelPulseConfig config = {
        .timer_hz = 78125,
        .minimum_pulses_per_km = 6000,
        .maximum_pulses_per_km = 6000,
        .high_permille = 500,
        .period_field_bits = 32,
        .period_encoding = PANEL_PERIOD_TICKS,
        .width_encoding = PANEL_WIDTH_HIGH_TICKS,
    };
    PanelPulse pulse;
    assert(panel_pulse_init(&pulse, &config));
    const PanelOutput p60 = panel_pulse_plan(&pulse, 6000, true);
    const PanelOutput p120 = panel_pulse_plan(&pulse, 12000, true);
    assert(p60.period_field == 781 && p60.width_field == 391);
    assert(p120.period_field == 391 && p120.width_field == 196);

    BoschPanelGpio gpio = {0};
    BoschPanelGpioTiming timing = {3, 2, false};
    BoschPanelGpioInputs inputs = {0};
    assert(bosch_panel_gpio_poll(&gpio, timing, p60, inputs) == BOSCH_PANEL_USE_NATIVE);
    inputs.route_armed = true;

    /* Run two complete cycles across the 32-bit clock rollover. */
    const uint32_t start = UINT32_MAX - 389;
    for (uint32_t elapsed = 0; elapsed < 2 * p60.period_field; ++elapsed) {
        inputs.now = start + elapsed;
        const bool high = elapsed % p60.period_field >= 390;
        assert(bosch_panel_gpio_poll(&gpio, timing, p60, inputs) ==
               (high ? BOSCH_PANEL_GPIO_HIGH : BOSCH_PANEL_GPIO_LOW));
    }

    /* A valid speed change completes the previous HIGH and starts the new LOW. */
    assert(bosch_panel_gpio_poll(&gpio, timing, p120, inputs) == BOSCH_PANEL_GPIO_HIGH);
    inputs.now = start + 2 * p60.period_field;
    assert(bosch_panel_gpio_poll(&gpio, timing, p120, inputs) == BOSCH_PANEL_GPIO_LOW);
    inputs.now += 194;
    assert(bosch_panel_gpio_poll(&gpio, timing, p120, inputs) == BOSCH_PANEL_GPIO_LOW);
    inputs.now += 2;
    assert(bosch_panel_gpio_poll(&gpio, timing, p120, inputs) == BOSCH_PANEL_GPIO_HIGH);

    /* The native relay and diagnostic owners preempt at the next call. */
    inputs.actuator_mask = BOSCH_PANEL_ACTUATOR_LOCK;
    assert(bosch_panel_gpio_poll(&gpio, timing, p120, inputs) == BOSCH_PANEL_USE_NATIVE);
    inputs.actuator_mask = 0;
    timing.inverted = true;
    assert(bosch_panel_gpio_poll(&gpio, timing, p120, inputs) == BOSCH_PANEL_GPIO_HIGH);
    inputs.now += 195;
    assert(bosch_panel_gpio_poll(&gpio, timing, p120, inputs) == BOSCH_PANEL_GPIO_LOW);
    inputs.native_priority = true;
    assert(bosch_panel_gpio_poll(&gpio, timing, p120, inputs) == BOSCH_PANEL_USE_NATIVE);
    inputs.native_priority = false;
    timing.inverted = false;

    /* A missed phase deadline relinquishes ownership instead of issuing a burst. */
    assert(bosch_panel_gpio_poll(&gpio, timing, p120, inputs) == BOSCH_PANEL_GPIO_LOW);
    inputs.now += 198;
    assert(bosch_panel_gpio_poll(&gpio, timing, p120, inputs) == BOSCH_PANEL_USE_NATIVE);
    assert(bosch_panel_gpio_poll(&gpio, timing, p120, inputs) == BOSCH_PANEL_GPIO_LOW);
    assert(bosch_panel_gpio_poll(&gpio, timing, panel_pulse_plan(&pulse, 6000, false), inputs) ==
           BOSCH_PANEL_USE_NATIVE);
    assert(bosch_panel_gpio_poll(&gpio, timing, panel_pulse_plan(&pulse, 0, true), inputs) ==
           BOSCH_PANEL_USE_NATIVE);
    assert(bosch_panel_gpio_poll(&gpio, timing, (PanelOutput){PANEL_OUTPUT_ACTIVE, 10, 4}, inputs) ==
           BOSCH_PANEL_USE_NATIVE);
    puts("Bosch panel GPIO timing and ownership PASS (host)");
    return 0;
}
