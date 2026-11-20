#include "chery_torque_rx.h"

static void clear_sample(BoschCheryTorqueRx *rx) {
    rx->sample = (BoschCheryTorqueSample){0};
}

static void revoke(BoschCheryTorqueRx *rx) {
    clear_sample(rx);
    rx->synchronized = false;
}

static int16_t signed_word(uint16_t word) {
    return word <= INT16_MAX ? (int16_t)word : (int16_t)((int32_t)word - INT32_C(65536));
}

bool bosch_chery_torque_init(BoschCheryTorqueRx *rx, uint32_t lease_ticks) {
    if (rx == NULL) {
        return false;
    }
    *rx = (BoschCheryTorqueRx){0};
    if (lease_ticks == 0 || lease_ticks > INT32_MAX) {
        return false;
    }
    rx->lease_ticks = lease_ticks;
    return true;
}

void bosch_chery_torque_set_generation(BoschCheryTorqueRx *rx, uint32_t generation) {
    if (rx != NULL && (!rx->have_can_generation || rx->can_generation != generation)) {
        *rx = (BoschCheryTorqueRx){
            .lease_ticks = rx->lease_ticks,
            .can_generation = generation,
            .have_can_generation = true,
        };
    }
}

BoschCheryTorqueSample bosch_chery_torque_snapshot(BoschCheryTorqueRx *rx,
        uint32_t now, bool upstream_permit) {
    if (rx == NULL) {
        return (BoschCheryTorqueSample){0};
    }
    if (!upstream_permit || rx->lease_ticks == 0 ||
        (rx->synchronized && now - rx->last_qualified_tick >= rx->lease_ticks)) {
        revoke(rx);
    }
    if (!upstream_permit) {
        /* Reject backlog captured before the observed permit withdrawal. */
        rx->order_floor_tick = now;
        rx->have_order_floor = true;
    } else if (rx->have_order_floor && now - rx->order_floor_tick >= rx->lease_ticks) {
        rx->have_order_floor = false;
    }
    return rx->sample;
}

static BoschCheryTorqueResult receive(BoschCheryTorqueRx *rx, const BoschCheryTorqueFrame *frame,
        uint32_t captured_at, uint32_t now, bool upstream_permit, bool capture_is_current) {
    (void)bosch_chery_torque_snapshot(rx, now, upstream_permit);
    if (frame == NULL || frame->id != BOSCH_CHERY_TORQUE_CAN_ID) {
        return BOSCH_CHERY_TORQUE_IGNORED;
    }
    if (rx == NULL || !upstream_permit || rx->lease_ticks == 0) {
        return BOSCH_CHERY_TORQUE_BLOCKED;
    }
    const uint32_t age = now - captured_at;
    if (!capture_is_current || age >= rx->lease_ticks ||
        (rx->have_order_floor && age > now - rx->order_floor_tick)) {
        return BOSCH_CHERY_TORQUE_STALE;
    }
    rx->order_floor_tick = captured_at;
    rx->have_order_floor = true;
    if (frame->extended || frame->remote || frame->fd || frame->lost || frame->dlc != 8) {
        revoke(rx);
        return BOSCH_CHERY_TORQUE_MALFORMED;
    }

    const uint8_t *data = frame->payload;
    const bool active = (data[2] & 1u) != 0;
    const bool had_sequence = rx->synchronized;
    CheryRequestQualification *qualification = &rx->qualification;
    qualification->raw_8173 = data[1];
    qualification->raw_8172 = data[4];
    qualification->checksum_8168 = (uint8_t)(((data[3] & 15u) << 4) | (data[0] & 15u));
    qualification->sequence_8166 = (uint8_t)((data[2] >> 4) & 7u);
    qualification->flags_08 = active && had_sequence ? UINT16_C(0x2000) : 0;
    (void)chery_request_qualification_reference(qualification);

    clear_sample(rx);
    if (!active) {
        revoke(rx);
        return BOSCH_CHERY_TORQUE_INACTIVE;
    }
    if ((qualification->flags_8182 & 3u) != 0) {
        return BOSCH_CHERY_TORQUE_UNQUALIFIED;
    }
    rx->last_qualified_tick = captured_at;
    rx->synchronized = true;
    if (!had_sequence) {
        return BOSCH_CHERY_TORQUE_SYNCHRONIZING;
    }

    if (!(qualification->flags_8182 & 8u)) {
        rx->sample.operand_byte1 = signed_word(qualification->request_8c86);
        rx->sample.valid_channels |= BOSCH_CHERY_TORQUE_BYTE1;
    }
    if (!(qualification->flags_8182 & 16u)) {
        rx->sample.operand_byte4 = signed_word(qualification->request_8c84);
        rx->sample.valid_channels |= BOSCH_CHERY_TORQUE_BYTE4;
    }
    return rx->sample.valid_channels != 0 ? BOSCH_CHERY_TORQUE_ACCEPTED :
                                          BOSCH_CHERY_TORQUE_UNQUALIFIED;
}

BoschCheryTorqueResult bosch_chery_torque_receive(BoschCheryTorqueRx *rx,
        const BoschCheryTorqueFrame *frame, uint32_t now, bool upstream_permit) {
    return receive(rx, frame, now, now, upstream_permit, true);
}

BoschCheryTorqueResult bosch_chery_torque_receive_captured(BoschCheryTorqueRx *rx,
        const BoschCheryTorqueFrame *frame, uint32_t captured_at, uint32_t now, bool upstream_permit) {
    return receive(rx, frame, captured_at, now, upstream_permit, true);
}

BoschCheryTorqueResult bosch_chery_torque_receive_queued(BoschCheryTorqueRx *rx,
        const BoschCheryTorqueFrame *frame, BoschCheryTorqueCapture capture, uint32_t now,
        bool upstream_permit) {
    const bool current = rx != NULL && rx->have_can_generation &&
                         capture.generation == rx->can_generation;
    return receive(rx, frame, capture.tick, now, upstream_permit, current);
}

bool bosch_chery_torque_lookup_q8(BoschCheryTorqueRx *rx, uint32_t now,
        bool upstream_permit, const BoschCheryTorqueCalibration *points, size_t point_count,
        uint32_t operating_point, uint8_t *reduction_q8) {
    const BoschCheryTorqueSample sample = bosch_chery_torque_snapshot(rx, now, upstream_permit);
    if (reduction_q8 == NULL) {
        return false;
    }
    *reduction_q8 = 0;
    if (points == NULL || sample.valid_channels != BOSCH_CHERY_TORQUE_BOTH) {
        return false;
    }

    const BoschCheryTorqueCalibration *match = NULL;
    for (size_t index = 0; index < point_count; ++index) {
        const BoschCheryTorqueCalibration *point = &points[index];
        if (point->operating_point != operating_point || point->operand_byte1 != sample.operand_byte1 ||
            point->operand_byte4 != sample.operand_byte4) {
            continue;
        }
        if (match != NULL || point->reduction_q8 == 0 ||
            point->reduction_q8 > BOSCH_E4M3_Q8_MAX_REDUCTION) {
            return false;
        }
        match = point;
    }
    if (match == NULL) {
        return false;
    }
    *reduction_q8 = match->reduction_q8;
    return true;
}
