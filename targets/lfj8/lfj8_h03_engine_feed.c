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

unsigned lfj8_h03_engine_feed_task2_with_model(Lfj8H03EngineRx *rx,
    Ta2005EngineQualifier *qualifier, CheryDtcState *dtc, const Lfj8RegisterIo *io,
    uint32_t now_us, uint8_t slots_owned, const Ta2005EngineQualificationContext *context,
    bool inhibit_history, RbmU340eQualifiedEngineFeed *feed, Lfj8H03EngineModelSample *model)
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
    if (!rx || !qualifier || !dtc || !feed || !io || !context || context->coherent != 1u) {
        return 0u;
    }

    Ta2005CherySnapshot raw;
    lfj8_h03_engine_rx_poll(rx, io, now_us, slots_owned, &raw);
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
    const unsigned events = ta2005_engine_qualifier_task2(qualifier, &raw, &signal, feed);
    manage_dtc(dtc, RPM_DTC, (qualifier->flags & TA2005_ENGINE_RPM_LATCH) != 0u,
               (events & TA2005_ENGINE_NEW_RPM_DTC) != 0u, inhibit_history);
    manage_dtc(dtc, COOLANT_DTC, (qualifier->flags & TA2005_ENGINE_COOLANT_LATCH) != 0u,
               (events & TA2005_ENGINE_NEW_COOLANT_DTC) != 0u, inhibit_history);
    if (model) {
        if (signal.e02b & E02B_BUS_FAULTS) {
            model->state = LFJ8_H03_MODEL_INHIBITED;
        } else {
            model->snapshot = raw;
            model->state = LFJ8_H03_MODEL_EVALUATE;
        }
    }
    return events;
}

unsigned lfj8_h03_engine_feed_task2(Lfj8H03EngineRx *rx, Ta2005EngineQualifier *qualifier,
    CheryDtcState *dtc, const Lfj8RegisterIo *io, uint32_t now_us, uint8_t slots_owned,
    const Ta2005EngineQualificationContext *context, bool inhibit_history,
    RbmU340eQualifiedEngineFeed *feed)
{
    return lfj8_h03_engine_feed_task2_with_model(rx, qualifier, dtc, io, now_us, slots_owned,
        context, inhibit_history, feed, NULL);
}
