#ifndef RBM_PANEL_PULSE_H
#define RBM_PANEL_PULSE_H

#include <stdbool.h>
#include <stdint.h>

#define PANEL_PULSES_PER_KM_NOMINAL UINT32_C(6000)
#define PANEL_SPEED_UNAVAILABLE UINT16_MAX

typedef enum {
    PANEL_PERIOD_TICKS,
    PANEL_PERIOD_TICKS_MINUS_ONE,
} PanelPeriodEncoding;

typedef enum {
    PANEL_WIDTH_HIGH_TICKS,
    PANEL_WIDTH_LOW_TICKS,
} PanelWidthEncoding;

typedef enum {
    PANEL_OUTPUT_UNCONFIGURED,
    PANEL_OUTPUT_STOPPED,
    PANEL_OUTPUT_UNAVAILABLE,
    PANEL_OUTPUT_OUT_OF_RANGE,
    PANEL_OUTPUT_ACTIVE,
} PanelOutputStatus;

typedef struct {
    uint32_t timer_hz;
    uint32_t minimum_pulses_per_km;
    uint32_t maximum_pulses_per_km;
    uint16_t high_permille;
    uint8_t period_field_bits;
    PanelPeriodEncoding period_encoding;
    PanelWidthEncoding width_encoding;
} PanelPulseConfig;

typedef struct {
    PanelPulseConfig config;
    uint32_t pulses_per_km;
} PanelPulse;

typedef struct {
    void *context;
    bool (*read)(void *context, uint32_t *pulses_per_km);
    /* Return true only after a complete durable update. */
    bool (*write)(void *context, uint32_t pulses_per_km);
} PanelCoefficientStorage;

typedef struct {
    PanelOutputStatus status;
    uint32_t period_field;
    uint32_t width_field;
} PanelOutput;

/* Start with the nominal coefficient. Serialize coefficient access with plan(). */
bool panel_pulse_init(PanelPulse *pulse, const PanelPulseConfig *config);
bool panel_pulse_load_coefficient(PanelPulse *pulse, const PanelCoefficientStorage *storage);
bool panel_pulse_store_coefficient(PanelPulse *pulse, const PanelCoefficientStorage *storage,
                                   uint32_t pulses_per_km);

/* speed_raw is in 0.01 km/h. Only ACTIVE authorizes a hardware period update. */
PanelOutput panel_pulse_plan(const PanelPulse *pulse, uint16_t speed_raw, bool fresh);

#endif
