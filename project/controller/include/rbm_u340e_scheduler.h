#ifndef RBM_U340E_SCHEDULER_H
#define RBM_U340E_SCHEDULER_H

#include "factory_hydraulics.h"

typedef enum {
    RBM_U340E_IRQ_BEFORE_INIT,
    RBM_U340E_IRQ_PRODUCER,
    RBM_U340E_IRQ_PRODUCER_OVERRUN,
} RbmU340eIrq;

typedef enum {
    RBM_U340E_RELEASE_INVALID,
    RBM_U340E_RELEASE_NONE,
    RBM_U340E_RELEASE_FAST,
    RBM_U340E_RELEASE_FAST_COALESCED,
    RBM_U340E_RELEASE_SECONDARY,
    RBM_U340E_RELEASE_SECONDARY_DROPPED,
} RbmU340eRelease;

typedef enum {
    RBM_U340E_SECONDARY_INVALID,
    RBM_U340E_SECONDARY_DONE,
    RBM_U340E_SECONDARY_RUN_MAIN,
} RbmU340eSecondary;

/* Zero-initialize on reset. All transitions belong to one serialized owner.
 * These counters follow the delivered donor events and have no time units. */
typedef struct {
    uint16_t irq_count;
    uint16_t producer_count;
    uint16_t fast_count;
    uint16_t secondary_count;
    uint8_t initialized;
    uint8_t producer_overrun;
    uint8_t producer_stage;
    uint8_t fast_pending;
    uint8_t fast_stage;
    uint8_t fast_phase;
    uint8_t secondary_stage;
} RbmU340eScheduler;

/* Publish after the external owner finishes the donor startup sequence. */
void rbm_u340e_schedule_finish_init(RbmU340eScheduler *schedule);
RbmU340eIrq rbm_u340e_schedule_timer_irq(RbmU340eScheduler *schedule);

/* Task 2 remains busy from activation through publication until termination. */
RbmU340eRelease rbm_u340e_schedule_producer_publish(RbmU340eScheduler *schedule);
int rbm_u340e_schedule_producer_done(RbmU340eScheduler *schedule);

/* ClearEvent, 05425C entry, 054346/054348 epilogue and task 1 completion are
 * separate boundaries. Call begin/end with the same caller-owned GP, around
 * the actual FAST body. The owner provides every intervening donor stage.
 * Bank increments match the serialized donor computation. A partial FAST
 * must not be replayed or completed by calling these functions again. */
int rbm_u340e_schedule_fast_claim(RbmU340eScheduler *schedule);
int rbm_u340e_schedule_fast_begin(RbmU340eScheduler *schedule, FactoryHydraulics *gp);
int rbm_u340e_schedule_fast_end(RbmU340eScheduler *schedule, FactoryHydraulics *gp);
int rbm_u340e_schedule_fast_done(RbmU340eScheduler *schedule);

/* Claim 05421C first. On RUN_MAIN, task 22 remains occupied until the owner
 * finishes 0540E4 and calls main_done. Busy activations are dropped. */
int rbm_u340e_schedule_secondary_claim(RbmU340eScheduler *schedule);
RbmU340eSecondary rbm_u340e_schedule_secondary_done(RbmU340eScheduler *schedule);
int rbm_u340e_schedule_main_done(RbmU340eScheduler *schedule);

#endif
