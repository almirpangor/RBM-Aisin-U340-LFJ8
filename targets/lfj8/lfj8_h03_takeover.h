#ifndef RBM_LFJ8_H03_TAKEOVER_H
#define RBM_LFJ8_H03_TAKEOVER_H

#include "lfj8_donor_io.h"
#include "lfj8_h03_outputs.h"

enum { LFJ8_H03_ALL_SPARE_PWM_ISOLATED = 0x0f };

typedef struct {
    const Lfj8RegisterIo *io;
    void (*write32)(void *context, uint32_t address, uint32_t value);
    uint32_t (*clock_ticks)(void *context);
    int (*qualified)(void *context);
    void (*arbitrate)(void *context);
    void (*apply)(void *context);
    void (*inhibit)(void *context);
    uint8_t isolated_pwm_mask;
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
    uint8_t pending;
} Lfj8H03Takeover;

/* Install once with stable ops and I/O storage. Callbacks run under the I/O
 * critical section. qualified is a read-only check that returns 1 only with
 * verified physical output authority and service isolation. A separate failure
 * response must cover mode changes and missed phases that block invocation.
 * inhibit carries out the commissioned failure response even when previous
 * outputs are latched. Arbitration and apply use the H03 OEM functions 0717B8
 * and 046900 respectively.
 * isolated_pwm_mask is the hardware qualification for unused A/B/C/PC-B. */
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

/* Consume a matching generation once if the initial P3 command is still the
 * same. A rejection invokes inhibit. The caller
 * of either phase must skip the original OEM call after this function. */
int lfj8_h03_takeover_apply(Lfj8H03Takeover *state, uint32_t generation);

#endif
