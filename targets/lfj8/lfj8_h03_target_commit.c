#include "h03_native_hooks.h"
#include "lfj8_h03_application.h"

/* The 0x07C10C redirect belongs with the 0x036F30 strategy replacement
 * for the ordinary H03 scheduler. Both must share the active takeover.
 * The monitor profile uses this callback for both redirects, revoking
 * unconditionally while RAM is owned. */
int rbm_h03_commit_callback(void)
{
    const Lfj8H03ApplicationBinding *const binding = &rbm_h03_application_binding;
    const Lfj8H03TakeoverOps *const ops = binding->takeover_ops;
    const Lfj8RegisterIo *const io = ops->io;
    void *const context = io->context;
    const uint32_t saved = io->enter(context);
    /* The RAM owner must withdraw authority before surrendering the arena.
     * While it is lent to service, suppress the OEM apply without touching it. */
    if (binding->ram_owned(context) == 1) {
        Lfj8H03Takeover *const state = binding->takeover;
        if (ops->apply && rbm_h03_application.running == 1u && state->ops == ops) {
            const volatile Lfj8H03PhaseClock *const phase = ops->phase_clock;
            /* Normal H03 runs strategy and apply on adjacent TOP10 releases.
             * The logical output generation is independent of that release. */
            if (phase && phase->latest.sequence - state->prepared_phase == 1u) {
                lfj8_h03_takeover_apply(state, state->generation);
            } else {
                lfj8_h03_takeover_revoke_locked(state);
            }
        } else {
            state->pending = 0u;
            ops->inhibit(context);
        }
    }
    io->leave(context, saved);
    return RBM_H03_HOOK_HANDLED;
}
