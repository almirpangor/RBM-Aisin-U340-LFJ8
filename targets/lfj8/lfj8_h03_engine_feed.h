#ifndef RBM_LFJ8_H03_ENGINE_FEED_H
#define RBM_LFJ8_H03_ENGINE_FEED_H

#include "chery_dtc.h"
#include "lfj8_h03_engine_rx.h"
#include "ta2005_engine_qualifier.h"

/* Run once per eligible task 2 release. The same foreground owner serializes
 * RX polling, diagnostic requests and this step. A successful 14 FF 00 event
 * resets the engine debouncers before any timing/context checks, including
 * when context or io is unavailable. Initialize the qualifier and the DTC
 * store together on cold startup. A receiver bound to the CAN setup
 * generation invalidates old data during its normal poll. Without the
 * binding, reinitialize RX on CAN-only reset. Retain the qualifier and
 * DTC store in either case.
 *
 * The shared DTC current byte corresponding to E02B and context->e02b
 * both contribute bus inhibit conditions. Local ownership/clock loss
 * invalidates retained feedback without recording a bus DTC. An ordinary
 * frame timeout on a continuously owned channel still runs its debounce.
 * inhibit_history carries the donor FD00.5 condition.
 *
 * Returns the qualifier event mask, or 0 with feed->coherent cleared when
 * no qualified task snapshot can be published. The feed grants no physical
 * output permit. All objects are disjoint. The owner may also poll RX
 * between task 2 releases to meet the receiver timebase requirement. */
unsigned lfj8_h03_engine_feed_task2(Lfj8H03EngineRx *rx, Ta2005EngineQualifier *qualifier,
    CheryDtcState *dtc, const Lfj8RegisterIo *io, uint32_t now_us, uint8_t slots_owned,
    const Ta2005EngineQualificationContext *context, bool inhibit_history,
    RbmU340eQualifiedEngineFeed *feed);

enum {
    LFJ8_H03_MODEL_NOT_EVALUATED = 0,
    LFJ8_H03_MODEL_INHIBITED,
    LFJ8_H03_MODEL_EVALUATE,
};

typedef struct {
    Ta2005CherySnapshot snapshot;
    uint8_t state;
} Lfj8H03EngineModelSample;

/* Same release and receiver snapshot as the engine feed, with an optional
 * disjoint model output. Only EVALUATE admits a model debounce step. In
 * EVALUATE, FF denotes an unavailable field and is independent of RPM.
 * INHIBITED denotes the E02B bus-fault path (including local RX or clock
 * loss). NOT_EVALUATED denotes a refused release. Both clear the snapshot
 * and must skip the normal model debounce. */
unsigned lfj8_h03_engine_feed_task2_with_model(Lfj8H03EngineRx *rx,
    Ta2005EngineQualifier *qualifier, CheryDtcState *dtc, const Lfj8RegisterIo *io,
    uint32_t now_us, uint8_t slots_owned, const Ta2005EngineQualificationContext *context,
    bool inhibit_history, RbmU340eQualifiedEngineFeed *feed, Lfj8H03EngineModelSample *model);

#endif
