#ifndef RBM_LFJ8_H03_PHASE_STARTUP_H
#define RBM_LFJ8_H03_PHASE_STARTUP_H

#include "lfj8_h03_takeover.h"

typedef struct {
    uint32_t min_period_ticks;
    uint32_t max_period_ticks;
    uint32_t phase_max_age_ticks;
    uint32_t command_max_age_ticks;
} Lfj8H03PhaseStartupConfig;

/* Call with owned storage, a qualified running clock and command authority
 * withdrawn. Keep all native callbacks disconnected until successful init.
 * The same lock excludes the phase publisher and foreground consumer.
 * State and ops->phase_clock are reset together under that lock. With valid
 * pointers and lock callbacks, failure leaves both states disabled. */
int lfj8_h03_phase_startup(Lfj8H03Takeover *state, const Lfj8H03TakeoverOps *ops,
                           const Lfj8H03PhaseStartupConfig *config);

#endif
