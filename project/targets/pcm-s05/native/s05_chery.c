#include "s05_chery.h"

void s05_chery_init(S05CheryTransport *transport, uint32_t now_us,
                    uint32_t period_1ae_us, uint32_t period_300_us)
{
    lfj8_schedule_init(&transport->schedule, now_us, period_1ae_us, period_300_us);
    transport->pending = 0u;
    transport->last_submitted = 0u;
    transport->counter_f8e4 = 0u;
}

uint8_t s05_chery_poll(S05CheryTransport *transport, uint32_t now_us,
                      const S05CheryInputs *inputs, S05CanSubmit submit, void *channel)
{
    uint8_t payload[8];
    uint8_t selected;
    uint16_t id;
    uint8_t next_counter = transport->counter_f8e4;

    transport->pending |= lfj8_schedule_poll(&transport->schedule, now_us);
    if (submit == 0) {
        transport->pending = 0u;
        transport->last_submitted = 0u;
        transport->counter_f8e4 = 0u;
        return 0u;
    }
    selected = transport->pending;
    if (selected == 0u) {
        return 0u;
    }
    if (selected == (LFJ8_DUE_1AE | LFJ8_DUE_300)) {
        selected = transport->last_submitted == LFJ8_DUE_1AE ? LFJ8_DUE_300 : LFJ8_DUE_1AE;
    }

    if (selected == LFJ8_DUE_1AE) {
        uint16_t speed_raw = inputs->speed_raw;
        if (speed_raw >= LFJ8_SPEED_WRAP) {
            speed_raw = LFJ8_SPEED_UNAVAILABLE;
        }
        next_counter = lfj8_pack_1ae_with_counter(payload, &inputs->status_1ae,
                                                  speed_raw, next_counter);
        id = LFJ8_CAN_1AE;
    } else {
        lfj8_pack_300(payload, inputs->status0_300, inputs->status1_300,
                      inputs->flag_fd18_9, inputs->atf_c, inputs->atf_valid);
        id = LFJ8_CAN_300;
    }

    if (submit(channel, id, payload) == 0u) {
        return 0u;
    }
    transport->pending &= (uint8_t)~selected;
    transport->last_submitted = selected;
    transport->counter_f8e4 = next_counter;
    return selected;
}
