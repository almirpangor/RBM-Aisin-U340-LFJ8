#ifndef RBM_LFJ8_H03_APPLICATION_BINDING_H
#define RBM_LFJ8_H03_APPLICATION_BINDING_H

#include "lfj8_h03_application.h"

/* Link to the existing typed control, communication and workspace fields.
 * These symbols allocate no storage in the binding. */
extern Lfj8H03Takeover rbm_h03_takeover_state;
extern Lfj8H03Cycle rbm_h03_cycle_state;
extern RbmU340eRuntime rbm_h03_runtime_state;
extern Lfj8H03CycleWorkspace rbm_h03_cycle_workspace;
extern Lfj8H03MainResult rbm_h03_main_result;
extern Lfj8H03CycleInput rbm_h03_cycle_input;

/* The target platform supplies stable native ops, the actual startup
 * objects and the qualified inputs required by the application contracts.
 * The I/O exclusion must also cover the AN2 producer. Bootstrap RAM checks
 * and inhibition must operate without reading application state. */
extern const Lfj8H03TakeoverOps rbm_h03_target_takeover_ops;
extern FactoryGearState rbm_h03_target_startup_gear;
extern FactoryHydraulics rbm_h03_target_startup_gp;
/* The U340E target always consumes the configured engine CAN source.
 * It must share the single CAN owner, DTC state and application clock. */
extern const Lfj8H03ApplicationEngine rbm_h03_target_engine;

int rbm_h03_target_ram_owned(void *context);
int rbm_h03_target_clock_ready(void *context);
int rbm_h03_target_initialize(void *context);
Lfj8H03ToyotaEvent rbm_h03_target_take_toyota(void *context, const Lfj8H03SensorSnapshot *sensors,
    Lfj8H03CycleInput *input, Lfj8H03CycleLoad *load, uint32_t *released_at);
void rbm_h03_target_service_phase(void *context, const Lfj8H03PhaseEvent *phase,
    const Lfj8H03SensorSnapshot *sensors, const Lfj8H03MainResult *main);

#endif
