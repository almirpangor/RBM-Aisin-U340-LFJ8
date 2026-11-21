#ifndef RBM_LFJ8_H03_CYCLE_H
#define RBM_LFJ8_H03_CYCLE_H

#include "lfj8_h03_torque.h"
#include "lfj8_h03_takeover.h"
#include "lfj8_h03_slu.h"
#include "rbm_u340e_runtime.h"
#include "rbm_u340e_scheduler.h"

typedef struct {
    RbmU340eScheduler scheduler;
    RbmU340eRangeState range;
    uint32_t last_event;
    uint8_t request_1120;
    uint8_t have_event;
    uint8_t faulted;
    uint8_t require_load_evidence; /* Latched after the first accepted group snapshot. */
} Lfj8H03Cycle;

/* MAIN finishes using the typed gear view before hydraulic processing.
 * They share one caller-owned buffer rather than growing the IRQ stack. */
typedef union {
    FactoryGearState gear;
    FactoryHydraulics hydraulics;
} Lfj8H03CycleWorkspace;

typedef struct {
    RbmU340eQualifiedEngineFeed engine;
    uint32_t command_at; /* Oldest sample across the qualified operands. */
    uint32_t event;      /* Consecutive delivered Toyota IRQ events, modulo 2^32. */
    uint8_t selector;
    uint8_t range_5722;
    uint8_t inhibit_5250;
    uint8_t qualified;   /* Includes the canonical GP, not only engine and range. */
    /* Current permitted manual gear (1..4), or 0 for the Toyota map.
     * Supply a level on each admitted event, including the donor delay.
     * command_at and qualified also cover the driver request, observed gear
     * and current external interlocks. */
    uint8_t requested_gear;
} Lfj8H03CycleInput;

typedef enum {
    LFJ8_H03_LOAD_SECONDARY, /* GP-8270/8272/8306/8298/8302/8310. */
    LFJ8_H03_LOAD_MAIN,      /* GP-9044/9030. */
    LFJ8_H03_LOAD_MODE,      /* GP-5299.1. */
    LFJ8_H03_LOAD_GROUPS,
    LFJ8_H03_LOAD_ALL_GROUPS = (1u << LFJ8_H03_LOAD_GROUPS) - 1u,
} Lfj8H03LoadGroup;

typedef struct {
    uint32_t captured_at; /* Oldest operand within this group. */
    uint32_t generation;
} Lfj8H03LoadStamp;

typedef struct {
    Lfj8H03LoadStamp group[LFJ8_H03_LOAD_GROUPS];
    uint8_t qualified_groups; /* Bit n authorizes group n in the attached sample. */
} Lfj8H03LoadEvidence;

/* Calculate sample->sampled_at from the three groups. The foreground producer
 * owns the coherent copies of the GP-domain operands and their evidence.
 * expected_generation comes from the current acquisition epoch independently
 * of those copies. Times share the qualified wrapping clock. On incomplete,
 * stale, future or cross-epoch evidence returns 0 and preserves oldest_us. */
int lfj8_h03_load_oldest_us(const Lfj8H03LoadEvidence *evidence, uint32_t expected_generation,
                            uint32_t now_us, uint32_t max_age_us, uint32_t *oldest_us);

typedef struct {
    const RbmU340eQualifiedLoadFeed *sample;
    uint32_t now_us;
    uint32_t max_age_us;
    /* Supply group evidence for separately acquired operands. A caller with
     * a source-qualified coherent sample from one acquisition may omit it. */
    const Lfj8H03LoadEvidence *evidence;
    uint32_t generation; /* Current acquisition epoch, not derived from evidence. */
} Lfj8H03CycleLoad;

typedef struct {
    FactoryGearWrites shift;
    Lfj8TorqueDemand torque;
    uint32_t command_at;
    uint8_t gear_4852; /* Donor command index 0..3, distinct from gear observation. */
    uint8_t gear_4848;
    uint8_t valid;
} Lfj8H03MainResult;

typedef struct {
    FactorySLTResult slt;
    FactoryDriverWrite st;
    uint32_t command_at;
    uint8_t valid;
} Lfj8H03FastOutput;

typedef struct {
    Lfj8H03OutputBinding binding;
    const Lfj8H03SltCalibration *slt;
} Lfj8H03ActuatorCalibration;

typedef enum {
    LFJ8_H03_CYCLE_FAULT,
    LFJ8_H03_CYCLE_NO_MAIN,
    LFJ8_H03_CYCLE_MAIN,
} Lfj8H03CycleResult;

/* Initialize after donor startup. The caller owns the initial GP and
 * selector startup values. No startup pressures or gear inputs are assumed. */
int lfj8_h03_cycle_init(Lfj8H03Cycle *cycle, const RbmU340eRangeState *range,
                         uint8_t initial_request_1120);

/* Serialized software path for the recovered FAST, SECONDARY and MAIN
 * fragments. Upstream qualification and the remaining donor stages own the
 * other GP and gear-only producers. The returned writes are logical S1/S2;
 * ST, SLT, shifts with external interlocks and plant authority are separate.
 *
 * Invoke only on a delivered timer event, at the verified Toyota cadence.
 * An exact repeated event is ignored. A gap or invalid/incomplete sample
 * stops publication until reseeded. On fault discard runtime and workspace
 * before reuse because an admitted stage may have partially modified them.
 * All objects are disjoint, and result is valid only for CYCLE_MAIN. */
Lfj8H03CycleResult lfj8_h03_cycle_tick(Lfj8H03Cycle *cycle, RbmU340eRuntime *runtime,
                                      const Lfj8H03CycleInput *input, Lfj8H03CycleWorkspace *work,
                                      Lfj8H03MainResult *result);

/* Publish the qualified donor load before advancing a new Toyota event.
 * The caller supplies the source-qualified snapshot and a continuous
 * clock shared by sampled_at, command_at and now_us. max_age_us is
 * inclusive and less than half a clock wrap. Both source timestamps
 * must be in the past half-wrap, including now. A refused load latches
 * a cycle fault without writing GP or advancing the scheduler. MAIN's
 * command timestamp includes the oldest load operand. Otherwise the
 * same serialization and recovery rules as cycle_tick apply. When group
 * evidence is supplied, sampled_at must match its oldest capture exactly.
 * Subsequent events require group evidence until cycle reinitialization. */
Lfj8H03CycleResult lfj8_h03_cycle_tick_with_load(Lfj8H03Cycle *cycle, RbmU340eRuntime *runtime,
    const Lfj8H03CycleInput *input, Lfj8H03CycleWorkspace *work, Lfj8H03MainResult *result,
    Lfj8H03CycleLoad load);

typedef struct {
    const Lfj8H03SluSnapshot *snapshot;
    Lfj8H03SluState *state;
    Lfj8H03SluOutput *output;
} Lfj8H03CycleSlu;

/* Run the numerical SLU chain during each admitted SECONDARY, including
 * SECONDARY releases without MAIN. The snapshot must match that event.
 * Use load.now_us and load.max_age_us for the combined oldest operand.
 * Initialize SLU state and GP-4735 from qualified donor startup state.
 * This call clears the logical SLU output before processing an event.
 * On a cycle fault discard the SLU state together with the runtime.
 * The output has donor units. Physical actuation needs a separate binding. */
Lfj8H03CycleResult lfj8_h03_cycle_tick_with_slu(Lfj8H03Cycle *cycle, RbmU340eRuntime *runtime,
    const Lfj8H03CycleInput *input, Lfj8H03CycleWorkspace *work, Lfj8H03MainResult *result,
    Lfj8H03CycleLoad load, Lfj8H03CycleSlu slu);

/* Read the SLT operands already published by MAIN. Use them at donor FAST
 * 05AF96/055BF4 with the separately qualified correction state. */
int lfj8_h03_cycle_slt_inputs(const FactoryHydraulics *gp, FactorySLTInputs *out);

/* From phase 3, join MAIN's S1/S2 with FAST's SLT and optional ST write.
 * The foreground owner supplies a coherent pair in donor write order, with
 * times in the takeover clock. Both records must have passed their stages.
 * The older sample determines expiry. Invalid input invokes the same
 * failure response as an unsuccessful generation. The actual D/E/F level
 * transition is derived from P3 under the takeover lock. */
int lfj8_h03_cycle_prepare_outputs(Lfj8H03Takeover *takeover, const Lfj8H03MainResult *main,
                                     const Lfj8H03FastOutput *fast,
                                     const Lfj8H03ActuatorCalibration *calibration,
                                     const Lfj8H03OemOutputState *oem, Lfj8H03OperatingPoint operating,
                                     uint32_t generation);

#endif
