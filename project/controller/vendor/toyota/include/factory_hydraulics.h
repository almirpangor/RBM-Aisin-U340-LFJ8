#ifndef RBM_FACTORY_HYDRAULICS_H
#define RBM_FACTORY_HYDRAULICS_H
#include "factory_hydraulic_state.h"
#include "factory_adaptation_store.h"
/* Bounded raw GP access for the platform adapter and tests; supports 1/2/4
 * bytes, only a completely mapped contiguous interval. No hardware memory. */
int factory_hydraulics_set(FactoryHydraulics *s,int gp,unsigned bytes,uint32_t value);
int factory_hydraulics_get(const FactoryHydraulics *s,int gp,unsigned bytes,uint32_t *value);
/* Exact contiguous donor main-task block: clear override flag, engagement,
 * phase queue/pressure, special pressure, learning up/down, clear second flag,
 * limit, base, override and final snapshot. No ISR runs during this operation.
 * Atomic in canonical state on failure. External signals must be consistent. */
int factory_hydraulics_main(FactoryHydraulics *s);
/* Exact next contiguous block 054178..05418C, shared with hydraulics.
 * This computes raw donor intervention only; it does not send CAN frames. */
int factory_hydraulics_torque_main(FactoryHydraulics *s);
/* Both adjacent blocks, 054144..05418C, committed atomically. */
int factory_hydraulics_control_main(FactoryHydraulics *s);
/* Exact adjacent calls 05A988 -> 05AD5E. Counter increments remain owned by
 * the scheduler. These are donor ticks; no millisecond period is assumed. */
int factory_hydraulics_fast_learning(FactoryHydraulics *s);
/* Individual task fragments in the same canonical state. The caller owns
 * ordering and must provide all intervening donor computations. These APIs
 * do not claim to execute a complete OEM task or define its wall-clock rate. */
void factory_hydraulics_load_main(FactoryHydraulics *s);
void factory_hydraulics_load_observer(FactoryHydraulics *s);
void factory_hydraulics_counters_begin(FactoryHydraulics *s);
void factory_hydraulics_counters_end(FactoryHydraulics *s);
void factory_hydraulics_capture(const FactoryHydraulics *s,FactoryAdaptation *a);
int factory_hydraulics_restore(FactoryHydraulics *s,const FactoryAdaptation *a);
#endif
