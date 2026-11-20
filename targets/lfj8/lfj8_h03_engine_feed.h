#ifndef RBM_LFJ8_H03_ENGINE_FEED_H
#define RBM_LFJ8_H03_ENGINE_FEED_H

#include "chery_dtc.h"
#include "lfj8_h03_engine_rx.h"
#include "ta2005_engine_qualifier.h"

/* Run once per eligible task 2 release. The same foreground owner serializes
 * RX polling, diagnostic requests and this step. A successful 14 FF 00 event
 * resets the engine debouncers before any timing/context checks, including
 * when context or io is unavailable. Initialize the qualifier and the DTC
 * store together on cold startup. On a CAN-only reset, reinitialize the RX
 * state and retain the qualifier and DTC store.
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

#endif
