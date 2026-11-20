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

typedef enum {
    RBM_U340E_ADAPTATION_INVALID = 0,
    RBM_U340E_ADAPTATION_LOADED,
    RBM_U340E_ADAPTATION_BASELINE_UNPUBLISHED,
    RBM_U340E_ADAPTATION_BASELINE_UNTRUSTED,
} RbmU340eAdaptationResult;

/* Restore at startup before scheduling learning or outputs. The serialized
 * owner supplies a qualified baseline and independent, stable slot snapshots
 * from a last-marker-write store. A NULL slot represents a failed read.
 * Keep the inputs disjoint from the runtime. An invalid call leaves GP intact.
 * Neither baseline outcome writes storage or qualifies actuation. The owner
 * must handle an untrusted store before allowing further saves. */
RbmU340eAdaptationResult rbm_u340e_runtime_restore_adaptation(
    RbmU340eRuntime *runtime, const FactoryAdaptation *baseline,
    const uint8_t *slot0, const uint8_t *slot1);

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

/* Coherent, source-qualified S01-domain operands for 054AB2 and 05518C.
 * The producer must establish the scaling and fallback flag from evidence. */
typedef struct {
    uint32_t sampled_at; /* Oldest operand, in the caller's monotonic clock. */
    int16_t gp_8270;
    int16_t gp_8272;
    int16_t gp_8306;
    int16_t gp_8298;
    int16_t gp_8302;
    int16_t gp_8310;
    int16_t gp_9044;
    int16_t gp_9030;
    uint8_t fallback_5299_bit1; /* Qualified donor mode, 0 or 1. */
    uint8_t coherent;           /* Exactly 1 after producer qualification. */
} RbmU340eQualifiedLoadFeed;

/* Publish before releasing any load consumer for the sample. The serialized
 * owner must reject the cycle on refusal and discard cached inputs on clock
 * discontinuity. now and sampled_at wrap at 2^32; max_age is inclusive and
 * must be below 2^31. Refusal leaves GP intact. Runtime and feed are disjoint. */
int rbm_u340e_runtime_publish_load(RbmU340eRuntime *runtime,
                                  const RbmU340eQualifiedLoadFeed *feed,
                                  uint32_t now, uint32_t max_age);

/* Toyota SECONDARY 054220 -> 05518C. Call once for each executed
 * SECONDARY before MAIN consumes the result. request_1120 is the persistent
 * donor byte, initialized by the caller, and must be disjoint from runtime.
 * Populate GP-8270, -8272, -8306, -8298, -8302, -8310, -7186 and -5299 from
 * coherent donor-domain inputs. inhibit_5250 supplies the shared GP-5250
 * byte also consumed by MAIN. A refusal leaves request_1120 unchanged. */
int rbm_u340e_runtime_secondary_load_qualify(const RbmU340eRuntime *runtime,
                                             uint8_t inhibit_5250, uint8_t *request_1120);

typedef struct {
    uint8_t count_1112;
    uint8_t count_1113;
    uint8_t mode_1114;
    uint8_t flags_1115;
    uint8_t flags_1376;
} RbmU340eRangeState;

typedef struct {
    uint8_t selector; /* Stabilized RBM_U340E_SELECTOR_*. */
    uint8_t range_5722; /* Independent Toyota range/auxiliary inputs. */
    uint8_t request_1120; /* Load qualifier publication from SECONDARY. */
    uint8_t inhibit_5250;
} RbmU340eRangeInputs;

/* Run the range qualifier at FAST 054EB2, after the counter prefix. Use
 * the same qualifier state in MAIN and serialize access from both owners.
 * Initialize these five bytes from the donor startup state. */
int rbm_u340e_range_fast(RbmU340eRangeState *range, const RbmU340eRangeInputs *inputs);

/* Project the range operands of 055138/054350 and run 054D76 and
 * 057694/05780E before 055EA0/0574C4. The caller supplies the other MAIN
 * inputs and stages in donor order. work is the snapshot passed next to
 * rbm_u340e_runtime_gears_outputs. Refusal produces no output permit. */
int rbm_u340e_runtime_main_range(RbmU340eRuntime *runtime, RbmU340eRangeState *range,
                                 const RbmU340eRangeInputs *inputs, FactoryGearState *work);

/* Save the gear/selector subset of 05449A after the full MAIN body. */
int rbm_u340e_runtime_main_range_complete(RbmU340eRuntime *runtime);

#endif
