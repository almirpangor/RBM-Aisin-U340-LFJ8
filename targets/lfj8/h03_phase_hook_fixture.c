#include "lfj8_h03_phase_clock.h"

enum { SNAPSHOT_WORDS = 23, RELEASES = 7 };

static volatile Lfj8H03PhaseClock clock;
static uint32_t callbacks;
static uint32_t missing_stock_publish;
uint32_t phase_snapshots[RELEASES][SNAPSHOT_WORDS];

void phase_fixture_release(uint32_t now, uint32_t *snapshot, unsigned carry);
void phase_fixture_consume(void);

static unsigned stock_flag(void)
{
    return *(volatile const uint8_t *)0x804ade;
}

void phase_fixture_publish(uint32_t now)
{
    ++callbacks;
    if (stock_flag() != 1 || *(volatile const uint8_t *)0x804862 != 10) {
        ++missing_stock_publish;
    }
    lfj8_h03_phase_clock_release(&clock, now);
}

static unsigned take(uint32_t now, uint32_t sequence, uint32_t released_at)
{
    Lfj8H03PhaseEvent event;
    const Lfj8H03PhaseResult result = lfj8_h03_phase_clock_take(&clock, now, &event);
    return result == LFJ8_H03_PHASE_EVENT && event.sequence == sequence &&
           event.released_at == released_at;
}

int phase_fixture_main(unsigned wrapped)
{
    callbacks = 0;
    missing_stock_publish = 0;
    if (!lfj8_h03_phase_clock_init(&clock, UINT32_MAX - 12, 8, 12, 2)) {
        return 1;
    }
    phase_fixture_release(UINT32_MAX - 2, phase_snapshots[0], 0);
    if (wrapped && !take(UINT32_MAX - 1, 1, UINT32_MAX - 2)) {
        return 2;
    }
    phase_fixture_consume();
    phase_fixture_release(7, phase_snapshots[1], 1);
    if (wrapped && !take(9, 2, 7)) {
        return 3;
    }
    phase_fixture_consume();

    phase_fixture_release(17, phase_snapshots[2], 0);
    phase_fixture_release(27, phase_snapshots[3], 1);
    Lfj8H03PhaseEvent discarded;
    if (wrapped && (lfj8_h03_phase_clock_take(&clock, 27, &discarded) != LFJ8_H03_PHASE_FAULT ||
        discarded.sequence != 0 || discarded.released_at != 0)) {
        return 4;
    }
    if (stock_flag() != 1) {
        return 5;
    }
    phase_fixture_consume();
    phase_fixture_release(37, phase_snapshots[4], 0);
    if (wrapped && lfj8_h03_phase_clock_take(&clock, 37, &discarded) != LFJ8_H03_PHASE_FAULT) {
        return 6;
    }
    phase_fixture_consume();

    lfj8_h03_phase_clock_init(&clock, 37, 8, 12, 2);
    phase_fixture_release(47, phase_snapshots[5], 1);
    if (wrapped && !take(47, 1, 47)) {
        return 7;
    }
    if (wrapped && lfj8_h03_phase_clock_take(&clock, 60, &discarded) != LFJ8_H03_PHASE_FAULT) {
        return 8;
    }
    phase_fixture_consume();
    phase_fixture_release(67, phase_snapshots[6], 0);
    phase_fixture_consume();
    if (wrapped && (callbacks != RELEASES || missing_stock_publish ||
        lfj8_h03_phase_clock_take(&clock, 67, &discarded) != LFJ8_H03_PHASE_FAULT)) {
        return 9;
    }
    if (!wrapped && callbacks) {
        return 10;
    }
    return 0;
}
