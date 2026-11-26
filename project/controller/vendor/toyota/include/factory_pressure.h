#ifndef RBM_FACTORY_PRESSURE_H
#define RBM_FACTORY_PRESSURE_H
#include <stdint.h>
typedef struct {
    uint16_t input_7154;
    int16_t input_7208, input_7204, input_7198, memory_p1580, output_7148;
    uint8_t index_4848, index_4852, flags_4835, flags_4834, flags_4829;
    uint8_t flags_4846, flags_4845, speed_4548, flags_7252, flags_5299, flags_4844;
} FactoryBasePressure;
/* Exact numerical path 05B440..05B58E, donor raw units. Inputs are NOT
 * automatically TPS, rpm, degrees or bar. No target timer/GPIO writes. */
void factory_base_pressure(FactoryBasePressure *s);
typedef struct {
    uint16_t input_7204, input_7154, input_7152, saved_p1584, limit_7138;
    int16_t row_p1586;
    uint8_t flags_9748, index_4852, index_4851;
} FactoryPressureLimit;
/* 05B592. Guard rejects unknown row/index before state mutation. */
int factory_pressure_limit(FactoryPressureLimit *s);
typedef struct {
    uint16_t input_7164, input_7184, output_7146;
    uint8_t flags_4829, flags_p1588, flags_4846, flags_4845;
    uint8_t index_4852, flags_4841, flags_4844, count_4742;
} FactoryPressureOverride;
/* 05B638. Counts 24/49 are donor task counts, not milliseconds. */
void factory_pressure_override(FactoryPressureOverride *s);
typedef struct {
    uint16_t input_7184, input_7152, output_7144;
    uint8_t flags_4838, index_4852, flags_7250, flags_7252;
    uint8_t flags_4830, count_4743, speed_4549, saved_p1576, flags_4844;
} FactoryPressureSpecial;
/* 05B382. State changes and raw calibration axes preserved. */
void factory_pressure_special(FactoryPressureSpecial *s);

/* Shared state for 059D46, 059DEA and 059EB8. Names retain donor GP
 * offsets until the physical signal contracts are recovered. */
typedef struct {
    uint32_t flags_9748;
    int32_t inputs_9728[3];
    uint16_t input_7244, input_7184, input_7100, input_7200, input_7154;
    int16_t input_7204;
    uint16_t pressure_p1462, subtract_p1458, ramp_p1456, subtract_p1454;
    uint16_t hold_p1460, saved_p1450, output_7142;
    uint8_t flags_9736, flags_9735, flags_4846, flags_4842, flags_4831;
    uint8_t flags_4845, flags_4844, flags_p1449;
    uint8_t selector_p1444, count_p1445, index_4514, index_4852, speed_4549;
} FactoryPhasePressure;
/* 059D46..059DE8: transient subtraction window. Rejects invalid table
 * domains without changing state (including missing threshold sentinel). */
int factory_pressure_window(FactoryPhasePressure *s);
/* 059DEA..059EB4: incremental correction, preserving 16-bit wrap. */
int factory_pressure_ramp(FactoryPhasePressure *s);
/* 059EB8..05A042: combines phase terms, hold/release, selected fallback
 * maps and zero override. Does not generate pressure_p1462 upstream. */
void factory_phase_pressure(FactoryPhasePressure *s);

typedef struct {
    uint32_t flags_9748;
    int32_t input_9724;
    uint16_t input_7100, input_7094, input_7152, input_7184, memory_p1452;
    uint16_t input_7154, input_7224, output_p1462;
    int16_t input_7106, input_7204, input_7208;
    uint8_t index_4514, index_4545, index_4546, flags_4838, flags_4843;
    uint8_t flags_4846, flags_5139, flags_4842, flags_4844, index_4519;
    int8_t learned_4579[18], learned_4554[5];
    uint16_t input_7200;
} FactoryPhaseDemand;
/* 0599DE..059D42, including the numerical helpers 05AA1C and 05AF64.
 * Applies supplied learned corrections; does not generate their learned values.
 * Rejects unsupported mode/index domains without mutation. */
int factory_phase_demand(FactoryPhaseDemand *s);

typedef struct {
    uint32_t flags_9748;
    int16_t input_7088, input_7208, input_7204;
    uint16_t subtract_p1454;
    uint8_t flags_9736, flags_9735, flags_4842;
    uint8_t count_p1448, count_p1447, count_4749;
} FactoryPressureFeedback;
/* 05A046..05A166: threshold-qualified subtractive correction. */
int factory_pressure_feedback(FactoryPressureFeedback *s);

/* One authoritative copy of each shared donor signal for the recovered
 * five-call phase-pressure tail. inputs_9728[1] is the GP-9724 word. */
typedef struct {
    uint32_t flags_9748;
    int32_t inputs_9728[3];
    uint16_t input_7244, input_7184, input_7100, input_7200;
    uint16_t input_7154, input_7094, input_7152, input_7224;
    int16_t input_7204, input_7208, input_7106, input_7088;
    uint16_t pressure_p1462, subtract_p1458, ramp_p1456, subtract_p1454;
    uint16_t hold_p1460, saved_p1450, output_7142, memory_p1452;
    uint8_t flags_9736, flags_9735, flags_4846, flags_4842, flags_4831;
    uint8_t flags_4845, flags_4844, flags_p1449;
    uint8_t selector_p1444, count_p1445, index_4514, index_4852, speed_4549;
    uint8_t index_4545, index_4546, flags_4838, flags_4843, flags_5139;
    uint8_t index_4519, count_p1448, count_p1447, count_4749;
    int8_t learned_4579[18], learned_4554[5];
} FactoryPhaseCycle;
/* Exact call order at 059510..059524. Atomic in caller state on validation
 * failure; caller supplies a consistent input snapshot. This is NOT the
 * full 05934E mode controller, scheduler or output driver. */
int factory_phase_cycle(FactoryPhaseCycle *s);
#endif
