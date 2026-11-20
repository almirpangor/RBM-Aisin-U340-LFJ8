#include "lfj8_h03_phase_clock.h"

#define SERIAL_HALF_RANGE UINT32_C(0x80000000)

int lfj8_h03_phase_clock_init(volatile Lfj8H03PhaseClock *clock, uint32_t now,
                              uint32_t min_period, uint32_t max_period, uint32_t max_age)
{
    if (!clock) {
        return 0;
    }
    const int valid = min_period != 0u && max_period >= min_period &&
        max_period < SERIAL_HALF_RANGE && max_period - min_period < min_period &&
        max_age < min_period;
    *clock = (Lfj8H03PhaseClock){
        .latest = {.released_at = now}, .min_period = min_period,
        .max_period = max_period, .max_age = max_age, .faulted = (uint8_t)!valid,
    };
    return valid;
}

void lfj8_h03_phase_clock_release(volatile Lfj8H03PhaseClock *clock, uint32_t now)
{
    if (!clock || !clock->min_period || clock->faulted) {
        return;
    }
    const uint32_t elapsed = now - clock->latest.released_at;
    if (clock->latest.sequence != clock->consumed || elapsed > clock->max_period ||
        (clock->have_release && elapsed < clock->min_period)) {
        clock->faulted = 1u;
        return;
    }
    clock->latest.released_at = now;
    ++clock->latest.sequence;
    clock->have_release = 1u;
}

Lfj8H03PhaseResult lfj8_h03_phase_clock_check(volatile Lfj8H03PhaseClock *clock,
                                             uint32_t now)
{
    if (!clock || !clock->min_period || clock->faulted) {
        return LFJ8_H03_PHASE_FAULT;
    }
    const int pending = clock->latest.sequence != clock->consumed;
    const uint32_t age = now - clock->latest.released_at;
    if (age > (pending ? clock->max_age : clock->max_period)) {
        clock->faulted = 1u;
        return LFJ8_H03_PHASE_FAULT;
    }
    return pending ? LFJ8_H03_PHASE_EVENT : LFJ8_H03_PHASE_WAIT;
}

Lfj8H03PhaseResult lfj8_h03_phase_clock_take(volatile Lfj8H03PhaseClock *clock,
                                            uint32_t now, Lfj8H03PhaseEvent *out)
{
    if (!out) {
        return LFJ8_H03_PHASE_FAULT;
    }
    *out = (Lfj8H03PhaseEvent){0};
    const Lfj8H03PhaseResult result = lfj8_h03_phase_clock_check(clock, now);
    if (result != LFJ8_H03_PHASE_EVENT) {
        return result;
    }
    *out = clock->latest;
    clock->consumed = out->sequence;
    return LFJ8_H03_PHASE_EVENT;
}
