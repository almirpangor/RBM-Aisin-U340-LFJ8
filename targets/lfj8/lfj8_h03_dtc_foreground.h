#ifndef RBM_LFJ8_H03_DTC_FOREGROUND_H
#define RBM_LFJ8_H03_DTC_FOREGROUND_H

#include "lfj8_h03_can13.h"
#include "lfj8_h03_dtc_rx_queue.h"

/* Poll once per CAN foreground cycle, including while TX13 is busy.
 * Supply a CAN timestamp paired with input->now_us, or NULL when there is
 * no valid pair. The input must be exclusive to foreground. The adapter
 * borrows its received field for the broker call and restores it on return.
 *
 * Serialize this call with CAN lease changes and queue reset. The CAN
 * owner changes generation and resets the queue after hardware reset or
 * verified drain, before enabling RX in the new generation. The RX IRQ
 * may publish between queue operations.
 *
 * diagnostic_consumed describes the broker's decision for its local copy.
 * An IRQ that expired that entry cannot cause the next entry to be removed.
 */
Lfj8H03Can13Result lfj8_h03_dtc_foreground_poll(
    Lfj8H03Can13 *broker, Lfj8H03DtcRxQueue *queue, const Lfj8RegisterIo *io,
    Lfj8H03Can13Input *input, const uint16_t *can_now);

#endif
