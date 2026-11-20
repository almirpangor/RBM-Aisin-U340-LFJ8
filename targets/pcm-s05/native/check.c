#include "s05_chery.h"

typedef struct {
    uint8_t accepts;
    uint8_t attempts;
    uint16_t last_id;
    uint8_t last_payload[8];
} CheckChannel;

static uint8_t submit(void *ctx, uint16_t std_id, const uint8_t payload[8])
{
    CheckChannel *channel = ctx;
    unsigned i;

    ++channel->attempts;
    channel->last_id = std_id;
    for (i = 0u; i < 8u; ++i) {
        channel->last_payload[i] = payload[i];
    }
    return channel->accepts;
}

static uint8_t payload_equals(const CheckChannel *channel, const uint8_t expected[8])
{
    unsigned i;
    for (i = 0u; i < 8u; ++i) {
        if (channel->last_payload[i] != expected[i]) {
            return 0u;
        }
    }
    return 1u;
}

int s05_chery_check(void)
{
    static const uint8_t expected_1ae[8] = {0x1a, 0xb1, 0x9f, 0x50, 0x44, 0xfe, 0x12, 0x34};
    static const uint8_t expected_300[8] = {0xa0, 0x02, 0x40, 0x23, 0x00, 0x00, 0x00, 0x00};
    S05CheryTransport transport;
    S05CheryInputs inputs;
    CheckChannel channel;

    inputs.status_1ae.byte1 = 0xb1u;
    inputs.status_1ae.byte3_high = 5u;
    inputs.status_1ae.byte4 = 0x44u;
    inputs.status_1ae.raw_fa5f = 130u;
    inputs.status_1ae.raw_f8e1 = 0xf3u;
    inputs.status_1ae.counter_f8e4 = 0x80u;
    inputs.status_1ae.flag_f842_5 = 1u;
    inputs.status_1ae.flag_fd18_4 = 1u;
    inputs.status_1ae.flag_fd10_7 = 1u;
    inputs.status_1ae.flag_f83e_4 = 1u;
    inputs.status_1ae.flag_e026_0 = 0u;
    inputs.speed_raw = 0x1234u;
    inputs.status0_300 = 0xa0u;
    inputs.status1_300 = 0x02u;
    inputs.flag_fd18_9 = 1u;
    inputs.atf_c = -5;
    inputs.atf_valid = 1u;
    channel.attempts = 0u;
    channel.accepts = 0u;

    s05_chery_init(&transport, UINT32_C(0xfffffff0), 10u, 20u);
    if (s05_chery_poll(&transport, UINT32_C(0xfffffff9), &inputs, submit, &channel) != 0u ||
        channel.attempts != 0u) {
        return 1;
    }
    if (s05_chery_poll(&transport, UINT32_C(0xfffffffa), &inputs, submit, &channel) != 0u ||
        channel.attempts != 1u || channel.last_id != LFJ8_CAN_1AE ||
        !payload_equals(&channel, expected_1ae) || transport.counter_f8e4 != 0u) {
        return 2;
    }
    channel.accepts = 1u;
    if (s05_chery_poll(&transport, 4u, &inputs, submit, &channel) != LFJ8_DUE_1AE ||
        channel.attempts != 2u || channel.last_id != LFJ8_CAN_1AE ||
        !payload_equals(&channel, expected_1ae) || transport.counter_f8e4 != 1u) {
        return 3;
    }
    if (s05_chery_poll(&transport, 4u, &inputs, submit, &channel) != LFJ8_DUE_300 ||
        channel.attempts != 3u || channel.last_id != LFJ8_CAN_300 ||
        !payload_equals(&channel, expected_300) || transport.counter_f8e4 != 1u) {
        return 4;
    }
    if (s05_chery_poll(&transport, 13u, &inputs, submit, &channel) != 0u) {
        return 5;
    }
    inputs.speed_raw = LFJ8_SPEED_WRAP;
    if (s05_chery_poll(&transport, 14u, &inputs, submit, &channel) != LFJ8_DUE_1AE ||
        transport.counter_f8e4 != 2u || channel.last_payload[2] != 0xafu ||
        channel.last_payload[6] != 0xffu || channel.last_payload[7] != 0xffu) {
        return 6;
    }
    if (s05_chery_poll(&transport, 24u, 0, 0, 0) != 0u || channel.attempts != 4u ||
        transport.counter_f8e4 != 0u || transport.pending != 0u ||
        s05_chery_poll(&transport, 24u, &inputs, submit, &channel) != 0u) {
        return 7;
    }
    inputs.atf_valid = 0u;
    if (s05_chery_poll(&transport, 44u, &inputs, submit, &channel) != LFJ8_DUE_1AE ||
        s05_chery_poll(&transport, 44u, &inputs, submit, &channel) != LFJ8_DUE_300 ||
        channel.last_payload[3] != 0xffu) {
        return 8;
    }
    return 0;
}

#ifdef S05_HOST_CHECK
int main(void)
{
    return s05_chery_check();
}
#endif
