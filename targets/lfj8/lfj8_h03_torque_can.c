#include "lfj8_h03_torque_can.h"

#include <stddef.h>

#define CAN_HALF_RANGE UINT16_C(0x8000)
#define TORQUE_STATUS_MAX_US UINT32_C(100000)

bool lfj8_h03_torque_can_init(Lfj8H03TorqueCan *adapter, uint16_t max_receive_age_bits,
                               uint16_t max_poll_gap_us, uint8_t bit_time_us)
{
    if (!adapter) {
        return false;
    }
    *adapter = (Lfj8H03TorqueCan){0};
    if (!max_receive_age_bits || max_receive_age_bits >= CAN_HALF_RANGE ||
        !max_poll_gap_us || max_poll_gap_us > 30000u || !bit_time_us ||
        (uint32_t)max_receive_age_bits * bit_time_us >= TORQUE_STATUS_MAX_US ||
        (uint32_t)max_poll_gap_us >= (uint32_t)CAN_HALF_RANGE * bit_time_us) {
        return false;
    }
    adapter->max_receive_age_bits = max_receive_age_bits;
    adapter->max_poll_gap_us = max_poll_gap_us;
    adapter->bit_time_us = bit_time_us;
    adapter->need_drain = true;
    return true;
}

static bool update_clock(Lfj8H03TorqueCan *adapter, uint16_t tick, uint32_t now_us)
{
    const uint16_t delta = (uint16_t)(tick - adapter->previous_tick);
    const bool continuous = adapter->clock_seen && delta < CAN_HALF_RANGE &&
        now_us - adapter->polled_at_us < adapter->max_poll_gap_us &&
        now_us - adapter->tick_changed_at_us < adapter->max_poll_gap_us;
    if (delta || !continuous) {
        adapter->tick_changed_at_us = now_us;
    }
    adapter->previous_tick = tick;
    adapter->polled_at_us = now_us;
    adapter->clock_seen = true;
    return continuous;
}

typedef struct {
    const Lfj8RegisterIo *io;
    bool unavailable;
} TorqueSubmission;

static bool submit(void *context, uint16_t id, const uint8_t payload[8])
{
    TorqueSubmission *tx = context;
    if (id != LFJ8_TORQUE_REQUEST_ID) {
        return false;
    }
    const Lfj8CanResult result = lfj8_h03_can0_torque_submit(tx->io, 1u, payload);
    tx->unavailable = result != LFJ8_CAN_SUBMITTED && result != LFJ8_CAN_SLOT_BUSY;
    return result == LFJ8_CAN_SUBMITTED;
}

static void clear_status(Lfj8H03TorqueCan *adapter)
{
    adapter->request.have_status = false;
    adapter->need_drain = true;
}

Lfj8H03TorqueCanSlot lfj8_h03_torque_can_poll(
    Lfj8H03TorqueCan *adapter, const Lfj8RegisterIo *io, uint8_t slot13_owned,
    bool yield_slot13, uint32_t generation, uint32_t now_us,
    const Lfj8TorqueInput *input, const Lfj8TorqueCalibration *cal)
{
    if (!adapter || !io || !adapter->max_poll_gap_us) {
        return LFJ8_H03_TORQUE_CAN_UNAVAILABLE;
    }
    if (adapter->generation != generation) {
        lfj8_h03_torque_init(&adapter->request);
        adapter->generation = generation;
        adapter->clock_seen = false;
        adapter->need_status_after_completion = false;
        adapter->lease_lost = false;
        clear_status(adapter);
    }
    Lfj8H03TorqueCanSlot slot = LFJ8_H03_TORQUE_CAN_RESERVED;
    Lfj8TorqueSubmit tx_submit = NULL;
    TorqueSubmission tx = {.io = io};
    uint16_t tick;
    if (slot13_owned != 1u || adapter->lease_lost || !lfj8_h03_can0_read_timestamp(io, &tick)) {
        goto lost_ownership;
    }
    const bool advancing = adapter->clock_seen && tick != adapter->previous_tick;
    const bool continuous = update_clock(adapter, tick, now_us);
    if (!continuous) {
        clear_status(adapter);
        input = NULL;
    }

    if (adapter->request.pending) {
        const bool cancel = !continuous ||
            now_us - adapter->request.submitted_at >= adapter->max_poll_gap_us ||
            lfj8_h03_torque_should_abort_tx(&adapter->request, input, cal, now_us);
        const Lfj8CanTxStatus status =
            lfj8_h03_can0_torque_status(io, 1u, cancel, &adapter->completed_tick);
        if (status == LFJ8_CAN_TX_UNAVAILABLE) {
            goto lost_ownership;
        }
        if (status == LFJ8_CAN_TX_PENDING) {
            goto poll_request;
        }
        adapter->need_status_after_completion = status == LFJ8_CAN_TX_FINISHED;
        adapter->completion_observed_at_us = now_us;
        lfj8_h03_torque_tx_done(&adapter->request, adapter->need_status_after_completion, now_us);
    }

    if (yield_slot13) {
        const Lfj8CanResult yielded = lfj8_h03_can0_torque_yield(io, 1u);
        slot = yielded == LFJ8_CAN_READY ? LFJ8_H03_TORQUE_CAN_RELEASED :
               yielded == LFJ8_CAN_SLOT_BUSY ? LFJ8_H03_TORQUE_CAN_RESERVED :
                                               LFJ8_H03_TORQUE_CAN_UNAVAILABLE;
        goto poll_request;
    }

    const Lfj8CanResult listening = lfj8_h03_can0_torque_listen(io, 1u);
    if (listening != LFJ8_CAN_READY) {
        if (listening != LFJ8_CAN_SLOT_BUSY) {
            goto unavailable;
        }
        goto poll_request;
    }

    Lfj8CanData8 frame;
    const Lfj8CanRxResult received = lfj8_h03_can0_torque_receive(io, 1u, &frame);
    if (received == LFJ8_CAN_RX_WRONG_SLOT || received == LFJ8_CAN_RX_UNAVAILABLE) {
        goto unavailable;
    }
    if (continuous && !adapter->need_drain && received == LFJ8_CAN_RX_RECEIVED &&
        lfj8_h03_can0_read_timestamp(io, &tick)) {
        const uint16_t age = (uint16_t)(tick - frame.timestamp);
        const uint16_t after_tx = (uint16_t)(frame.timestamp - adapter->completed_tick);
        const bool newer_than_tx = !adapter->need_status_after_completion ||
            (after_tx != 0u && after_tx < CAN_HALF_RANGE) ||
            now_us - adapter->completion_observed_at_us >=
                (uint32_t)adapter->max_receive_age_bits * adapter->bit_time_us;
        if (age < adapter->max_receive_age_bits &&
            newer_than_tx) {
            const uint32_t captured = now_us - (uint32_t)age * adapter->bit_time_us;
            if (lfj8_h03_torque_receive(&adapter->request, frame.id, 8u, frame.payload, captured)) {
                adapter->need_status_after_completion = false;
            }
        }
    }
    if (adapter->need_drain && received != LFJ8_CAN_RX_RETRY && continuous && advancing) {
        adapter->need_drain = false;
    }
    tx_submit = submit;
    goto poll_request;

lost_ownership:
    /* An unverified completion cannot retire the old generation's TX. */
    adapter->lease_lost = adapter->lease_lost || adapter->request.pending;
    adapter->clock_seen = false;
unavailable:
    clear_status(adapter);
    input = NULL;
    slot = LFJ8_H03_TORQUE_CAN_UNAVAILABLE;
poll_request:
    lfj8_h03_torque_poll(&adapter->request, input, cal, now_us, tx_submit, &tx);
    if (tx.unavailable) {
        /* The slot became unavailable between listening and arming TX. */
        adapter->lease_lost = true;
        adapter->clock_seen = false;
        clear_status(adapter);
        lfj8_h03_torque_poll(&adapter->request, NULL, cal, now_us, NULL, NULL);
        return LFJ8_H03_TORQUE_CAN_UNAVAILABLE;
    }
    return slot;
}
