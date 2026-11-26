#ifndef RBM_LFJ8_H03_OUTPUTS_H
#define RBM_LFJ8_H03_OUTPUTS_H

#include <stddef.h>
#include <stdint.h>

#include "rbm_u340e.h"

typedef enum {
    LFJ8_H03_SHIFT_D, /* Mazda connector 1F. */
    LFJ8_H03_SHIFT_E, /* Mazda connector 1H. */
    LFJ8_H03_SHIFT_F, /* Mazda connector 1J. */
} Lfj8H03ShiftOutput;

typedef struct {
    Lfj8H03ShiftOutput s1;
    Lfj8H03ShiftOutput s2;
    Lfj8H03ShiftOutput st;
} Lfj8H03OutputBinding;

typedef struct {
    uint8_t current;           /* Gates and donor commands are from the same cycle. */
    uint8_t d_fault;           /* 0x8063AF */
    uint8_t e_fault;           /* 0x8063B7 */
    uint8_t f_fault;           /* 0x8063C4 */
    uint8_t pressure_fault;    /* 0x806356 */
    uint8_t discrete_inhibit;  /* 0x8063F2 */
    uint8_t service_d;         /* 0x80636E */
    uint8_t service_e;         /* 0x80636F */
    uint8_t service_f;         /* 0x806370 */
    uint8_t service_pressure;  /* 0x80636D */
    uint8_t force_zero_a;      /* 0x8065BA */
    uint8_t force_zero_b;      /* 0x8065B8 */
    uint8_t force_fallback_a;  /* 0x8065B7 */
    uint8_t force_fallback_b;  /* 0x8065B6 */
} Lfj8H03OemOutputState;

typedef struct {
    uint16_t toyota_compare;
    uint16_t lfj8_request_ma;
} Lfj8H03SltPoint;

typedef struct {
    const Lfj8H03SltPoint *points; /* Ascending Toyota compare, measured across this window. */
    size_t point_count;
    int16_t min_atf_tenths_c;
    int16_t max_atf_tenths_c;
    uint16_t min_supply_mv;
    uint16_t max_supply_mv;
} Lfj8H03SltCalibration;

typedef struct {
    int16_t atf_tenths_c;
    uint16_t supply_mv;
} Lfj8H03OperatingPoint;

typedef struct {
    uint32_t mailbox;
    uint8_t on;
} Lfj8H03DiscreteCommand;

typedef struct {
    Lfj8H03DiscreteCommand discrete[5];
    uint8_t discrete_count;
    uint32_t pressure_mailbox;
    uint32_t pressure_binary32;
    uint16_t pressure_request_ma;
    uint16_t toyota_compare;
} Lfj8H03OutputPlan;

typedef enum {
    LFJ8_H03_OUTPUT_OK,
    LFJ8_H03_OUTPUT_INVALID,
    LFJ8_H03_OUTPUT_OEM_OVERRIDE,
    LFJ8_H03_OUTPUT_OUTSIDE_CALIBRATION,
} Lfj8H03OutputResult;

/* Plans commands for the strategy inputs of the exact H03 OEM output arbiter,
 * after rbm_u340e_outputs_step succeeds. The OEM arbiter owns the final outputs.
 * The plan keeps discrete write order. Pressure is separate for scheduling.
 * Pass a current, coherent OEM snapshot. There are no memory or register writes.
 * Output is cleared on rejection. The caller owns publication and scheduling.
 */
Lfj8H03OutputResult lfj8_h03_plan_outputs(const RbmU340eHydraulicOutput *request,
    const Lfj8H03OutputBinding *binding, const Lfj8H03OemOutputState *oem,
    const Lfj8H03SltCalibration *calibration, Lfj8H03OperatingPoint operating,
    Lfj8H03OutputPlan *plan);

/* Replay the discrete writes from an observed D/E/F register state to the
 * proposed state. Independent same-level writes do not count as edges.
 * Each edge must be representable by one H03 pass in D/E/F order. */
int lfj8_h03_output_plan_matches(const Lfj8H03OutputPlan *plan, uint8_t before, uint8_t after);

/* Resolve the complete D/E/F target from the live mask and ordered writes. */
int lfj8_h03_output_plan_resolve(const Lfj8H03OutputPlan *plan, uint8_t before, uint8_t *after);

#endif
