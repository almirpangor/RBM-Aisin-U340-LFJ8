#ifndef RBM_BOSCH_CHERY_TORQUE_RX_H
#define RBM_BOSCH_CHERY_TORQUE_RX_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "chery_request_qualification.h"

enum {
    BOSCH_CHERY_TORQUE_CAN_ID = 0x1AE,
    BOSCH_CHERY_TORQUE_BYTE1 = 1,
    BOSCH_CHERY_TORQUE_BYTE4 = 2,
    BOSCH_CHERY_TORQUE_BOTH = 3,
    BOSCH_E4M3_Q8_MAX_REDUCTION = 64,
};

typedef struct {
    uint32_t id;
    uint8_t dlc;
    bool extended;
    bool remote;
    bool fd;
    bool lost;
    uint8_t payload[8];
} BoschCheryTorqueFrame;

typedef enum {
    BOSCH_CHERY_TORQUE_IGNORED,
    BOSCH_CHERY_TORQUE_BLOCKED,
    BOSCH_CHERY_TORQUE_MALFORMED,
    BOSCH_CHERY_TORQUE_INACTIVE,
    BOSCH_CHERY_TORQUE_UNQUALIFIED,
    BOSCH_CHERY_TORQUE_SYNCHRONIZING,
    BOSCH_CHERY_TORQUE_ACCEPTED,
} BoschCheryTorqueResult;

typedef struct {
    int16_t operand_byte1;
    int16_t operand_byte4;
    uint8_t valid_channels;
} BoschCheryTorqueSample;

typedef struct {
    CheryRequestQualification qualification;
    BoschCheryTorqueSample sample;
    uint32_t lease_ticks;
    uint32_t last_qualified_tick;
    bool synchronized;
} BoschCheryTorqueRx;

typedef struct {
    uint32_t operating_point;
    int16_t operand_byte1;
    int16_t operand_byte4;
    uint8_t reduction_q8;
} BoschCheryTorqueCalibration;

/* Call receive/snapshot/lookup in the same serialized service context. Set a
 * measured lease (1..INT32_MAX) in the same monotonic wrapping tick units as now.
 * upstream_permit covers bus health, engine readiness and all external gates.
 */
bool bosch_chery_torque_init(BoschCheryTorqueRx *rx, uint32_t lease_ticks);
BoschCheryTorqueResult bosch_chery_torque_receive(BoschCheryTorqueRx *rx,
    const BoschCheryTorqueFrame *frame, uint32_t now, bool upstream_permit);
BoschCheryTorqueSample bosch_chery_torque_snapshot(BoschCheryTorqueRx *rx,
    uint32_t now, bool upstream_permit);

/* A lookup requires two fresh operands and one exact match at the caller's
 * verified operating point. No interpolation, built-in map, CAN or ECU writes.
 * The caller owns calibration measurement, attribution and operating-point validity.
 * A failed lookup clears the output. A match does not grant actuator authority.
 */
bool bosch_chery_torque_lookup_q8(BoschCheryTorqueRx *rx, uint32_t now,
    bool upstream_permit, const BoschCheryTorqueCalibration *points, size_t point_count,
    uint32_t operating_point, uint8_t *reduction_q8);

#endif
