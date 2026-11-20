#include "lfj8_h03_takeover.h"

#define H03_SERVICE_MODE UINT32_C(0x804887)
#define H03_EVENT_SUSPENDED UINT32_C(0x80801C)
#define H03_MONITOR_FLAGS UINT32_C(0x808580)
#define H03_MONITOR_CHECKSUM_REMAINING UINT32_C(0x808DA4)
#define H03_MONITOR_COPY_REMAINING UINT32_C(0x808DA8)
#define H03_FCNT1 UINT32_C(0x8007E2)
#define H03_P3DATA UINT32_C(0x800703)
#define H03_STARTUP_COUNT UINT32_C(0x80621A)
#define SERIAL_HALF_RANGE UINT32_C(0x80000000)

enum { TAKEOVER_READY = 1, TAKEOVER_PREPARING };

static const uint32_t shift_final[] = {0x8063D7, 0x8063DA, 0x8063DD};
static const uint32_t pwm_proposal[] = {0x804F6C, 0x804F78, 0x804F84, 0x804F94};
static const uint32_t pwm_final[] = {0x804F74, 0x804F80, 0x804F8C, 0x804F9C};
static const uint32_t output_guards[] = {
    0x8063AF, 0x8063B7, 0x8063C4, 0x806356, 0x8063F2,
    0x80636E, 0x80636F, 0x806370, 0x80636D,
    0x8065BA, 0x8065B8, 0x8065B7, 0x8065B6,
};

static int qualified(const Lfj8H03Takeover *state)
{
    const Lfj8H03TakeoverOps *const ops = state->ops;
    const Lfj8RegisterIo *const io = ops->io;
    void *const context = io->context;

    const uint16_t startup_count = io->read16(context, H03_STARTUP_COUNT);

    /* The 002E80 session close does not cancel the ADC0 monitor work or
     * restore the flash mode. Check these independently under the lock. */
    if (startup_count <= 2u || startup_count >= 0x8000u ||
        io->read8(context, H03_SERVICE_MODE) == 4u ||
        io->read8(context, H03_EVENT_SUSPENDED) != 0u ||
        io->read8(context, H03_FCNT1) != 0u ||
        (io->read8(context, H03_MONITOR_FLAGS) & 0x20u) != 0u ||
        io->read32(context, H03_MONITOR_CHECKSUM_REMAINING) != 0u ||
        io->read32(context, H03_MONITOR_COPY_REMAINING) != 0u ||
        ops->qualified(context) != 1) {
        return 0;
    }
    for (size_t i = 0; i < sizeof(output_guards) / sizeof(output_guards[0]); ++i) {
        if (io->read8(context, output_guards[i]) != 0u) {
            return 0;
        }
    }
    const uint32_t now = ops->clock_ticks(context);
    const volatile Lfj8H03PhaseClock *const phase = ops->phase_clock;
    return now - state->command_at < state->max_age_ticks &&
        (!phase || (phase->have_release && !phase->faulted &&
                    phase->latest.sequence == phase->consumed &&
                    now - phase->latest.released_at <= phase->max_age));
}

static uint8_t read_shift_levels(const Lfj8RegisterIo *io)
{
    const unsigned p3 = io->read8(io->context, H03_P3DATA);
    return (uint8_t)((p3 >> 7) | ((p3 >> 5) & 2u) | ((p3 >> 3) & 4u));
}

static void publish_proposals(const Lfj8H03Takeover *state)
{
    const Lfj8H03TakeoverOps *const ops = state->ops;
    const Lfj8RegisterIo *const io = ops->io;
    void *const context = io->context;

    for (size_t i = 0; i < sizeof(shift_final) / sizeof(shift_final[0]); ++i) {
        io->write8(context, shift_final[i] - 2u, (uint8_t)(((unsigned)state->shift_mask >> i) & 1u));
    }
    ops->write32(context, 0x80508C, state->pressure_word);
    for (size_t i = 0; i < sizeof(pwm_proposal) / sizeof(pwm_proposal[0]); ++i) {
        ops->write32(context, pwm_proposal[i], 0u);
    }
}

static int matching_commands(const Lfj8H03Takeover *state)
{
    const Lfj8RegisterIo *const io = state->ops->io;
    void *const context = io->context;

    for (size_t i = 0; i < sizeof(shift_final) / sizeof(shift_final[0]); ++i) {
        if (io->read8(context, shift_final[i]) != (((unsigned)state->shift_mask >> i) & 1u)) {
            return 0;
        }
    }
    if (io->read32(context, 0x805094) != state->pressure_word) {
        return 0;
    }
    for (size_t i = 0; i < sizeof(pwm_final) / sizeof(pwm_final[0]); ++i) {
        if (io->read32(context, pwm_final[i]) != 0u) {
            return 0;
        }
    }
    return 1;
}

int lfj8_h03_takeover_init(Lfj8H03Takeover *state, const Lfj8H03TakeoverOps *ops,
                          uint32_t max_age_ticks)
{
    if (!state) {
        return 0;
    }
    *state = (Lfj8H03Takeover){0};
    if (!ops || !ops->io || !ops->io->read8 || !ops->io->read16 ||
        !ops->io->read32 || !ops->io->write8 || !ops->io->enter || !ops->io->leave ||
        !ops->write32 || !ops->clock_ticks ||
        !ops->qualified || !ops->arbitrate || !ops->apply || !ops->inhibit ||
        ops->isolated_pwm_mask != LFJ8_H03_ALL_SPARE_PWM_ISOLATED ||
        max_age_ticks == 0u || max_age_ticks >= SERIAL_HALF_RANGE) {
        return 0;
    }
    state->ops = ops;
    state->max_age_ticks = max_age_ticks;
    return 1;
}

static int prepare(Lfj8H03Takeover *state, const Lfj8H03OutputPlan *plan,
                   const uint8_t *expected_mask, uint32_t generation, uint32_t command_at)
{
    if (!state || !state->ops) {
        return 0;
    }
    const Lfj8H03TakeoverOps *const ops = state->ops;
    const Lfj8RegisterIo *const io = ops->io;
    void *const context = io->context;
    const uint32_t saved = io->enter(context);
    const uint32_t advance = generation - state->generation;

    const int missed_apply = state->pending;
    const int consecutive = !state->have_generation || advance == 1u;
    state->pending = 0;
    if (!state->have_generation || (advance != 0u && advance < SERIAL_HALF_RANGE)) {
        state->generation = generation;
        state->have_generation = 1;
        state->command_at = command_at;
        if (consecutive && !missed_apply && qualified(state)) {
            const uint8_t before = read_shift_levels(io);
            uint8_t shift_mask;
            if (lfj8_h03_output_plan_resolve(plan, before, &shift_mask) &&
                (!expected_mask || *expected_mask == shift_mask)) {
                state->shift_before = before;
                state->shift_mask = shift_mask;
                state->pressure_word = plan->pressure_binary32;
                publish_proposals(state);
                state->pending = TAKEOVER_PREPARING;
                ops->arbitrate(context);
                const int ready = state->pending == TAKEOVER_PREPARING &&
                    matching_commands(state) && qualified(state) && read_shift_levels(io) == before;
                if (state->pending != TAKEOVER_PREPARING) {
                    /* A nested fault already withdrew authority under this lock. */
                    io->leave(context, saved);
                    return 0;
                }
                if (ready && ops->phase_clock) {
                    state->prepared_phase = ops->phase_clock->latest.sequence;
                }
                state->pending = ready ? TAKEOVER_READY : 0u;
            }
        }
    }
    const int accepted = state->pending == TAKEOVER_READY;
    if (!accepted) {
        ops->inhibit(context);
    }
    io->leave(context, saved);
    return accepted;
}

int lfj8_h03_takeover_prepare(Lfj8H03Takeover *state, const Lfj8H03OutputPlan *plan,
                             uint8_t shift_mask, uint32_t generation, uint32_t command_at)
{
    return prepare(state, plan, &shift_mask, generation, command_at);
}

int lfj8_h03_takeover_prepare_plan(Lfj8H03Takeover *state, const Lfj8H03OutputPlan *plan,
                                  uint32_t generation, uint32_t command_at)
{
    return prepare(state, plan, NULL, generation, command_at);
}

int lfj8_h03_takeover_apply(Lfj8H03Takeover *state, uint32_t generation)
{
    if (!state || !state->ops) {
        return 0;
    }
    const Lfj8H03TakeoverOps *const ops = state->ops;
    const Lfj8RegisterIo *const io = ops->io;
    void *const context = io->context;
    const uint32_t saved = io->enter(context);
    const int ready = state->pending == TAKEOVER_READY;
    state->pending = 0;
    const int accepted = ready && generation == state->generation &&
        qualified(state) && matching_commands(state) && read_shift_levels(io) == state->shift_before;
    if (accepted) {
        ops->apply(context);
    } else {
        ops->inhibit(context);
    }
    io->leave(context, saved);
    return accepted;
}

void lfj8_h03_takeover_revoke_locked(Lfj8H03Takeover *state)
{
    if (!state || !state->ops) {
        return;
    }
    const Lfj8H03TakeoverOps *const ops = state->ops;
    state->pending = 0;
    ops->inhibit(ops->io->context);
}

static Lfj8H03PhaseResult check_phase(Lfj8H03Takeover *state, Lfj8H03PhaseEvent *event,
                                     int consume)
{
    if (!state || !state->ops || !state->ops->phase_clock) {
        if (event) {
            *event = (Lfj8H03PhaseEvent){0};
        }
        return LFJ8_H03_PHASE_FAULT;
    }
    const Lfj8H03TakeoverOps *const ops = state->ops;
    const Lfj8RegisterIo *const io = ops->io;
    void *const context = io->context;
    const uint32_t saved = io->enter(context);
    const uint32_t now = ops->clock_ticks(context);
    const Lfj8H03PhaseResult result = consume
        ? lfj8_h03_phase_clock_take(ops->phase_clock, now, event)
        : lfj8_h03_phase_clock_check(ops->phase_clock, now);
    if (result == LFJ8_H03_PHASE_FAULT) {
        state->pending = 0;
        ops->inhibit(context);
    }
    io->leave(context, saved);
    return result;
}

Lfj8H03PhaseResult lfj8_h03_takeover_check_phase(Lfj8H03Takeover *state)
{
    return check_phase(state, NULL, 0);
}

Lfj8H03PhaseResult lfj8_h03_takeover_take_phase(Lfj8H03Takeover *state, Lfj8H03PhaseEvent *event)
{
    return check_phase(state, event, 1);
}
