#ifndef RBM_U340E_RUNTIME_H
#define RBM_U340E_RUNTIME_H

#include "factory_gears.h"
#include "factory_hydraulics.h"

enum { RBM_U340E_GEAR_SHARED_BYTES = 93 };

typedef struct {
    /* Canonical GP for the 93 shared bytes and all hydraulic-only fields.
     * The scheduler runs the hydraulic, load and counter fragments here. */
    FactoryHydraulics gp;
    /* Native bytes of gear-only fields, private to the adapter. Use
     * snapshot_gears for a complete, naturally aligned working structure. */
    uint8_t gear_private[sizeof(FactoryGearState) - RBM_U340E_GEAR_SHARED_BYTES];
    uint8_t initialized;
} RbmU340eRuntime;

/* Zero-initialize the runtime before first use. The owner must supply qualified
 * donor startup snapshots. Reject conflicting shared GP without changing the
 * runtime. No default for an in-gear state or any raw input is supplied. */
int rbm_u340e_runtime_init(RbmU340eRuntime *runtime, const FactoryGearState *gear,
                           const FactoryHydraulics *gp);

/* Project current GP and private gear state into caller-owned workspace. The
 * scheduler may update gear-only inputs there. Publish shared inputs in gp.
 * Keep the typed workspace disjoint from the runtime and use it within the
 * same serialized gear step. */
int rbm_u340e_runtime_snapshot_gears(const RbmU340eRuntime *runtime, FactoryGearState *work);

/* Execute the adjacent donor 055EA0 -> 0574C4 S1/S2 fragment. Refresh the
 * shared fields from gp before processing and publish them only on success.
 * The runtime is unchanged on failure. A separate writes object has a zero
 * count on failure. Work is scratch and can change. All arguments must
 * refer to separate objects.
 * Serialize this with other GP stages and run the intervening donor stages
 * before calling factory_hydraulics_control_main. Writes are logical. */
int rbm_u340e_runtime_gears_outputs(RbmU340eRuntime *runtime, FactoryGearState *work,
                                    FactoryGearWrites *writes);

/* Coherent TA2005 operands after 06E856 and 06ED70. The owner checks
 * source selection and freshness before supplying this snapshot.
 * FAD8/F9E9 are raw receiver values and are outside this contract. */
typedef struct {
    uint16_t fa62; /* Engine speed in eighths of a revolution per minute. */
    uint16_t fd10; /* Bit 12 marks the TA2005 coolant fallback path. */
    uint8_t f9b8; /* Coolant in integer Celsius + 50. FF is unavailable. */
    uint8_t e026; /* Bit 1 is the TA2005 engine speed failure flag. */
    uint8_t coherent;
} RbmU340eQualifiedEngineFeed;

typedef struct {
    uint16_t speed_9306;
    uint16_t coolant_9006;
} RbmU340eMainEngineInputs;

/* Prepare donor MAIN operands and merge GP-8677.4 into the runtime. The
 * scheduler owns these disjoint objects. A refusal leaves both outputs
 * unchanged. Run the two publishers at their own MAIN call sites, using
 * the same successful snapshot. The numeric fallback grants no permit. */
int rbm_u340e_runtime_prepare_engine(RbmU340eRuntime *runtime,
                                    const RbmU340eQualifiedEngineFeed *qualified,
                                    RbmU340eMainEngineInputs *prepared);

/* Toyota 0540F4 -> 055336 (ECT) and 054110 -> 054D6A (engine speed). */
int rbm_u340e_runtime_main_coolant(RbmU340eRuntime *runtime,
                                 const RbmU340eMainEngineInputs *prepared);
int rbm_u340e_runtime_main_engine_speed(RbmU340eRuntime *runtime,
                                      const RbmU340eMainEngineInputs *prepared);

#endif
