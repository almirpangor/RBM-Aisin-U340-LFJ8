#ifndef RBM_FACTORY_CORE_H
#define RBM_FACTORY_CORE_H
#include <stdint.h>

/* Recovered numerical kernels from 89663-52F01, not a complete TCM.
 * Inputs use donor integer units. None of these functions writes GPIO/CAN.
 * Map pointers must reference validated, nondecreasing donor tables.
 * No table resizing, axis sorting, floating point or inferred SI conversion. */
uint16_t factory_interp1(uint16_t x_q8, const uint8_t *table);
uint16_t factory_interp2(uint16_t x_q8, uint16_t y_q8, const uint8_t *table);
uint16_t factory_div_u32_u16(uint32_t numerator, uint16_t denominator);
int16_t factory_atf(uint16_t donor_adc);
uint8_t factory_atf_status(uint16_t donor_adc);
uint16_t factory_period_raw(uint16_t donor_period);
uint8_t factory_speed_code(uint16_t raw, uint8_t *alternate_code);
uint16_t factory_load_code(uint16_t nonnegative_source);

/* Names are RAM offsets from gp=0x03FF4000, deliberately not guessed modes.
 * index_4854 is a requested gear INDEX (0..3), not the physical gear.
 * threshold_override_4862 is only accepted below donor sentinel 0x113F.
 * The wrapper returns 0 without changing state for invalid input state. */
typedef struct {
    uint16_t load_7202;
    uint8_t index_4854;
    uint8_t speed_4549;
    uint8_t flags_4845;
    uint8_t flags_4846;
    uint8_t flags_4844;
    uint8_t flags_7252;
    uint8_t flags_4839;
    uint8_t flags_p1172;
    uint8_t counter_4771;
    uint8_t override_4862;
    uint8_t thresholds_4541[6];
} FactoryRequestState;

void factory_lookup_thresholds(FactoryRequestState *s);
int factory_request_normal(FactoryRequestState *s);
int factory_request_special1(FactoryRequestState *s);
int factory_request_special2(FactoryRequestState *s);
int factory_request_stage(FactoryRequestState *s);

/* SLT numerical characteristic only; input is donor raw command, NOT pressure.
 * Driver conversion is a timer count, NOT an STM32 duty or coil current. */
uint16_t factory_slt_characteristic(uint16_t donor_command_q8);
uint16_t factory_slu_characteristic(uint16_t donor_command_q8);
uint16_t factory_driver_count(uint16_t u_q8); /* valid domain 0..25600 */
/* 055B98 snapshot: selected pressure source and two flag/state writes.
 * Caller supplies a consistent snapshot under its own interrupt exclusion.
 * Values retain donor units; this does not calculate the four sources. */
typedef struct {
    int16_t source_7148, source_7146, source_7144, source_7142;
    int16_t selected_p1158;
    uint8_t flags_4829, flags_4830, flags_9748, flags_4841, flags_9746;
    uint8_t flags_p1156, index_4856;
} FactoryPressureSnapshot;
void factory_pressure_snapshot(FactoryPressureSnapshot *s);
/* 0x055BF4..0x055C3C, excluding hardware dispatch. Donor raw units. */
int16_t factory_slt_select(int16_t base, int16_t correction, int16_t limit,
    int16_t override_value, uint8_t f9748, uint8_t f4830, uint8_t fp1156);
/* 0x0575F0..0x057612, before driver state machine. Output bit0=S1,
 * bit1=S2; 1 is an ON request, not a GPIO voltage. 255 means invalid index. */
uint8_t factory_s1_s2_requests(uint8_t output_index);
/* 0x054D12: donor fault/mode flag projection, physical meanings unresolved. */
uint8_t factory_bank_flags(uint8_t old_4846, uint8_t f7193, uint8_t f7191,
    uint8_t f4844, uint8_t f8438, uint8_t v5138, uint8_t f7189, uint8_t f7187);
#endif

