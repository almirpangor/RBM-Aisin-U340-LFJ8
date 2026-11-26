#ifndef RBM_BOSCH_PANEL_GPIO_H
#define RBM_BOSCH_PANEL_GPIO_H

#include "panel_pulse.h"

#define BOSCH_PANEL_ACTUATOR_LOCK UINT16_C(0x0100)

typedef enum {
    BOSCH_PANEL_USE_NATIVE,
    BOSCH_PANEL_GPIO_LOW,
    BOSCH_PANEL_GPIO_HIGH,
} BoschPanelGpioCommand;

typedef struct {
    uint32_t minimum_phase_ticks;
    uint32_t maximum_lateness_ticks;
    bool inverted;
} BoschPanelGpioTiming;

typedef struct {
    uint32_t now;
    uint16_t actuator_mask;
    bool route_armed;
    bool native_priority;
} BoschPanelGpioInputs;

typedef struct {
    uint32_t phase_started;
    uint32_t phase_ticks;
    uint32_t high_ticks;
    bool active;
    bool high;
} BoschPanelGpio;

/* Zero-initialize state. Supply plans in PANEL_PERIOD_TICKS / PANEL_WIDTH_HIGH_TICKS
 * and one monotonic, wrapping 32-bit timebase shared by timing and plans. Change
 * timing only while disarmed. A valid plan change takes effect at the next LOW.
 * Call in the serialized owner of P3.6. On USE_NATIVE, apply the stock path.
 * route_armed requires an assigned and electrically verified output route.
 * native_priority includes native forced writes and any request from the relay owner.
 */
BoschPanelGpioCommand bosch_panel_gpio_poll(BoschPanelGpio *gpio, BoschPanelGpioTiming timing,
                                          PanelOutput plan, BoschPanelGpioInputs inputs);

#endif
