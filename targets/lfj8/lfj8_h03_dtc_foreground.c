#include "lfj8_h03_dtc_foreground.h"

#include <stddef.h>

Lfj8H03Can13Result lfj8_h03_dtc_foreground_poll(
    Lfj8H03Can13 *broker, Lfj8H03DtcRxQueue *queue, const Lfj8RegisterIo *io,
    Lfj8H03Can13Input *input, const uint16_t *can_now)
{
    if (!broker || !broker->initialized || !io || !input || !input->dtc) {
        return (Lfj8H03Can13Result){0};
    }
    const bool owns_slot = input->owns_slot13 == 1u;
    const bool session_ended = owns_slot && lfj8_h03_dtc_can_service_session(
        &broker->diagnostic, input->generation, input->diagnostic_tick);
    if (session_ended) {
        lfj8_h03_dtc_rx_queue_end_session(queue, io, input->now_us, can_now);
    }
    Lfj8H03DtcRxDelivery delivery;
    const bool have_delivery = owns_slot && !session_ended && can_now && lfj8_h03_dtc_rx_queue_peek(
        queue, io, input->generation, input->now_us, *can_now, &delivery);
    const Lfj8H03DtcReceive *saved = input->received;
    input->received = have_delivery ? &delivery.received : NULL;
    const Lfj8H03Can13Result result = lfj8_h03_can13_poll(broker, io, input);
    input->received = saved;
    if (!result.available) {
        /* The broker has revoked the session. Discard the whole backlog;
         * the owner drains the hardware and changes the RX generation
         * before granting access again. */
        lfj8_h03_dtc_rx_queue_end_session(queue, io, input->now_us, NULL);
    } else if (have_delivery && result.diagnostic_consumed) {
        lfj8_h03_dtc_rx_queue_consume(queue, io, &delivery);
    }
    return result;
}
