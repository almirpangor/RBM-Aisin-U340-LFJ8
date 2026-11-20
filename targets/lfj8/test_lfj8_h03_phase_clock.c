#include "lfj8_h03_phase_clock.h"

#include <assert.h>

int main(void)
{
    volatile Lfj8H03PhaseClock clock = {0};
    Lfj8H03PhaseEvent event = {12, 34};
    assert(lfj8_h03_phase_clock_take(&clock, 100, &event) == LFJ8_H03_PHASE_FAULT);
    assert(event.sequence == 0 && event.released_at == 0);
    assert(!lfj8_h03_phase_clock_init(&clock, 100, 0, 10, 2));
    assert(!lfj8_h03_phase_clock_init(&clock, 100, 4, 3, 2));
    assert(!lfj8_h03_phase_clock_init(&clock, 100, 4, 8, 2));
    assert(!lfj8_h03_phase_clock_init(&clock, 100, 4, 5, 4));

    assert(lfj8_h03_phase_clock_init(&clock, 100, 8, 12, 3));
    assert(lfj8_h03_phase_clock_take(&clock, 112, &event) == LFJ8_H03_PHASE_WAIT);
    lfj8_h03_phase_clock_release(&clock, 112);
    assert(lfj8_h03_phase_clock_take(&clock, 115, &event) == LFJ8_H03_PHASE_EVENT);
    assert(event.sequence == 1 && event.released_at == 112);
    assert(lfj8_h03_phase_clock_take(&clock, 115, &event) == LFJ8_H03_PHASE_WAIT);
    lfj8_h03_phase_clock_release(&clock, 120);
    assert(lfj8_h03_phase_clock_take(&clock, 120, &event) == LFJ8_H03_PHASE_EVENT);
    assert(event.sequence == 2 && event.released_at == 120);
    assert(lfj8_h03_phase_clock_take(&clock, 133, &event) == LFJ8_H03_PHASE_FAULT);
    lfj8_h03_phase_clock_release(&clock, 133);
    assert(lfj8_h03_phase_clock_take(&clock, 133, &event) == LFJ8_H03_PHASE_FAULT);

    assert(lfj8_h03_phase_clock_init(&clock, 100, 8, 12, 3));
    lfj8_h03_phase_clock_release(&clock, 101);
    lfj8_h03_phase_clock_release(&clock, 111);
    assert(lfj8_h03_phase_clock_take(&clock, 111, &event) == LFJ8_H03_PHASE_FAULT);

    assert(lfj8_h03_phase_clock_init(&clock, 100, 8, 12, 3));
    lfj8_h03_phase_clock_release(&clock, 109);
    assert(lfj8_h03_phase_clock_take(&clock, 113, &event) == LFJ8_H03_PHASE_FAULT);

    assert(lfj8_h03_phase_clock_init(&clock, 100, 8, 12, 3));
    lfj8_h03_phase_clock_release(&clock, 110);
    assert(lfj8_h03_phase_clock_take(&clock, 110, &event) == LFJ8_H03_PHASE_EVENT);
    lfj8_h03_phase_clock_release(&clock, 117);
    assert(lfj8_h03_phase_clock_take(&clock, 117, &event) == LFJ8_H03_PHASE_FAULT);

    assert(lfj8_h03_phase_clock_init(&clock, 100, 8, 12, 3));
    lfj8_h03_phase_clock_release(&clock, 113);
    assert(lfj8_h03_phase_clock_take(&clock, 113, &event) == LFJ8_H03_PHASE_FAULT);

    assert(lfj8_h03_phase_clock_init(&clock, UINT32_MAX - 9, 8, 12, 3));
    clock.latest.sequence = UINT32_MAX;
    clock.consumed = UINT32_MAX;
    lfj8_h03_phase_clock_release(&clock, UINT32_MAX - 5);
    assert(lfj8_h03_phase_clock_take(&clock, UINT32_MAX - 5, &event) == LFJ8_H03_PHASE_EVENT);
    assert(event.sequence == 0 && event.released_at == UINT32_MAX - 5);
    lfj8_h03_phase_clock_release(&clock, 4);
    assert(lfj8_h03_phase_clock_take(&clock, 5, &event) == LFJ8_H03_PHASE_EVENT);
    assert(event.sequence == 1 && event.released_at == 4);
    assert(lfj8_h03_phase_clock_take(&clock, 3, &event) == LFJ8_H03_PHASE_FAULT);
    return 0;
}
