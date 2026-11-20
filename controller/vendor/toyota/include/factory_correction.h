#ifndef RBM_FACTORY_CORRECTION_H
#define RBM_FACTORY_CORRECTION_H
#include <stdint.h>
typedef struct {
    uint32_t flags_9748;
    int32_t history_p1524[5];
    int32_t integral_p1552,state_p1556,filter_p1560,filter_p1564,filter_p1568,previous_p1572;
    uint16_t input_7184;
    int16_t input_7206,previous_p1548,memory_p1550,output_7140;
    uint8_t index_4514,index_4545,flags_4842,flags_4830,count_4696;
    uint8_t count_p1544,count_p1545,flags_p1546;
} FactoryPressureCorrection;
/* Donor 05AF96 reads these three stack slots on its inactive path without
 * initializing them. Explicit inputs let the exact numerical port be checked
 * against arbitrary donor stack contents without introducing C undefinedness. */
typedef struct { int32_t slot28,slot36,slot40; } FactoryCorrectionScratch;
/* 05B30A: exact partial-product arithmetic, including the high-byte truncation.
 * This is not advertised as a general signed 32x32 Q16 multiply. */
int32_t factory_correction_multiply(int32_t a,int32_t b);
/* 05B35E: signed 24-bit saturation, latching bit0 of supplied flags. */
int32_t factory_correction_saturate(int32_t value,uint8_t *flags);
/* 05AF96 including both helpers. Original GP and scratch effects.
 * Inputs use donor units. Index guards: 4514<=5,4545<=6. Atomic on failure. */
int factory_pressure_correction_raw(FactoryPressureCorrection *s,FactoryCorrectionScratch *scratch);
/* Deterministic integration entry: holds three inactive filter words instead
 * of copying unknown donor stack contents. They are reset before the next
 * active calculation. All active calculations and control outputs are retained.
 * This deliberate normalization is documented and tested, not hidden as a
 * byte-identical copy of inactive donor RAM. */
int factory_pressure_correction(FactoryPressureCorrection *s);
typedef struct {
    int16_t selected_p1158,limit_7138,override_7134;
    uint8_t flags_p1156;
} FactorySLTInputs;
typedef struct { int16_t selected_7244;uint16_t characteristic_7132; } FactorySLTResult;
/* Numerical chain 05AF96 -> 055BF4..055C3C. Same canonical inactive-state
 * normalization as above. No physical duty, coil-current or driver conversion. */
int factory_slt_correction_step(FactoryPressureCorrection *s,const FactorySLTInputs *in,FactorySLTResult *out);
#endif
