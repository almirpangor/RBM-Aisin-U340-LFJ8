#ifndef RBM_LFJ8_H03_PHASE_CLOCK_H
#define RBM_LFJ8_H03_PHASE_CLOCK_H

#include <stdint.h>

typedef struct {
    uint32_t sequence;
    uint32_t released_at;
} Lfj8H03PhaseEvent;

typedef struct {
    Lfj8H03PhaseEvent latest;
    uint32_t consumed;
    uint32_t min_period;
    uint32_t max_period;
    uint32_t max_age;
    uint8_t have_release;
    uint8_t faulted;
} Lfj8H03PhaseClock;

typedef enum {
    LFJ8_H03_PHASE_FAULT,
    LFJ8_H03_PHASE_WAIT,
    LFJ8_H03_PHASE_EVENT,
} Lfj8H03PhaseResult;

/* All calls are serialized with the phase publisher. The foreground masks
 * that interrupt around its clock read and the whole take operation. Times
 * share one qualified clock, with no reset, halt, or unobserved half wrap.
 * Choose inclusive bounds from measured release intervals. In particular,
 * one interval must never cover two consecutive qualified periods. */
int lfj8_h03_phase_clock_init(volatile Lfj8H03PhaseClock *clock, uint32_t now,
                              uint32_t min_period, uint32_t max_period, uint32_t max_age);

/* Once per native H03 publication at 040474–040478. For example, do this
 * immediately after the stock 040468 routine from its exclusive 040424 call.
 * This event belongs to the H03 output phases. Toyota Task 2 has its own cadence. */
void lfj8_h03_phase_clock_release(volatile Lfj8H03PhaseClock *clock, uint32_t now);

/* Platform callback for h03_phase_release_hook.S. TML0CT is sampled after
 * the original publication. Call phase_clock_release only for initialized,
 * owned RAM and a running timebase. Keep this IRQ callback bounded and leave
 * control registers (apart from the arithmetic condition bit) untouched. */
void rbm_h03_phase_release_callback(uint32_t released_at);

/* Check the same deadline as take, leaving a fresh event pending.
 * The caller must serialize this check with the publisher and consumer. */
Lfj8H03PhaseResult lfj8_h03_phase_clock_check(volatile Lfj8H03PhaseClock *clock, uint32_t now);

/* No backlog is delivered. A missing, late or overwritten event latches a
 * fault until reinitialization with the drivetrain command disabled. Check
 * on each foreground turn, including those with no OEM phase bit pending.
 * On fault, the caller must revoke actuator authority. */
Lfj8H03PhaseResult lfj8_h03_phase_clock_take(volatile Lfj8H03PhaseClock *clock,
                                            uint32_t now, Lfj8H03PhaseEvent *out);

#endif
