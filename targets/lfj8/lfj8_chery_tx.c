#include "lfj8_chery_tx.h"

void lfj8_chery_tx_init(Lfj8CheryTx *tx, uint32_t now_us, uint32_t period_1ae_us,
                       uint32_t period_300_us)
{
    lfj8_schedule_init(&tx->schedule, now_us, period_1ae_us, period_300_us);
    tx->pending = 0u;
    tx->last_submitted = 0u;
    tx->counter_f8e4 = 0u;
}

uint8_t lfj8_chery_tx_poll(Lfj8CheryTx *tx, const Lfj8RegisterIo *io, uint32_t now_us,
                          uint8_t slot13_owned, volatile Lfj8RawVss *vss,
                          const Lfj8VehicleCalibration *cal,
                          const Lfj8CheryTxInputs *inputs)
{
    const uint8_t due = lfj8_schedule_poll(&tx->schedule, now_us);
    uint8_t payload[8];
    uint8_t selected;
    uint8_t next_counter = tx->counter_f8e4;
    uint16_t id;

    if (slot13_owned == 0u) {
        tx->pending = 0u;
        tx->last_submitted = 0u;
        tx->counter_f8e4 = 0u;
        return 0u;
    }
    tx->pending |= due;
    if (tx->pending == 0u) {
        return 0u;
    }

    /* At most one pending frame per ID. Alternate if both are waiting. */
    selected = tx->pending;
    if (selected == (LFJ8_DUE_1AE | LFJ8_DUE_300)) {
        selected = (uint8_t)(tx->last_submitted == LFJ8_DUE_1AE ? LFJ8_DUE_300 : LFJ8_DUE_1AE);
    }

    if (selected == LFJ8_DUE_1AE) {
        const Lfj8CaptureSnapshot sample =
            lfj8_9e1b_raw_vss_snapshot(vss, io, cal->vss_timeout_ticks);
        uint8_t state = sample.state;
        uint16_t raw;

        if (state == LFJ8_VSS_UNAVAILABLE && inputs->stopped != 0u) {
            state = LFJ8_VSS_STOPPED;
        }
        raw = lfj8_vss_raw_1ae(sample.interval_ticks, (uint8_t)sample.pulse_window,
                              cal->tick_hz, cal->wheel_um, cal->wheel_num,
                              cal->wheel_den, state);
        next_counter = lfj8_pack_1ae_with_counter(payload, &inputs->status_1ae, raw,
                                                 tx->counter_f8e4);
        id = LFJ8_CAN_1AE;
    } else {
        lfj8_pack_300(payload, inputs->status0_300, inputs->status1_300,
                      inputs->flag_fd18_9, inputs->atf_c, inputs->atf_valid);
        id = LFJ8_CAN_300;
    }

    if (lfj8_can0_slot13_submit(io, slot13_owned, id, payload) != LFJ8_CAN_SUBMITTED) {
        return 0u;
    }
    tx->counter_f8e4 = next_counter;
    tx->pending &= (uint8_t)~selected;
    tx->last_submitted = selected;
    return selected;
}
