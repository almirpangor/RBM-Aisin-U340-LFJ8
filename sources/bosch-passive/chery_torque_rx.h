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
    BOSCH_CHERY_TORQUE_STALE,
} BoschCheryTorqueResult;

typedef struct {
    int16_t operand_byte1;
    int16_t operand_byte4;
    uint8_t valid_channels;
} BoschCheryTorqueSample;

typedef struct {
    uint32_t tick;
    uint32_t generation;
} BoschCheryTorqueCapture;

typedef struct {
    CheryRequestQualification qualification;
    BoschCheryTorqueSample sample;
    uint32_t lease_ticks;
    uint32_t last_qualified_tick;
    uint32_t order_floor_tick;
    uint32_t can_generation;
    bool synchronized;
    bool have_order_floor;
    bool have_can_generation;
    bool order_floor_exclusive;
} BoschCheryTorqueRx;

typedef struct {
    uint32_t operating_point;
    int16_t operand_byte1;
    int16_t operand_byte4;
    uint8_t reduction_q8;
} BoschCheryTorqueCalibration;

/* Serialize all operations on an instance, including generation updates.
 * Set a measured lease (1..INT32_MAX) in the same wrapping tick units as now.
 * upstream_permit covers bus health, engine readiness and all external gates.
 * A withdrawal excludes captures at or before that tick in the same
 * generation. Only later captures can start a new sequence.
 */
bool bosch_chery_torque_init(BoschCheryTorqueRx *rx, uint32_t lease_ticks);
/* Immediate delivery: capture and service occur at the same tick. */
BoschCheryTorqueResult bosch_chery_torque_receive(BoschCheryTorqueRx *rx,
    const BoschCheryTorqueFrame *frame, uint32_t now, bool upstream_permit);
/* Use this entry when the caller has already checked that the capture
 * belongs to the current generation. An operand expires one lease after
 * capture, so pass the original capture tick. */
BoschCheryTorqueResult bosch_chery_torque_receive_captured(BoschCheryTorqueRx *rx,
    const BoschCheryTorqueFrame *frame, uint32_t captured_at, uint32_t now, bool upstream_permit);

/* Set the active generation from the CAN/clock owner before servicing its
 * queue or exposing a snapshot. Establishing or changing it clears the
 * sequence, operands and capture order, while the configured lease is kept.
 * Repeating the current generation is idempotent. */
void bosch_chery_torque_set_generation(BoschCheryTorqueRx *rx, uint32_t generation);

/* Pass the tick and generation recorded with the frame by the producer.
 * The consumer supplies now in the current generation and orders captures
 * with equal ticks. A frame cannot establish or change the active generation. */
BoschCheryTorqueResult bosch_chery_torque_receive_queued(BoschCheryTorqueRx *rx,
    const BoschCheryTorqueFrame *frame, BoschCheryTorqueCapture capture, uint32_t now,
    bool upstream_permit);
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
