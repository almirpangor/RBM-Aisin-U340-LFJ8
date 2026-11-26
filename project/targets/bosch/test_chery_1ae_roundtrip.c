#include "chery_torque_rx.h"
#include "../lfj8/lfj8_bridge.h"

#include <assert.h>
#include <stdio.h>

static BoschCheryTorqueFrame encode(const Lfj8Chery1ae *inputs, uint8_t *counter)
{
    BoschCheryTorqueFrame frame = {.id = LFJ8_CAN_1AE, .dlc = 8};
    *counter = lfj8_pack_1ae_with_counter(frame.payload, inputs, 0x1234u, *counter);
    return frame;
}

static void test_operands(void)
{
    for (unsigned byte1 = 0; byte1 <= UINT8_MAX; ++byte1) {
        for (unsigned byte4 = 0; byte4 <= UINT8_MAX; ++byte4) {
            Lfj8Chery1ae inputs = {
                .byte1 = (uint8_t)byte1, .byte4 = (uint8_t)byte4, .flag_fd18_4 = 1,
                .flag_f842_5 = 1, .byte3_high = 0xAu,
            };
            const uint8_t channels =
                (byte1 != UINT8_MAX ? BOSCH_CHERY_TORQUE_BYTE1 : 0) |
                (byte4 != UINT8_MAX ? BOSCH_CHERY_TORQUE_BYTE4 : 0);
            BoschCheryTorqueRx rx;
            assert(bosch_chery_torque_init(&rx, 8));

            uint8_t counter = 6;
            BoschCheryTorqueFrame frame = encode(&inputs, &counter);
            assert(bosch_chery_torque_receive(&rx, &frame, 0, true) ==
                   BOSCH_CHERY_TORQUE_SYNCHRONIZING);
            frame = encode(&inputs, &counter);
            assert(bosch_chery_torque_receive(&rx, &frame, 1, true) ==
                   (channels ? BOSCH_CHERY_TORQUE_ACCEPTED : BOSCH_CHERY_TORQUE_UNQUALIFIED));
            assert(rx.qualification.raw_8173 == byte1 && rx.qualification.raw_8172 == byte4);
            assert(rx.qualification.sequence_8166 == 0);
            assert((rx.qualification.flags_8182 & 3u) == 0);
            assert(bosch_chery_torque_snapshot(&rx, 1, true).valid_channels == channels);
        }
    }
}

static void test_validity(void)
{
    Lfj8Chery1ae inputs = {.byte1 = 40, .byte4 = 60, .flag_fd18_4 = 1};
    BoschCheryTorqueRx rx;
    uint8_t counter = 0;
    assert(bosch_chery_torque_init(&rx, 8));
    BoschCheryTorqueFrame frame = encode(&inputs, &counter);
    assert(bosch_chery_torque_receive(&rx, &frame, 0, true) == BOSCH_CHERY_TORQUE_SYNCHRONIZING);
    (void)encode(&inputs, &counter);
    frame = encode(&inputs, &counter);
    assert(bosch_chery_torque_receive(&rx, &frame, 2, true) == BOSCH_CHERY_TORQUE_ACCEPTED);
    BoschCheryTorqueSample sample = bosch_chery_torque_snapshot(&rx, 2, true);
    assert(sample.operand_byte1 == -2621 && sample.operand_byte4 == 2621);

    assert(bosch_chery_torque_receive(&rx, &frame, 3, true) == BOSCH_CHERY_TORQUE_UNQUALIFIED);
    assert(bosch_chery_torque_snapshot(&rx, 3, true).valid_channels == 0);
    frame = encode(&inputs, &counter);
    frame.payload[0] ^= 1u;
    assert(bosch_chery_torque_receive(&rx, &frame, 4, true) == BOSCH_CHERY_TORQUE_UNQUALIFIED);
    assert(bosch_chery_torque_snapshot(&rx, 4, true).valid_channels == 0);
    frame = encode(&inputs, &counter);
    assert(bosch_chery_torque_receive(&rx, &frame, 5, true) == BOSCH_CHERY_TORQUE_ACCEPTED);

    inputs.flag_fd18_4 = 0;
    frame = encode(&inputs, &counter);
    assert(counter == 0);
    assert(bosch_chery_torque_receive(&rx, &frame, 6, true) == BOSCH_CHERY_TORQUE_INACTIVE);
    assert(bosch_chery_torque_snapshot(&rx, 6, true).valid_channels == 0);
    inputs.flag_fd18_4 = 1;
    frame = encode(&inputs, &counter);
    assert(bosch_chery_torque_receive(&rx, &frame, 7, true) == BOSCH_CHERY_TORQUE_SYNCHRONIZING);
    frame = encode(&inputs, &counter);
    assert(bosch_chery_torque_receive(&rx, &frame, 8, true) == BOSCH_CHERY_TORQUE_ACCEPTED);
    assert(bosch_chery_torque_snapshot(&rx, 15, true).valid_channels == BOSCH_CHERY_TORQUE_BOTH);
    assert(bosch_chery_torque_snapshot(&rx, 16, true).valid_channels == 0);
    frame = encode(&inputs, &counter);
    assert(bosch_chery_torque_receive(&rx, &frame, 16, true) == BOSCH_CHERY_TORQUE_SYNCHRONIZING);
}

int main(void)
{
    test_operands();
    test_validity();
    puts("CAN-05 PASS: 65536 operand pairs, counter wrap/gap/replay, checksum, disable and expiry (host model)");
    return 0;
}
