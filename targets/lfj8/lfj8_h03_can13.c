#include "lfj8_h03_can13.h"

bool lfj8_h03_can13_init(Lfj8H03Can13 *broker, const Lfj8H03Can13Config *config,
                         uint32_t now_us)
{
    if (!broker) {
        return false;
    }
    *broker = (Lfj8H03Can13){0};
    if (!config || !lfj8_h03_torque_can_init(&broker->torque, config->torque_receive_age_bits,
                                 config->max_poll_gap_us, config->bit_time_us) ||
        !lfj8_h03_dtc_can_init(&broker->diagnostic, config->diagnostic_receive_age_bits)) {
        return false;
    }
    lfj8_chery_tx_init(&broker->status, now_us, config->period_1ae_us, config->period_300_us);
    broker->initialized = true;
    return true;
}

static bool diagnostic_current(const Lfj8H03DtcReceive *received, uint32_t generation,
                               uint16_t timestamp, uint16_t max_age)
{
    return received && received->generation == generation &&
        (uint16_t)(timestamp - received->can_timestamp) < max_age &&
        received->frame.id == CHERY_DTC_CAN_REQUEST_ID && !received->frame.extended &&
        !received->frame.remote && !received->frame.fd && received->frame.length != 0u &&
        received->frame.length <= CHERY_DTC_CAN_FRAME_BYTES;
}

static bool torque_holds(const Lfj8H03Torque *request)
{
    return request->pending || request->phase == LFJ8_TORQUE_WAITING ||
        request->phase == LFJ8_TORQUE_ACTIVE || request->phase == LFJ8_TORQUE_RELEASING;
}

Lfj8H03Can13Result lfj8_h03_can13_poll(Lfj8H03Can13 *broker, const Lfj8RegisterIo *io,
                                      const Lfj8H03Can13Input *input)
{
    if (!broker || !broker->initialized || !io || !input || !input->dtc) {
        return (Lfj8H03Can13Result){0};
    }
    uint32_t now = input->now_us;
    if (broker->generation != input->generation) {
        broker->generation = input->generation;
        broker->status_in_flight = 0u;
        broker->status_during_reduction = false;
        broker->lease_seen = false;
        broker->lease_lost = false;
        lfj8_chery_tx_init(&broker->status, now, broker->status.schedule.period_1ae_us,
                          broker->status.schedule.period_300_us);
    }

    uint16_t timestamp;
    if (broker->lease_lost || input->owns_slot13 != 1u ||
        !lfj8_h03_can0_slot13_timestamp(io, &timestamp)) {
        goto slot_unavailable;
    }
    broker->lease_seen = true;
    const bool have_diagnostic = diagnostic_current(input->received, input->generation,
                                                     timestamp, broker->diagnostic.max_receive_age_bits);
    Lfj8H03Can13Result result = {
        .available = true,
        .diagnostic_consumed = input->received && !have_diagnostic,
    };
    broker->status.pending |= lfj8_schedule_poll(&broker->status.schedule, now);

    /* Without an RX input this only ages DTC state and finishes its own TX.
     * A reply awaiting Flow Control has no claim on the hardware slot. */
    const Lfj8H03DtcSlotUse diagnostic = lfj8_h03_dtc_can_poll(
        &broker->diagnostic, input->dtc, io, 1u, input->generation, input->diagnostic_tick, NULL);
    if (diagnostic == LFJ8_H03_DTC_NO_OWNERSHIP) {
        goto slot_unavailable;
    }
    if (diagnostic == LFJ8_H03_DTC_SLOT_RESERVED) {
        return result;
    }

    Lfj8H03Torque *request = &broker->torque.request;
    if (broker->status_in_flight) {
        const bool loan_expired = now - broker->status_started_us >= broker->torque.max_poll_gap_us;
        if (broker->status_during_reduction) {
            /* Once the loan exceeds the receive gap, revoke the old torque
             * confirmation even if the controller still owns the aborted TX. */
            lfj8_h03_torque_poll(request, loan_expired ? NULL : input->torque,
                                input->torque_calibration, now, NULL, NULL);
        }
        const bool cancel = loan_expired ||
            (broker->status_during_reduction && !lfj8_h03_torque_applied(request, now));
        const uint16_t id = broker->status_in_flight == LFJ8_DUE_1AE ? LFJ8_CAN_1AE : LFJ8_CAN_300;
        const Lfj8CanTxStatus status = lfj8_h03_can0_telemetry_status(io, id, cancel);
        if (status == LFJ8_CAN_TX_UNAVAILABLE) {
            goto slot_unavailable;
        }
        if (status == LFJ8_CAN_TX_PENDING) {
            return result;
        }
        /* An idle slot without TRFIN did not send the frame. Keep the last
         * acknowledged 1AE counter for the next submission. */
        if (status == LFJ8_CAN_TX_IDLE && id == LFJ8_CAN_1AE) {
            broker->status.counter_f8e4 = broker->counter_before_status;
        }
        broker->status_in_flight = 0u;
    }

    const uint32_t previous_progress = request->progress_at;
    if (lfj8_h03_torque_can_poll(&broker->torque, io, 1u, false, input->generation, now,
                                 input->torque, input->torque_calibration) ==
        LFJ8_H03_TORQUE_CAN_UNAVAILABLE) {
        goto slot_unavailable;
    }
    const bool torque_priority = torque_holds(request);
    const bool status_window = !request->pending && request->progress_at != previous_progress &&
        lfj8_h03_torque_applied(request, now + broker->torque.max_poll_gap_us);
    const bool use_diagnostic = have_diagnostic && !torque_priority;
    const bool use_status = broker->status.pending && input->vss && input->vehicle && input->status &&
        (!torque_priority || status_window);
    if (!use_diagnostic && !use_status) {
        return result;
    }
    /* Service torque once above, so a START or CANCEL already due cannot
     * be overtaken. Check for an in-progress receive before changing mode. */
    const Lfj8CanResult yielded = lfj8_h03_can0_torque_yield(io, 1u);
    if (yielded == LFJ8_CAN_SLOT_BUSY) {
        return result;
    }
    if (yielded != LFJ8_CAN_READY) {
        goto slot_unavailable;
    }
    if (use_diagnostic) {
        const Lfj8H03DtcSlotUse admitted = lfj8_h03_dtc_can_poll(
            &broker->diagnostic, input->dtc, io, 1u, input->generation,
            input->diagnostic_tick, input->received);
        if (admitted == LFJ8_H03_DTC_NO_OWNERSHIP) {
            goto slot_unavailable;
        }
        result.diagnostic_consumed = true;
        if (admitted == LFJ8_H03_DTC_SLOT_RESERVED) {
            return result;
        }
    }
    if (use_status) {
        broker->counter_before_status = broker->status.counter_f8e4;
        const Lfj8CanResult status = lfj8_chery_tx_poll_status(
            &broker->status, io, now, 1u, input->vss, input->vehicle, input->status,
            &result.status_submitted);
        if (status == LFJ8_CAN_READY || status == LFJ8_CAN_SLOT_BUSY) {
            return result;
        }
        if (status != LFJ8_CAN_SUBMITTED) {
            goto slot_unavailable;
        }
        broker->status_started_us = now;
        broker->status_in_flight = result.status_submitted;
        broker->status_during_reduction = status_window;
    }
    return result;

slot_unavailable:
    broker->lease_lost = broker->lease_lost || broker->lease_seen;
    lfj8_h03_torque_can_poll(&broker->torque, io, 0u, false, input->generation, input->now_us,
                            NULL, input->torque_calibration);
    lfj8_h03_dtc_can_poll(&broker->diagnostic, input->dtc, io, 0u,
                         input->generation, input->diagnostic_tick, NULL);
    lfj8_chery_tx_poll(&broker->status, io, input->now_us, 0u, NULL, NULL, NULL);
    return (Lfj8H03Can13Result){.diagnostic_consumed = input->received != NULL};
}
