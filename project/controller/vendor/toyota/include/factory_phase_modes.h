#ifndef RBM_FACTORY_PHASE_MODES_H
#define RBM_FACTORY_PHASE_MODES_H
#include "factory_pressure.h"

typedef struct {
    uint32_t flags;
    uint16_t sample_7100, sample_7094;
    int16_t ratio_7088;
    uint8_t index_4514, index_4519, count_4749, count_4696;
} FactoryQueuedPhase;
typedef struct {
    FactoryPhaseCycle phase; /* Queue slot zero is stored here, not duplicated. */
    FactoryQueuedPhase queued[2];
    int32_t input_9732; /* Remaining three words are phase.inputs_9728. */
    uint8_t index_4851, index_4854, flags_7252, flags_4833, flags_4840, flags_4832;
    uint8_t count_p1440, limit_p1441, count_p1446, count_4696;
    uint8_t count_4693, count_4692, count_4691, count_4746, count_4744, count_4745;
    uint8_t saved_p1464[6], saved_p1470[2], counts_4511[3], output_4508;
} FactoryPhaseModes;

/* Exact saturated signed division helper 012EFC. */
int16_t factory_div_s32_s16(int32_t numerator,int16_t denominator);
/* Individual functions use the same shared state as the full step. Failure
 * leaves caller state untouched. The caller provides a consistent snapshot. */
int factory_phase_enqueue(FactoryPhaseModes *s); /* 059528 */
int factory_phase_pop(FactoryPhaseModes *s);     /* 059800, numerical effects */
int factory_phase_deadline(FactoryPhaseModes *s);/* 0598CC */
int factory_phase_delay32(FactoryPhaseModes *s); /* 05A168, donor indices 3->2 */
int factory_phase_delay31(FactoryPhaseModes *s); /* 05A280, donor indices 3->1 */
int factory_phase_trim(FactoryPhaseModes *s);    /* 05A348 */
/* Full 05934E including the five pressure functions. No task timing, GPIO,
 * new requested-gear calculation or learning updates are invented here. */
int factory_phase_modes_step(FactoryPhaseModes *s);
#endif
