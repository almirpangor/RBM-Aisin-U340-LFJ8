#ifndef RBM_U340E_RUNTIME_H
#define RBM_U340E_RUNTIME_H

#include "factory_gears.h"
#include "factory_hydraulics.h"

typedef struct {
    /* Canonical GP for the 93 shared bytes and all hydraulic-only fields.
     * The scheduler runs the hydraulic, load and counter fragments here. */
    FactoryHydraulics gp;
    /* Private to the gear adapter. Read through snapshot_gears to see GP. */
    FactoryGearState gear_state;
    uint8_t initialized;
} RbmU340eRuntime;

/* Zero-initialize the runtime before first use. The owner must supply qualified
 * donor startup snapshots. Reject conflicting shared GP without changing the
 * runtime. No default for an in-gear state or any raw input is supplied. */
int rbm_u340e_runtime_init(RbmU340eRuntime *runtime, const FactoryGearState *gear,
                           const FactoryHydraulics *gp);

/* Project current GP and private gear state into caller-owned workspace. The
 * scheduler may update gear-only inputs there. Publish shared inputs in gp. */
int rbm_u340e_runtime_snapshot_gears(const RbmU340eRuntime *runtime, FactoryGearState *work);

/* Execute the adjacent donor 055EA0 -> 0574C4 S1/S2 fragment. Refresh the
 * shared fields from gp before processing and publish them only on success.
 * The runtime is unchanged and writes.count is zero on failure. Work is
 * scratch and can change. All arguments must refer to separate objects.
 * Serialize this with other GP stages and run the intervening donor stages
 * before calling factory_hydraulics_control_main. Writes are logical. */
int rbm_u340e_runtime_gears_outputs(RbmU340eRuntime *runtime, FactoryGearState *work,
                                    FactoryGearWrites *writes);

#endif
