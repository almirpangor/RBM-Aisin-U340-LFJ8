#include "h03_native_hooks.h"
#include "lfj8_h03_application.h"
#include "lfj8_h03_target_strategy.h"

/* The converted target always handles the stock strategy call. A missing
 * plan consumes its generation and withdraws authority through the same
 * takeover path as a rejected plan. OEM diagnostics at 036F34 still run. */
int rbm_h03_strategy_callback(void)
{
    const Lfj8H03ApplicationBinding *const binding = &rbm_h03_application_binding;
    const Lfj8H03TakeoverOps *const ops = binding->takeover_ops;
    const Lfj8RegisterIo *const io = ops->io;
    void *const context = io->context;
    const uint32_t saved = io->enter(context);
    if (binding->ram_owned(context) == 1) {
        Lfj8H03Takeover *const state = binding->takeover;
        if (rbm_h03_application.running == 1u && state->ops == ops) {
            const volatile Lfj8H03PhaseClock *const phase = ops->phase_clock;
            const uint32_t generation = state->generation + 1u;
            Lfj8H03StrategySnapshot snapshot = {0};
            if (phase && phase->have_release && !phase->faulted &&
                phase->latest.sequence == phase->consumed &&
                rbm_h03_target_strategy_snapshot(context, phase->consumed, &snapshot) == 1) {
                lfj8_h03_cycle_prepare_outputs(state, binding->main, &rbm_h03_fast_output,
                    snapshot.actuators, &snapshot.oem, snapshot.operating, generation);
            } else {
                lfj8_h03_takeover_prepare_plan(state, NULL, generation, 0u);
            }
        } else {
            state->pending = 0u;
            ops->inhibit(context);
        }
    }
    io->leave(context, saved);
    return RBM_H03_HOOK_HANDLED;
}
