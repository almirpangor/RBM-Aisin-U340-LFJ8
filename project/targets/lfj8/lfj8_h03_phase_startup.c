#include "lfj8_h03_phase_startup.h"

int lfj8_h03_phase_startup(Lfj8H03Takeover *state, const Lfj8H03TakeoverOps *ops,
                           const Lfj8H03PhaseStartupConfig *config)
{
    if (!state || !ops || !config || !ops->phase_clock || !ops->io ||
        !ops->io->enter || !ops->io->leave) {
        return 0;
    }
    const Lfj8RegisterIo *const io = ops->io;
    const uint32_t saved = io->enter(io->context);
    const int ready = lfj8_h03_takeover_init(state, ops, config->command_max_age_ticks) &&
        lfj8_h03_phase_clock_init(ops->phase_clock, ops->clock_ticks(io->context),
                                  config->min_period_ticks, config->max_period_ticks,
                                  config->phase_max_age_ticks);

    if (!ready) {
        state->ops = NULL;
        *ops->phase_clock = (Lfj8H03PhaseClock){.faulted = 1u};
    }
    io->leave(io->context, saved);
    return ready;
}
