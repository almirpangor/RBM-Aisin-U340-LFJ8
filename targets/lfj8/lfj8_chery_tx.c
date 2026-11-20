#include "lfj8_chery_tx.h"

static Lfj8CaptureSnapshot foreground_vss(const Lfj8CapturePair *capture, uint32_t now_us,
                                         const Lfj8VehicleCalibration *cal, uint8_t stopped)
{
    const uint32_t timeout = cal->vss_timeout_ticks;
    const uint32_t age = now_us - capture->now_tml0;
    Lfj8CaptureSnapshot sample = capture->vss;
    if (cal->tick_hz != UINT32_C(1000000) || timeout >= UINT32_C(0x80000000) || age >= timeout ||
        (sample.state == LFJ8_VSS_VALID &&
         capture->now_tml0 - capture->vss_at_tml0 >= timeout - age) ||
        (sample.state == LFJ8_VSS_STOPPED && stopped != 1u)) {
        sample.state = LFJ8_VSS_UNAVAILABLE;
    }
    return sample;
}

void lfj8_chery_tx_init(Lfj8CheryTx *tx, uint32_t now_us, uint32_t period_1ae_us,
                       uint32_t period_300_us)
{
    lfj8_schedule_init(&tx->schedule, now_us, period_1ae_us, period_300_us);
    tx->pending = 0u;
    tx->last_submitted = 0u;
    tx->counter_f8e4 = 0u;
}

Lfj8CanResult lfj8_chery_tx_poll_status(Lfj8CheryTx *tx, const Lfj8RegisterIo *io,
                                       uint32_t now_us, uint8_t slot13_owned,
                                       volatile Lfj8RawVss *vss, const Lfj8VehicleCalibration *cal,
                                       const Lfj8CheryTxInputs *inputs, uint8_t *submitted)
{
    const uint8_t due = lfj8_schedule_poll(&tx->schedule, now_us);
    uint8_t payload[8];
    uint8_t selected;
    uint8_t next_counter = tx->counter_f8e4;
    uint16_t id;

    *submitted = 0u;
    if (slot13_owned == 0u) {
        tx->pending = 0u;
        tx->last_submitted = 0u;
        tx->counter_f8e4 = 0u;
        return LFJ8_CAN_SLOT_NOT_OWNED;
    }
    tx->pending |= due;
    if (tx->pending == 0u) {
        return LFJ8_CAN_READY;
    }

    /* At most one pending frame per ID. Alternate if both are waiting. */
    selected = tx->pending;
    if (selected == (LFJ8_DUE_1AE | LFJ8_DUE_300)) {
        selected = (uint8_t)(tx->last_submitted == LFJ8_DUE_1AE ? LFJ8_DUE_300 : LFJ8_DUE_1AE);
    }

    if (selected == LFJ8_DUE_1AE) {
        const Lfj8CaptureSnapshot sample = inputs->s51_capture
            ? foreground_vss(inputs->s51_capture, now_us, cal, inputs->stopped)
            : lfj8_raw_vss_snapshot_with_standstill(vss, io, cal->vss_timeout_ticks, inputs->stopped);
        const uint16_t raw = lfj8_vss_raw_1ae(sample.interval_ticks, (uint8_t)sample.pulse_window,
                                              cal->tick_hz, cal->wheel_um, cal->wheel_num,
                                              cal->wheel_den, sample.state);
        next_counter = lfj8_pack_1ae_with_counter(payload, &inputs->status_1ae, raw,
                                                 tx->counter_f8e4);
        id = LFJ8_CAN_1AE;
    } else {
        lfj8_pack_300(payload, inputs->status0_300, inputs->status1_300,
                      inputs->flag_fd18_9, inputs->atf_c, inputs->atf_valid);
        id = LFJ8_CAN_300;
    }

    const Lfj8CanResult status = lfj8_can0_slot13_submit(io, slot13_owned, id, payload);
    if (status == LFJ8_CAN_SUBMITTED) {
        tx->counter_f8e4 = next_counter;
        tx->pending &= (uint8_t)~selected;
        tx->last_submitted = selected;
        *submitted = selected;
    }
    return status;
}

uint8_t lfj8_chery_tx_poll(Lfj8CheryTx *tx, const Lfj8RegisterIo *io, uint32_t now_us,
                          uint8_t slot13_owned, volatile Lfj8RawVss *vss,
                          const Lfj8VehicleCalibration *cal,
                          const Lfj8CheryTxInputs *inputs)
{
    uint8_t submitted;
    lfj8_chery_tx_poll_status(tx, io, now_us, slot13_owned, vss, cal, inputs, &submitted);
    return submitted;
}
