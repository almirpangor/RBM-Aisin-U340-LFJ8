#include "factory_hydraulics.h"
#include "factory_learning.h"
#include "factory_phase_modes.h"
#include "factory_core.h"
#include "factory_inputs.h"
#include "factory_torque.h"
#include <stddef.h>
#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error Transfer tables require a little-endian host/target
#endif
/* All component structures fit 255 bytes; only canonical position needs 16.
 * This avoids two padding/offset bytes in every Flash transfer-table entry. */
typedef struct { uint16_t pos;uint8_t member,bytes; } Transfer;
_Static_assert(sizeof(FactoryLearning)<256 && sizeof(FactoryPhaseModes)<256,"transfer member width");
_Static_assert(sizeof(FactoryLoadInputs)<256,"input transfer member width");
_Static_assert(sizeof(FactoryTorque)<256,"torque transfer member width");
#include "hydraulic_mapping.h"
static int position(int gp,unsigned bytes) {
    if(bytes!=1&&bytes!=2&&bytes!=4) return -1;
    for(unsigned i=0;i<sizeof ranges/sizeof ranges[0];++i) {
        int delta=gp-ranges[i].gp;
        if(delta>=0&&(unsigned)delta+bytes<=ranges[i].len) return ranges[i].pos+delta;
    }
    return -1;
}
int factory_hydraulics_set(FactoryHydraulics *s,int gp,unsigned bytes,uint32_t value) {
    int p=position(gp,bytes);if(!s||p<0) return 0;
    for(unsigned i=0;i<bytes;++i) s->data[p+i]=(uint8_t)(value>>(8*i));return 1;
}
int factory_hydraulics_get(const FactoryHydraulics *s,int gp,unsigned bytes,uint32_t *value) {
    int p=position(gp,bytes);if(!s||!value||p<0) return 0;
    uint32_t v=0;for(unsigned i=0;i<bytes;++i) v|=(uint32_t)s->data[p+i]<<(8*i);*value=v;return 1;
}
/* Keep one copy: LTO otherwise expands this loop into each hydraulic stage,
 * increasing the measured Cortex-M3 image by about 0.8 KiB. */
__attribute__((noinline)) static void transfer(FactoryHydraulics *s,void *object,const Transfer *map,unsigned n,int write) {
    uint8_t *p=object;
    for(unsigned i=0;i<n;++i) for(unsigned k=0;k<map[i].bytes;++k) {
        if(write) s->data[map[i].pos+k]=p[map[i].member+k];
        else p[map[i].member+k]=s->data[map[i].pos+k];
    }
}
#define TRANSFER(type,object,write) transfer(s,object,map_##type,sizeof map_##type/sizeof map_##type[0],write)
void factory_hydraulics_load_main(FactoryHydraulics *s) {
    if(!s) return;FactoryLoadInputs v;TRANSFER(FactoryLoadInputs,&v,0);
    factory_load_main(&v);TRANSFER(FactoryLoadInputs,&v,1);
}
void factory_hydraulics_load_observer(FactoryHydraulics *s) {
    if(!s) return;FactoryLoadInputs v;TRANSFER(FactoryLoadInputs,&v,0);
    factory_load_observer(&v);TRANSFER(FactoryLoadInputs,&v,1);
}
void factory_hydraulics_counters_begin(FactoryHydraulics *s) {
    if(s) factory_counter_banks(s->data+HYDRAULIC_COUNTER_BASE,s->data[HYDRAULIC_CLOCK_PHASE]);
}
void factory_hydraulics_counters_end(FactoryHydraulics *s) {
    if(s) ++s->data[HYDRAULIC_CLOCK_PHASE];
}
static int main_step(FactoryHydraulics *s) {
    union { FactoryLearning learn;FactoryPhaseModes phase;FactoryPressureSpecial special;
        FactoryPressureLimit limit;FactoryBasePressure base;FactoryPressureOverride over;
        FactoryPressureSnapshot snapshot; } w;
    s->data[HYDRAULIC_FLAGS_4841]&=(uint8_t)~4u;
    TRANSFER(FactoryLearning,&w.learn,0);
    if(!factory_engagement_step(&w.learn)) return 0;
    TRANSFER(FactoryLearning,&w.learn,1);
    TRANSFER(FactoryPhaseModes,&w.phase,0);
    if(!factory_phase_modes_step(&w.phase)) return 0;
    TRANSFER(FactoryPhaseModes,&w.phase,1);
    TRANSFER(FactoryPressureSpecial,&w.special,0);factory_pressure_special(&w.special);TRANSFER(FactoryPressureSpecial,&w.special,1);
    TRANSFER(FactoryLearning,&w.learn,0);
    if(!factory_learning_up(&w.learn)||!factory_learning_down(&w.learn)) return 0;
    TRANSFER(FactoryLearning,&w.learn,1);
    s->data[HYDRAULIC_FLAGS_4841]&=(uint8_t)~8u;
    TRANSFER(FactoryPressureLimit,&w.limit,0);
    if(!factory_pressure_limit(&w.limit)) return 0;
    TRANSFER(FactoryPressureLimit,&w.limit,1);
    TRANSFER(FactoryBasePressure,&w.base,0);factory_base_pressure(&w.base);TRANSFER(FactoryBasePressure,&w.base,1);
    TRANSFER(FactoryPressureOverride,&w.over,0);factory_pressure_override(&w.over);TRANSFER(FactoryPressureOverride,&w.over,1);
    TRANSFER(FactoryPressureSnapshot,&w.snapshot,0);factory_pressure_snapshot(&w.snapshot);TRANSFER(FactoryPressureSnapshot,&w.snapshot,1);
    return 1;
}
int factory_hydraulics_main(FactoryHydraulics *s) {
    if(!s) return 0;FactoryHydraulics t=*s;if(!main_step(&t)) return 0;*s=t;return 1;
}
static int torque_step(FactoryHydraulics *s) {
    FactoryTorque value;TRANSFER(FactoryTorque,&value,0);
    if(!factory_torque_step(&value)) return 0;TRANSFER(FactoryTorque,&value,1);return 1;
}
int factory_hydraulics_torque_main(FactoryHydraulics *s) {
    if(!s) return 0;FactoryHydraulics t=*s;if(!torque_step(&t)) return 0;*s=t;return 1;
}
int factory_hydraulics_control_main(FactoryHydraulics *s) {
    if(!s) return 0;FactoryHydraulics t=*s;if(!main_step(&t)||!torque_step(&t)) return 0;*s=t;return 1;
}
int factory_hydraulics_fast_learning(FactoryHydraulics *s) {
    if(!s) return 0;FactoryLearning value;TRANSFER(FactoryLearning,&value,0);
    if(!factory_learning_up_observer(&value)||!factory_learning_down_observer(&value)) return 0;
    TRANSFER(FactoryLearning,&value,1);return 1;
}
void factory_hydraulics_capture(const FactoryHydraulics *s,FactoryAdaptation *a) {
    if(!s||!a) return;FactoryLearning value;
    /* read-only transfer; copy to retain const-correctness of canonical state */
    for(unsigned i=0;i<sizeof map_FactoryLearning/sizeof map_FactoryLearning[0];++i) {
        const Transfer *m=map_FactoryLearning+i;
        for(unsigned k=0;k<m->bytes;++k) ((uint8_t*)&value)[m->member+k]=s->data[m->pos+k];
    }
    factory_adaptation_capture(&value,a);
}
int factory_hydraulics_restore(FactoryHydraulics *s,const FactoryAdaptation *a) {
    if(!s||!factory_adaptation_valid(a)) return 0;FactoryLearning value;TRANSFER(FactoryLearning,&value,0);
    factory_adaptation_apply(&value,a);TRANSFER(FactoryLearning,&value,1);return 1;
}
