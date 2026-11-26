#include "chery_torque_rx.h"

#include <assert.h>
#include <stdio.h>

static BoschCheryTorqueFrame make_frame(uint8_t sequence, uint8_t byte1, uint8_t byte4,
        bool active, bool corrupt) {
    const uint8_t checksum = (uint8_t)~(uint8_t)(byte1 + byte4) ^ (uint8_t)corrupt;
    return (BoschCheryTorqueFrame){
        .id = BOSCH_CHERY_TORQUE_CAN_ID, .dlc = 8,
        .payload = {
            checksum & 15u, byte1, (uint8_t)(((sequence & 7u) << 4) | (uint8_t)active),
            (uint8_t)(0x30u | (checksum >> 4)), byte4,
        },
    };
}

static BoschCheryTorqueResult submit(BoschCheryTorqueRx *rx, uint32_t tick,
        uint8_t sequence, uint8_t byte1, uint8_t byte4, bool corrupt) {
    const BoschCheryTorqueFrame frame = make_frame(sequence, byte1, byte4, true, corrupt);
    return bosch_chery_torque_receive(rx, &frame, tick, true);
}

static BoschCheryTorqueResult submit_captured(BoschCheryTorqueRx *rx, uint32_t captured_at,
        uint32_t now, uint8_t sequence) {
    const BoschCheryTorqueFrame frame = make_frame(sequence, 40, 60, true, false);
    return bosch_chery_torque_receive_captured(rx, &frame, captured_at, now, true);
}

static void test_capture_age(void) {
    BoschCheryTorqueRx rx;
    assert(bosch_chery_torque_init(&rx, 8));
    assert(submit_captured(&rx, 1, 20, 7) == BOSCH_CHERY_TORQUE_STALE);
    assert(submit_captured(&rx, 2, 21, 0) == BOSCH_CHERY_TORQUE_STALE);
    assert(!rx.synchronized && bosch_chery_torque_snapshot(&rx, 21, true).valid_channels == 0);

    const uint32_t start = UINT32_MAX - 3;
    assert(submit_captured(&rx, start - 8, start, 7) == BOSCH_CHERY_TORQUE_STALE);
    assert(submit_captured(&rx, start + 1, start, 7) == BOSCH_CHERY_TORQUE_STALE);
    assert(submit_captured(&rx, start, start + 1, 7) == BOSCH_CHERY_TORQUE_SYNCHRONIZING);
    assert(submit_captured(&rx, start + 1, start + 4, 0) == BOSCH_CHERY_TORQUE_ACCEPTED);
    assert(submit_captured(&rx, start, start + 5, 7) == BOSCH_CHERY_TORQUE_STALE);
    assert(bosch_chery_torque_snapshot(&rx, start + 8, true).valid_channels == BOSCH_CHERY_TORQUE_BOTH);
    assert(bosch_chery_torque_snapshot(&rx, start + 9, true).valid_channels == 0);

    assert(submit_captured(&rx, 10, 17, 1) == BOSCH_CHERY_TORQUE_SYNCHRONIZING);
    /* Earlier capture expired before the next fresh frame was serviced. */
    assert(submit_captured(&rx, 12, 18, 2) == BOSCH_CHERY_TORQUE_SYNCHRONIZING);
    assert(bosch_chery_torque_snapshot(&rx, 18, true).valid_channels == 0);
    assert(submit_captured(&rx, 18, 19, 3) == BOSCH_CHERY_TORQUE_ACCEPTED);
}

static void test_capture_order_after_revocation(void) {
    BoschCheryTorqueRx rx;
    assert(bosch_chery_torque_init(&rx, 8));
    assert(submit_captured(&rx, 10, 10, 1) == BOSCH_CHERY_TORQUE_SYNCHRONIZING);
    assert(submit_captured(&rx, 11, 11, 2) == BOSCH_CHERY_TORQUE_ACCEPTED);
    assert(bosch_chery_torque_snapshot(&rx, 14, false).valid_channels == 0);
    assert(submit_captured(&rx, 13, 15, 3) == BOSCH_CHERY_TORQUE_STALE);
    assert(submit_captured(&rx, 15, 16, 4) == BOSCH_CHERY_TORQUE_SYNCHRONIZING);
    assert(submit_captured(&rx, 16, 17, 5) == BOSCH_CHERY_TORQUE_ACCEPTED);

    const BoschCheryTorqueFrame inactive = make_frame(0, 40, 60, false, false);
    assert(bosch_chery_torque_receive_captured(&rx, &inactive, 18, 19, true) ==
           BOSCH_CHERY_TORQUE_INACTIVE);
    assert(submit_captured(&rx, 17, 20, 6) == BOSCH_CHERY_TORQUE_STALE);
    assert(submit_captured(&rx, 19, 20, 1) == BOSCH_CHERY_TORQUE_SYNCHRONIZING);

    BoschCheryTorqueFrame lost = make_frame(2, 40, 60, true, false);
    lost.lost = true;
    assert(bosch_chery_torque_receive_captured(&rx, &lost, 21, 22, true) ==
           BOSCH_CHERY_TORQUE_MALFORMED);
    assert(submit_captured(&rx, 20, 22, 2) == BOSCH_CHERY_TORQUE_STALE);
    assert(bosch_chery_torque_snapshot(&rx, 22, true).valid_channels == 0);
    assert(submit_captured(&rx, 22, 22, 3) == BOSCH_CHERY_TORQUE_SYNCHRONIZING);
    assert(submit_captured(&rx, 22, 23, 4) == BOSCH_CHERY_TORQUE_ACCEPTED);
}

static void test_capture_generation(void) {
    BoschCheryTorqueRx rx;
    assert(bosch_chery_torque_init(&rx, 8));
    const BoschCheryTorqueFrame first = make_frame(7, 40, 60, true, false);
    const BoschCheryTorqueFrame second = make_frame(0, 40, 60, true, false);
    const BoschCheryTorqueCapture old_first = {.tick = 1, .generation = UINT32_MAX};
    const BoschCheryTorqueCapture old_second = {.tick = 2, .generation = UINT32_MAX};
    const BoschCheryTorqueCapture new_first = {.tick = 1, .generation = 0};
    const BoschCheryTorqueCapture new_second = {.tick = 2, .generation = 0};

    assert(bosch_chery_torque_receive_queued(&rx, &first, new_first, 1, true) ==
           BOSCH_CHERY_TORQUE_STALE);
    bosch_chery_torque_set_generation(&rx, UINT32_MAX);
    assert(bosch_chery_torque_receive_queued(&rx, &first, old_first, 1, true) ==
           BOSCH_CHERY_TORQUE_SYNCHRONIZING);
    assert(bosch_chery_torque_receive_queued(&rx, &second, old_second, 2, true) ==
           BOSCH_CHERY_TORQUE_ACCEPTED);

    /* CAN recovered and its clock restarted. Old captures appear fresh. */
    bosch_chery_torque_set_generation(&rx, 0);
    assert(bosch_chery_torque_snapshot(&rx, 1, true).valid_channels == 0);
    assert(bosch_chery_torque_receive_queued(&rx, &first, old_first, 1, true) ==
           BOSCH_CHERY_TORQUE_STALE);
    assert(bosch_chery_torque_receive_queued(&rx, &second, old_second, 2, true) ==
           BOSCH_CHERY_TORQUE_STALE);
    assert(bosch_chery_torque_receive_queued(&rx, &first, new_first, 2, true) ==
           BOSCH_CHERY_TORQUE_SYNCHRONIZING);
    assert(bosch_chery_torque_receive_queued(&rx, &second, new_second, 2, true) ==
           BOSCH_CHERY_TORQUE_ACCEPTED);

    const BoschCheryTorqueFrame inactive = make_frame(1, 40, 60, false, false);
    const BoschCheryTorqueCapture late_old = {.tick = 3, .generation = UINT32_MAX};
    assert(bosch_chery_torque_receive_queued(&rx, &inactive, late_old, 3, true) ==
           BOSCH_CHERY_TORQUE_STALE);
    bosch_chery_torque_set_generation(&rx, 0);
    assert(bosch_chery_torque_snapshot(&rx, 3, true).valid_channels == BOSCH_CHERY_TORQUE_BOTH);
    assert(rx.order_floor_tick == 2);

    /* An external permit withdrawal remains effective even with a stale frame. */
    assert(bosch_chery_torque_receive_queued(&rx, &inactive, late_old, 4, false) ==
           BOSCH_CHERY_TORQUE_BLOCKED);
    assert(bosch_chery_torque_snapshot(&rx, 4, true).valid_channels == 0);
    assert(bosch_chery_torque_receive_queued(&rx, &second, new_second, 4, true) ==
           BOSCH_CHERY_TORQUE_STALE);
}

static void test_permit_boundary(void) {
    static const uint32_t boundaries[] = {14, UINT32_MAX, 0};
    const BoschCheryTorqueFrame first = make_frame(7, 40, 60, true, false);
    const BoschCheryTorqueFrame second = make_frame(0, 40, 60, true, false);
    const uint32_t generation = 7;
    for (size_t i = 0; i < sizeof boundaries / sizeof boundaries[0]; ++i) {
        const uint32_t withdrawn_at = boundaries[i];
        BoschCheryTorqueRx rx;
        assert(bosch_chery_torque_init(&rx, 8));
        bosch_chery_torque_set_generation(&rx, generation);
        assert(submit_captured(&rx, withdrawn_at - 2, withdrawn_at - 2, 1) ==
               BOSCH_CHERY_TORQUE_SYNCHRONIZING);
        assert(submit_captured(&rx, withdrawn_at - 1, withdrawn_at - 1, 2) ==
               BOSCH_CHERY_TORQUE_ACCEPTED);

        assert(bosch_chery_torque_snapshot(&rx, withdrawn_at, false).valid_channels == 0);
        const BoschCheryTorqueCapture queued = {.tick = withdrawn_at, .generation = generation};
        assert(bosch_chery_torque_receive_queued(&rx, &first, queued, withdrawn_at, true) ==
               BOSCH_CHERY_TORQUE_STALE);
        assert(bosch_chery_torque_receive(&rx, &first, withdrawn_at, true) ==
               BOSCH_CHERY_TORQUE_STALE);
        assert(submit_captured(&rx, withdrawn_at, withdrawn_at + 1, 7) ==
               BOSCH_CHERY_TORQUE_STALE);
        assert(!rx.synchronized);

        assert(submit_captured(&rx, withdrawn_at + 1, withdrawn_at + 1, 7) ==
               BOSCH_CHERY_TORQUE_SYNCHRONIZING);
        assert(bosch_chery_torque_snapshot(&rx, withdrawn_at + 1, true).valid_channels == 0);
        const BoschCheryTorqueCapture fresh = {.tick = withdrawn_at + 1, .generation = generation};
        assert(bosch_chery_torque_receive_queued(&rx, &second, fresh, withdrawn_at + 2, true) ==
               BOSCH_CHERY_TORQUE_ACCEPTED);
        assert(bosch_chery_torque_snapshot(&rx, withdrawn_at + 2, true).valid_channels ==
               BOSCH_CHERY_TORQUE_BOTH);

        assert(bosch_chery_torque_snapshot(&rx, withdrawn_at + 3, false).valid_channels == 0);
        assert(bosch_chery_torque_snapshot(&rx, withdrawn_at + 4, false).valid_channels == 0);
        assert(submit_captured(&rx, withdrawn_at + 4, withdrawn_at + 5, 7) ==
               BOSCH_CHERY_TORQUE_STALE);
        assert(!rx.synchronized);
    }
}

static void test_transport(void) {
    BoschCheryTorqueRx rx;
    assert(!bosch_chery_torque_init(&rx, 0));
    assert(!bosch_chery_torque_init(&rx, UINT32_C(0x80000000)));
    assert(bosch_chery_torque_init(&rx, 30));
    const uint32_t start = UINT32_MAX - 5;
    assert(submit(&rx, start, 7, 40, 60, false) == BOSCH_CHERY_TORQUE_SYNCHRONIZING);
    assert(bosch_chery_torque_snapshot(&rx, start, true).valid_channels == 0);
    assert(submit(&rx, start + 2, 0, 40, 60, false) == BOSCH_CHERY_TORQUE_ACCEPTED);
    assert(submit(&rx, start + 3, 2, 40, 60, false) == BOSCH_CHERY_TORQUE_ACCEPTED);
    const BoschCheryTorqueSample sample = bosch_chery_torque_snapshot(&rx, start + 32, true);
    assert(sample.valid_channels == BOSCH_CHERY_TORQUE_BOTH);
    assert(sample.operand_byte1 == -2621 && sample.operand_byte4 == 2621);
    assert(bosch_chery_torque_snapshot(&rx, start + 33, true).valid_channels == 0);
    assert(submit(&rx, start + 34, 6, 60, 40, false) == BOSCH_CHERY_TORQUE_SYNCHRONIZING);
    assert(submit(&rx, start + 35, 7, 60, 40, false) == BOSCH_CHERY_TORQUE_ACCEPTED);

    BoschCheryTorqueFrame unrelated = make_frame(5, 20, 80, true, false);
    unrelated.id = 0x300;
    assert(bosch_chery_torque_receive(&rx, &unrelated, start + 36, true) == BOSCH_CHERY_TORQUE_IGNORED);
    assert(bosch_chery_torque_snapshot(&rx, start + 36, true).operand_byte4 == -2621);
    assert(bosch_chery_torque_snapshot(&rx, start + 37, false).valid_channels == 0);
    assert(submit(&rx, start + 38, 0, 60, 40, false) == BOSCH_CHERY_TORQUE_SYNCHRONIZING);

    const BoschCheryTorqueFrame inactive = make_frame(1, 250, 250, false, false);
    assert(bosch_chery_torque_receive(&rx, &inactive, start + 39, true) == BOSCH_CHERY_TORQUE_INACTIVE);
    assert(submit(&rx, start + 40, 2, 40, 60, false) == BOSCH_CHERY_TORQUE_SYNCHRONIZING);
    for (unsigned invalid_type = 0; invalid_type < 5; ++invalid_type) {
        BoschCheryTorqueFrame frame = make_frame(3, 40, 60, true, false);
        frame.extended = invalid_type == 0;
        frame.remote = invalid_type == 1;
        frame.fd = invalid_type == 2;
        frame.lost = invalid_type == 3;
        if (invalid_type == 4) {
            frame.dlc = 7;
        }
        assert(bosch_chery_torque_receive(&rx, &frame, start + 41, true) == BOSCH_CHERY_TORQUE_MALFORMED);
        assert(!rx.synchronized);
        assert(bosch_chery_torque_snapshot(&rx, start + 41, true).valid_channels == 0);
    }
}

static void test_qualification(void) {
    BoschCheryTorqueRx rx;
    assert(bosch_chery_torque_init(&rx, 50));
    assert(submit(&rx, 0, 0, 40, 60, false) == BOSCH_CHERY_TORQUE_SYNCHRONIZING);
    assert(submit(&rx, 1, 1, 40, 60, false) == BOSCH_CHERY_TORQUE_ACCEPTED);
    const uint8_t native_checksum_flags[] = {0x01, 0x01, 0x99, 0xB9};
    for (uint8_t sequence = 2; sequence < 6; ++sequence) {
        assert(submit(&rx, sequence, sequence, 60, 40, true) == BOSCH_CHERY_TORQUE_UNQUALIFIED);
        assert(bosch_chery_torque_snapshot(&rx, sequence, true).valid_channels == 0);
        assert(rx.qualification.request_8c86 == (uint16_t)-2621);
        assert(rx.qualification.flags_8182 == native_checksum_flags[sequence - 2]);
    }
    assert((rx.qualification.flags_8182 & 0xA0u) == 0xA0u);
    for (uint8_t sequence = 6; sequence < 9; ++sequence) {
        assert(submit(&rx, sequence, sequence, 60, 40, false) == BOSCH_CHERY_TORQUE_UNQUALIFIED);
        assert(rx.qualification.flags_8182 == 0xB8u);
    }
    assert(submit(&rx, 9, 1, 60, 40, false) == BOSCH_CHERY_TORQUE_ACCEPTED);
    assert(rx.qualification.flags_8182 == 0);

    for (uint32_t tick = 10; tick < 13; ++tick) {
        assert(submit(&rx, tick, 1, 40, 60, false) == BOSCH_CHERY_TORQUE_UNQUALIFIED);
    }
    assert(rx.qualification.flags_8182 & 0x40u);
    assert(submit(&rx, 13, 2, UINT8_MAX, 60, false) == BOSCH_CHERY_TORQUE_ACCEPTED);
    assert((rx.qualification.flags_8182 & 0x40u) == 0);
    const BoschCheryTorqueSample byte4 = bosch_chery_torque_snapshot(&rx, 13, true);
    assert(byte4.valid_channels == BOSCH_CHERY_TORQUE_BYTE4);
    assert(byte4.operand_byte1 == 0 && byte4.operand_byte4 == 2621);
    assert(submit(&rx, 14, 3, 40, UINT8_MAX, false) == BOSCH_CHERY_TORQUE_ACCEPTED);
    const BoschCheryTorqueSample byte1 = bosch_chery_torque_snapshot(&rx, 14, true);
    assert(byte1.valid_channels == BOSCH_CHERY_TORQUE_BYTE1);
    assert(byte1.operand_byte1 == -2621 && byte1.operand_byte4 == 0);
    assert(submit(&rx, 15, 4, UINT8_MAX, UINT8_MAX, false) == BOSCH_CHERY_TORQUE_UNQUALIFIED);
}

static void test_calibration_lookup(void) {
    BoschCheryTorqueRx rx;
    assert(bosch_chery_torque_init(&rx, 8));
    assert(submit(&rx, 0, 0, 40, 60, false) == BOSCH_CHERY_TORQUE_SYNCHRONIZING);
    assert(submit(&rx, 1, 1, 40, 60, false) == BOSCH_CHERY_TORQUE_ACCEPTED);
    /* Synthetic points exercise lookup behavior only. */
    const BoschCheryTorqueCalibration match[] = {{7, -2621, 2621, 24}, {8, -2621, 2621, 65}};
    const BoschCheryTorqueCalibration duplicate[] = {{7, -2621, 2621, 12}, {7, -2621, 2621, 24}};
    const BoschCheryTorqueCalibration reversed[] = {{7, 2621, -2621, 24}};
    uint8_t q8 = 255;
    assert(!bosch_chery_torque_lookup_q8(&rx, 1, true, NULL, 0, 7, &q8) && q8 == 0);
    assert(!bosch_chery_torque_lookup_q8(&rx, 1, true, match, 2, 9, &q8) && q8 == 0);
    assert(!bosch_chery_torque_lookup_q8(&rx, 1, true, match, 2, 8, &q8) && q8 == 0);
    assert(!bosch_chery_torque_lookup_q8(&rx, 1, true, reversed, 1, 7, &q8) && q8 == 0);
    assert(!bosch_chery_torque_lookup_q8(&rx, 1, true, duplicate, 2, 7, &q8) && q8 == 0);
    assert(bosch_chery_torque_lookup_q8(&rx, 1, true, match, 2, 7, &q8) && q8 == 24);
    assert(!bosch_chery_torque_lookup_q8(&rx, 9, true, match, 2, 7, &q8) && q8 == 0);
    assert(submit(&rx, 10, 4, 40, 60, false) == BOSCH_CHERY_TORQUE_SYNCHRONIZING);
    assert(submit(&rx, 11, 5, 40, UINT8_MAX, false) == BOSCH_CHERY_TORQUE_ACCEPTED);
    assert(!bosch_chery_torque_lookup_q8(&rx, 11, true, match, 2, 7, &q8) && q8 == 0);
}

int main(void) {
    test_transport();
    test_capture_age();
    test_capture_order_after_revocation();
    test_capture_generation();
    test_permit_boundary();
    test_qualification();
    test_calibration_lookup();
    puts("Bosch Chery torque qualification, capture-time lease, CAN generation and calibrated lookup PASS (host)");
    return 0;
}
