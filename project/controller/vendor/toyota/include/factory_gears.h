#ifndef RBM_FACTORY_GEARS_H
#define RBM_FACTORY_GEARS_H
#include "factory_gears_state.h"
#include "factory_outputs.h"

/* GP snapshots, not physical units. Gear indices 0..3; b4862 is 0..7.
 * No GPIO, interrupt, scheduler or CAN side effects. Caller supplies an atomic
 * snapshot. Public functions return 0 without mutation for invalid state.
 * Numeric suffixes are donor entry addresses, not guessed feature names. */
int factory_gears_step(FactoryGearState *s); /* Full 055EA0 */
typedef struct { uint8_t count; FactoryDriverWrite writes[4]; } FactoryGearWrites;
/* Exact adjacent calls at 054128..05412C: 055EA0 -> 0574C4 -> dispatcher.
 * State and ordered low-level write requests commit together on success.
 * This stops at 01DD02: it does not perform physical output writes. */
int factory_gears_outputs_step(FactoryGearState *s,FactoryGearWrites *writes);
#define FACTORY_GEAR_ENTRIES(X) \
    X(57bf2) X(57d78) X(5769a) X(57b6a) X(56484) X(57c6c) X(5608a) \
    X(57cc6) X(56152) X(561e4) X(5631a) X(56348) X(56408) \
    X(578f0) X(57a3e) X(57a78) X(57aac) X(57ac8) X(57ade) X(57b0c) \
    X(565ce) X(56eda) X(571e2) X(57210) X(5715e) X(571b4) X(5722e) X(57074)
#define DECLARE_GEAR(a) int factory_gear_##a(FactoryGearState *s);
FACTORY_GEAR_ENTRIES(DECLARE_GEAR)
#undef DECLARE_GEAR
/* Pure return-value helpers commit their state changes only on success. */
int factory_gear_57b8a(FactoryGearState *s,int8_t *delta);
int factory_gear_5641e(FactoryGearState *s,uint8_t *count);
int factory_gear_567b6(FactoryGearState *s,uint8_t *index);
int factory_gear_56b88(FactoryGearState *s,uint8_t *index);
int factory_gear_5737e(FactoryGearState *s,uint8_t *index);
int factory_gear_5724c(FactoryGearState *s,uint8_t channel);
#endif
