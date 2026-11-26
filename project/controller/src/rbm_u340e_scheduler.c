#include "rbm_u340e_scheduler.h"

enum {
    PRODUCER_IDLE,
    PRODUCER_ACTIVATED,
    PRODUCER_PUBLISHED,
};

enum {
    FAST_IDLE,
    FAST_CLAIMED,
    FAST_BODY,
    FAST_RETURNED,
};

enum {
    SECONDARY_IDLE,
    SECONDARY_QUEUED,
    SECONDARY_BODY,
    SECONDARY_MAIN,
};

enum { FAST_PHASE_GP = 1060 };

void rbm_u340e_schedule_finish_init(RbmU340eScheduler *schedule)
{
    schedule->initialized = 1u;
}

RbmU340eIrq rbm_u340e_schedule_timer_irq(RbmU340eScheduler *schedule)
{
    if (schedule->producer_overrun) {
        return RBM_U340E_IRQ_PRODUCER_OVERRUN;
    }
    ++schedule->irq_count;
    if (!schedule->initialized) {
        return RBM_U340E_IRQ_BEFORE_INIT;
    }
    if (schedule->producer_stage != PRODUCER_IDLE) {
        schedule->producer_overrun = 1u;
        return RBM_U340E_IRQ_PRODUCER_OVERRUN;
    }
    schedule->producer_stage = PRODUCER_ACTIVATED;
    return RBM_U340E_IRQ_PRODUCER;
}

RbmU340eRelease rbm_u340e_schedule_producer_publish(RbmU340eScheduler *schedule)
{
    if (schedule->producer_overrun || schedule->producer_stage != PRODUCER_ACTIVATED) {
        return RBM_U340E_RELEASE_INVALID;
    }
    const unsigned phase = schedule->producer_count & 7u;
    RbmU340eRelease result = RBM_U340E_RELEASE_NONE;
    if ((phase & 3u) == 2u) {
        result = schedule->fast_pending ? RBM_U340E_RELEASE_FAST_COALESCED : RBM_U340E_RELEASE_FAST;
        schedule->fast_pending = 1u;
    } else if (phase == 4u) {
        if (schedule->secondary_stage == SECONDARY_IDLE) {
            result = RBM_U340E_RELEASE_SECONDARY;
            schedule->secondary_stage = SECONDARY_QUEUED;
        } else {
            result = RBM_U340E_RELEASE_SECONDARY_DROPPED;
        }
    }
    ++schedule->producer_count;
    schedule->producer_stage = PRODUCER_PUBLISHED;
    return result;
}

int rbm_u340e_schedule_producer_done(RbmU340eScheduler *schedule)
{
    if (schedule->producer_overrun || schedule->producer_stage != PRODUCER_PUBLISHED) {
        return 0;
    }
    schedule->producer_stage = PRODUCER_IDLE;
    return 1;
}

int rbm_u340e_schedule_fast_claim(RbmU340eScheduler *schedule)
{
    if (schedule->producer_overrun || schedule->fast_stage != FAST_IDLE || !schedule->fast_pending) {
        return 0;
    }
    schedule->fast_pending = 0u;
    schedule->fast_stage = FAST_CLAIMED;
    return 1;
}

int rbm_u340e_schedule_fast_begin(RbmU340eScheduler *schedule, FactoryHydraulics *gp)
{
    uint32_t phase;
    if (schedule->producer_overrun || schedule->fast_stage != FAST_CLAIMED ||
        !factory_hydraulics_get(gp, FAST_PHASE_GP, 1u, &phase)) {
        return 0;
    }
    schedule->fast_phase = (uint8_t)phase;
    factory_hydraulics_counters_begin(gp);
    schedule->fast_stage = FAST_BODY;
    return 1;
}

int rbm_u340e_schedule_fast_end(RbmU340eScheduler *schedule, FactoryHydraulics *gp)
{
    if (schedule->producer_overrun || schedule->fast_stage != FAST_BODY ||
        !factory_hydraulics_set(gp, FAST_PHASE_GP, 1u, (uint8_t)(schedule->fast_phase + 1u))) {
        return 0;
    }
    schedule->fast_stage = FAST_RETURNED;
    return 1;
}

int rbm_u340e_schedule_fast_done(RbmU340eScheduler *schedule)
{
    if (schedule->producer_overrun || schedule->fast_stage != FAST_RETURNED) {
        return 0;
    }
    ++schedule->fast_count;
    schedule->fast_stage = FAST_IDLE;
    return 1;
}

int rbm_u340e_schedule_secondary_claim(RbmU340eScheduler *schedule)
{
    if (schedule->producer_overrun || schedule->secondary_stage != SECONDARY_QUEUED) {
        return 0;
    }
    schedule->secondary_stage = SECONDARY_BODY;
    return 1;
}

static void finish_secondary(RbmU340eScheduler *schedule)
{
    ++schedule->secondary_count;
    schedule->secondary_stage = SECONDARY_IDLE;
}

RbmU340eSecondary rbm_u340e_schedule_secondary_done(RbmU340eScheduler *schedule)
{
    if (schedule->producer_overrun || schedule->secondary_stage != SECONDARY_BODY) {
        return RBM_U340E_SECONDARY_INVALID;
    }
    if ((schedule->secondary_count & 1u) == 0u) {
        schedule->secondary_stage = SECONDARY_MAIN;
        return RBM_U340E_SECONDARY_RUN_MAIN;
    }
    finish_secondary(schedule);
    return RBM_U340E_SECONDARY_DONE;
}

int rbm_u340e_schedule_main_done(RbmU340eScheduler *schedule)
{
    if (schedule->producer_overrun || schedule->secondary_stage != SECONDARY_MAIN) {
        return 0;
    }
    finish_secondary(schedule);
    return 1;
}
