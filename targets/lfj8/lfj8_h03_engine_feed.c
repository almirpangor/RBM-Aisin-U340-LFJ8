#include "lfj8_h03_engine_feed.h"

enum {
    RPM_DTC = 0x15,
    COOLANT_DTC = 0x14,
    CURRENT_E02A = 2,
    CURRENT_E02B = 3,
    E02B_INHIBIT = 0x80,
    E02B_BUS_FAULTS = E02B_INHIBIT | 0x04,
};

static void manage_dtc(CheryDtcState *dtc, uint8_t index, bool latched, bool new_event,
                       bool inhibit_history)
{
    if (new_event) {
        chery_dtc_raise_c0(dtc, index, inhibit_history);
    } else if (!latched) {
        chery_dtc_set_current(dtc, index, false);
    }
}

static void prepare_task2(Ta2005EngineQualifier *qualifier, CheryDtcState *dtc,
    RbmU340eQualifiedEngineFeed *feed, Lfj8H03EngineModelSample *model)
{
    if (qualifier && dtc && dtc->clear_pending) {
        /* Native clear 0652FC resets E04C, E020, E02A and E026. FA62
         * and FD16.2 belong to separate storage and stay unchanged. */
        qualifier->rpm_count = 0u;
        qualifier->coolant_count = 0u;
        qualifier->flags &= (uint8_t)~(TA2005_ENGINE_RPM_LATCH |
            TA2005_ENGINE_COOLANT_LATCH | TA2005_ENGINE_RPM_FAILED);
        dtc->clear_pending = false;
    }
    if (feed) {
        feed->coherent = 0u;
    }
    if (model) {
        ta2005_chery_snapshot_clear(&model->snapshot);
        model->state = LFJ8_H03_MODEL_NOT_EVALUATED;
    }
}

static unsigned qualify_task2(Lfj8H03EngineRx *rx, Ta2005EngineQualifier *qualifier,
    CheryDtcState *dtc, const Ta2005CherySnapshot *raw,
    const Ta2005EngineQualificationContext *context, bool inhibit_history,
    RbmU340eQualifiedEngineFeed *feed, Lfj8H03EngineModelSample *model)
{
    Ta2005EngineQualificationContext signal = *context;
    signal.e02b |= dtc->current[CURRENT_E02B];
    if (rx->discontinuity || !rx->clock_running) {
        signal.e02b |= E02B_INHIBIT;
        rx->discontinuity = 0u;
    }

    const uint8_t status = dtc->current[CURRENT_E02A];
    const uint8_t latches = (uint8_t)(
        ((status & (1u << (RPM_DTC % 8))) ? TA2005_ENGINE_RPM_LATCH : 0u) |
        ((status & (1u << (COOLANT_DTC % 8))) ? TA2005_ENGINE_COOLANT_LATCH : 0u));
    qualifier->flags = (uint8_t)((qualifier->flags &
        ~(TA2005_ENGINE_RPM_LATCH | TA2005_ENGINE_COOLANT_LATCH)) | latches);
    const unsigned events = ta2005_engine_qualifier_task2(qualifier, raw, &signal, feed);
    manage_dtc(dtc, RPM_DTC, (qualifier->flags & TA2005_ENGINE_RPM_LATCH) != 0u,
               (events & TA2005_ENGINE_NEW_RPM_DTC) != 0u, inhibit_history);
    manage_dtc(dtc, COOLANT_DTC, (qualifier->flags & TA2005_ENGINE_COOLANT_LATCH) != 0u,
               (events & TA2005_ENGINE_NEW_COOLANT_DTC) != 0u, inhibit_history);
    if (model) {
        if (signal.e02b & E02B_BUS_FAULTS) {
            model->state = LFJ8_H03_MODEL_INHIBITED;
        } else {
            model->snapshot = *raw;
            model->state = LFJ8_H03_MODEL_EVALUATE;
        }
    }
    return events;
}

unsigned lfj8_h03_engine_feed_task2_with_model(Lfj8H03EngineRx *rx,
    Ta2005EngineQualifier *qualifier, CheryDtcState *dtc, const Lfj8RegisterIo *io,
    uint32_t now_us, uint8_t slots_owned, const Ta2005EngineQualificationContext *context,
    bool inhibit_history, RbmU340eQualifiedEngineFeed *feed, Lfj8H03EngineModelSample *model)
{
    prepare_task2(qualifier, dtc, feed, model);
    if (!rx || !qualifier || !dtc || !feed || !io || !context || context->coherent != 1u) {
        return 0u;
    }
    Ta2005CherySnapshot raw;
    lfj8_h03_engine_rx_poll(rx, io, now_us, slots_owned, &raw);
    return qualify_task2(rx, qualifier, dtc, &raw, context, inhibit_history, feed, model);
}

unsigned lfj8_h03_engine_feed_task2(Lfj8H03EngineRx *rx, Ta2005EngineQualifier *qualifier,
    CheryDtcState *dtc, const Lfj8RegisterIo *io, uint32_t now_us, uint8_t slots_owned,
    const Ta2005EngineQualificationContext *context, bool inhibit_history,
    RbmU340eQualifiedEngineFeed *feed)
{
    return lfj8_h03_engine_feed_task2_with_model(rx, qualifier, dtc, io, now_us, slots_owned,
        context, inhibit_history, feed, NULL);
}

int lfj8_h03_engine_feed_target_init(const Lfj8H03EngineFeedTarget *target,
                                     uint16_t max_age_ticks, uint16_t max_poll_gap_us)
{
    const Lfj8RegisterIo *const io = target->io;
    if (!lfj8_h03_engine_rx_init(target->rx, max_age_ticks, max_poll_gap_us)) {
        return 0;
    }
    ta2005_engine_qualifier_init(target->qualifier);
    const uint32_t saved = io->enter(io->context);
    lfj8_h03_engine_rx_bind_generation(target->rx, &target->can_owner->setup_generation);
    io->leave(io->context, saved);
    return 1;
}

static void poll_target_locked(const Lfj8H03EngineFeedTarget *target, Ta2005CherySnapshot *raw)
{
    const Lfj8H03CanOwner *const owner = target->can_owner;
    uint32_t now_us = 0u;
    const uint8_t ready = target->rx->generation_source == &owner->setup_generation &&
                          owner->initialized && owner->grant == 1u &&
                          owner->setup_generation == owner->admitted_generation &&
                          target->now_us(&now_us) == 1;
    lfj8_h03_engine_rx_poll(target->rx, target->io, now_us, ready, raw);
}

void lfj8_h03_engine_feed_target_poll(const Lfj8H03EngineFeedTarget *target)
{
    const Lfj8RegisterIo *const io = target->io;
    const uint32_t saved = io->enter(io->context);
    Ta2005CherySnapshot unused;
    poll_target_locked(target, &unused);
    io->leave(io->context, saved);
}

unsigned lfj8_h03_engine_feed_target_task2(const Lfj8H03EngineFeedTarget *target,
    const Ta2005EngineQualificationContext *context, bool inhibit_history,
    RbmU340eQualifiedEngineFeed *feed, Lfj8H03EngineModelSample *model)
{
    prepare_task2(target->qualifier, target->dtc, feed, model);
    const Lfj8RegisterIo *const io = target->io;
    const uint32_t saved = io->enter(io->context);
    Ta2005CherySnapshot raw;
    poll_target_locked(target, &raw);
    unsigned events = 0u;
    if (feed && context && context->coherent == 1u) {
        events = qualify_task2(target->rx, target->qualifier, target->dtc, &raw,
                              context, inhibit_history, feed, model);
    }
    io->leave(io->context, saved);
    return events;
}
