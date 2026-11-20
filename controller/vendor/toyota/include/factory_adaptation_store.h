#ifndef RBM_FACTORY_ADAPTATION_STORE_H
#define RBM_FACTORY_ADAPTATION_STORE_H
#include "factory_learning_state.h"
#define FACTORY_ADAPT_RECORD_BYTES 96u
#define FACTORY_ADAPT_PROFILE_E4R21 0x213006c6u
typedef struct {
    uint8_t learned_flags[2], up_counts[6], down_counts[2];
    int8_t up[18],down[5];
    uint8_t down_seen;
} FactoryAdaptation;
/* Different magic/schema from E4R21 config. Never interprets a legacy record
 * as factory adaptations. New format belongs to this separate project. */
void factory_adaptation_capture(const FactoryLearning *s,FactoryAdaptation *a);
void factory_adaptation_apply(FactoryLearning *s,const FactoryAdaptation *a);
int factory_adaptation_valid(const FactoryAdaptation *a);
int factory_adaptation_encode(uint8_t record[FACTORY_ADAPT_RECORD_BYTES],const FactoryAdaptation *a,uint32_t generation);
int factory_adaptation_decode(const uint8_t record[FACTORY_ADAPT_RECORD_BYTES],FactoryAdaptation *a,uint32_t *generation);
/* Returns slot 0/1, or -1 for no valid record. Equal generations prefer 0;
 * exactly half-range apart is ambiguous and fails closed. Outputs unchanged
 * on -1. A uint32_t generation wrap is explicitly supported. */
int factory_adaptation_load(const uint8_t *slot0,const uint8_t *slot1,FactoryAdaptation *a,uint32_t *generation);
typedef const uint8_t *(*FactoryAdaptRead)(void *context,unsigned slot);
typedef int (*FactoryAdaptWrite)(void *context,unsigned slot,const uint8_t *record,unsigned bytes);
/* Callback must erase/program ONLY the requested inactive 1 KiB page and
 * program bytes in order, with the commit marker last. Full read-back is
 * checked before reporting success. Returns 1 saved, 2 unchanged, 0 failed.
 * idle must be established by the runtime (no actuation/torque transaction).
 * Flash programming/scheduling integration is deliberately outside this API. */
int factory_adaptation_save(const FactoryAdaptation *a,int idle,FactoryAdaptRead read,
    FactoryAdaptWrite write,void *context);
#endif
