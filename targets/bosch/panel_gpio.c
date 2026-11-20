#include "panel_gpio.h"

static bool valid_plan(PanelOutput plan, BoschPanelGpioTiming timing) {
    if (plan.status != PANEL_OUTPUT_ACTIVE || plan.period_field > INT32_MAX ||
        plan.width_field >= plan.period_field || timing.minimum_phase_ticks == 0 ||
        timing.minimum_phase_ticks > INT32_MAX ||
        timing.maximum_lateness_ticks >= timing.minimum_phase_ticks) {
        return false;
    }
    const uint32_t required_ticks = timing.minimum_phase_ticks + timing.maximum_lateness_ticks;
    return plan.width_field >= required_ticks &&
           plan.period_field - plan.width_field >= required_ticks;
}

static void start_low_phase(BoschPanelGpio *gpio, PanelOutput plan) {
    gpio->high = false;
    gpio->high_ticks = plan.width_field;
    gpio->phase_ticks = plan.period_field - plan.width_field;
}

BoschPanelGpioCommand bosch_panel_gpio_poll(BoschPanelGpio *gpio, BoschPanelGpioTiming timing,
                                          PanelOutput plan, BoschPanelGpioInputs inputs) {
    if (!inputs.route_armed || inputs.native_priority ||
        (inputs.actuator_mask & BOSCH_PANEL_ACTUATOR_LOCK) || !valid_plan(plan, timing)) {
        gpio->active = false;
        return BOSCH_PANEL_USE_NATIVE;
    }

    if (!gpio->active) {
        gpio->active = true;
        gpio->phase_started = inputs.now;
        start_low_phase(gpio, plan);
    } else {
        const uint32_t elapsed = inputs.now - gpio->phase_started;
        if (elapsed >= gpio->phase_ticks) {
            if (elapsed - gpio->phase_ticks > timing.maximum_lateness_ticks) {
                gpio->active = false;
                return BOSCH_PANEL_USE_NATIVE;
            }
            gpio->phase_started += gpio->phase_ticks;
            if (gpio->high) {
                start_low_phase(gpio, plan);
            } else {
                gpio->high = true;
                gpio->phase_ticks = gpio->high_ticks;
            }
        }
    }

    return gpio->high != timing.inverted ? BOSCH_PANEL_GPIO_HIGH : BOSCH_PANEL_GPIO_LOW;
}
