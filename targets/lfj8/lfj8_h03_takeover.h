#ifndef RBM_LFJ8_H03_TAKEOVER_H
#define RBM_LFJ8_H03_TAKEOVER_H

#include "lfj8_donor_io.h"
#include "lfj8_h03_outputs.h"
#include "lfj8_h03_phase_clock.h"

enum {
    LFJ8_H03_PWM_A_ISOLATED = 1u << 0,
    LFJ8_H03_PWM_B_ISOLATED = 1u << 1,
    LFJ8_H03_PWM_C_ISOLATED = 1u << 2,
    LFJ8_H03_PRESSURE_B_ISOLATED = 1u << 3,
    LFJ8_H03_TIO9_ISOLATED = 1u << 4,
    LFJ8_H03_ALL_SPARE_PWM_ISOLATED = LFJ8_H03_PWM_A_ISOLATED | LFJ8_H03_PWM_B_ISOLATED |
        LFJ8_H03_PWM_C_ISOLATED | LFJ8_H03_PRESSURE_B_ISOLATED | LFJ8_H03_TIO9_ISOLATED
};

typedef struct {
    const Lfj8RegisterIo *io;
    void (*write32)(void *context, uint32_t address, uint32_t value);
    uint32_t (*clock_ticks)(void *context);
    int (*qualified)(void *context);
    void (*arbitrate)(void *context);
    void (*apply)(void *context);
    void (*inhibit)(void *context);
    uint8_t isolated_pwm_mask;
    volatile Lfj8H03PhaseClock *phase_clock;
} Lfj8H03TakeoverOps;

typedef struct {
    const Lfj8H03TakeoverOps *ops;
    uint32_t max_age_ticks;
    uint32_t generation;
    uint32_t command_at;
    uint32_t pressure_word;
    uint8_t shift_mask;
    uint8_t shift_before;
    uint8_t have_generation;
    uint8_t pending; /* Private preparation state. Only apply consumes a ready plan. */
} Lfj8H03Takeover;

/* Install once with stable ops and I/O storage. Callbacks run under the I/O
 * critical section. qualified is a read-only check that returns 1 only with
 * verified physical output authority and service isolation. A separate failure
 * response must cover mode changes and missed phases that block invocation.
 * Both phases screen the OEM monitor and Flash state under the I/O lock.
 * The owner must establish control of executable Flash and state RAM before
 * calling either phase and reinitialize state after surrendering ownership.
 * inhibit carries out the commissioned failure response even when previous
 * outputs are latched. Arbitration and apply use the H03 OEM functions 0717B8
 * and 046900 respectively.
 * With phase_clock set, clock_ticks uses the phase publication timebase;
 * the I/O lock must also exclude that publisher. A command may advance only
 * after the current phase has been taken and while it is fresh.
 * Set each isolated_pwm_mask bit after confirming isolation in the target
 * wiring. The OEM apply callback can drive TIO9/P97 independently of the
 * A/B/C/Pressure B commands and common inhibit. */
int lfj8_h03_takeover_init(Lfj8H03Takeover *state, const Lfj8H03TakeoverOps *ops,
                          uint32_t max_age_ticks);

/* Stage and arbitrate one complete generation. shift_mask is the current
 * D/E/F state (bits 0/1/2), including channels absent from the ordered plan.
 * Replay must reach that state from the current P3DATA command bits.
 * The caller qualifies the observable output mode. command_at is the oldest
 * required sample in this generation, in clock_ticks
 * units. Pass NULL for a failed plan. The caller provides serialized phase
 * invocations and consecutive generations even when an input is missing.
 * A skipped generation, or a skipped apply after a successful prepare,
 * invalidates the new generation and invokes inhibit. */
int lfj8_h03_takeover_prepare(Lfj8H03Takeover *state, const Lfj8H03OutputPlan *plan,
                             uint8_t shift_mask, uint32_t generation, uint32_t command_at);

/* Use the actual locked P3 levels and the plan to calculate the full mask.
 * The caller supplies the intact ordered writes from both donor tasks. */
int lfj8_h03_takeover_prepare_plan(Lfj8H03Takeover *state, const Lfj8H03OutputPlan *plan,
                                  uint32_t generation, uint32_t command_at);

/* Consume a matching generation once if the initial P3 command is still the
 * same. A rejection invokes inhibit. The caller
 * of either phase must skip the original OEM call after this function. */
int lfj8_h03_takeover_apply(Lfj8H03Takeover *state, uint32_t generation);

/* Revoke on a fault event under the same exclusion used for apply.
 * The caller must already hold it across the latch store and this call.
 * This covers an OEM flag that may be cleared before apply. A revoke
 * from within arbitration also cancels that preparation. Keep the
 * generation consumed and invoke the commissioned inhibit callback.
 * For the native fault hooks the linker binds rbm_h03_takeover_state to the
 * existing takeover object. Initialize that object before exposing the hooks. */
void lfj8_h03_takeover_revoke_locked(Lfj8H03Takeover *state);

/* Check while waiting for the stock flag. Fault revokes a staged command
 * under the I/O lock. A fresh publication remains pending for take_phase. */
Lfj8H03PhaseResult lfj8_h03_takeover_check_phase(Lfj8H03Takeover *state);

/* Consume the foreground phase with the same lock used for apply.
 * A fault revokes a staged command and
 * invokes the qualified failure response on a missing or invalid phase.
 * While recovering, reinitialize both the takeover and phase clock under
 * the owner lock with command authority withdrawn. */
Lfj8H03PhaseResult lfj8_h03_takeover_take_phase(Lfj8H03Takeover *state, Lfj8H03PhaseEvent *event);

#endif
