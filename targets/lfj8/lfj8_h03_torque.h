#ifndef RBM_LFJ8_H03_TORQUE_H
#define RBM_LFJ8_H03_TORQUE_H

#include <stdbool.h>
#include <stdint.h>

#include "factory_hydraulic_state.h"

enum { LFJ8_TORQUE_REQUEST_ID = 0x5e8, LFJ8_TORQUE_STATUS_ID = 0x5e9 };

typedef struct {
    uint8_t active;
    uint8_t from_gear;
    uint8_t to_gear;
    uint8_t level;
} Lfj8TorqueDemand;

/* Project a successful, serialized Toyota MAIN output. An active alternate
 * path is reported with zero gear numbers, which blocks request admission. */
bool lfj8_h03_torque_demand(const FactoryHydraulics *gp, Lfj8TorqueDemand *demand);

typedef struct {
    uint8_t levels;       /* Bits 1..7 select independently calibrated levels. */
    uint8_t reduction_q8; /* E4M3 relative reduction range 1..64. */
    uint8_t duration;     /* E4M3 units of 10 ms, range 1..30. */
} Lfj8TorqueProfile;

typedef struct {
    /* In order: 1→2, 2→3, 3→4 and 2→1, 3→2, 4→3. A zero mask disables a pair. */
    Lfj8TorqueProfile up[3];
    Lfj8TorqueProfile down[3];
} Lfj8TorqueCalibration;

typedef struct {
    Lfj8TorqueDemand demand;
    uint32_t captured_at_us;
    uint16_t engine_rpm;
    uint8_t observed_gear; /* Required only on admission. */
    bool permitted;       /* Verified ignition, forward selector, CAN and shift ownership. */
} Lfj8TorqueInput;

typedef enum {
    LFJ8_TORQUE_IDLE,
    LFJ8_TORQUE_WAITING,
    LFJ8_TORQUE_ACTIVE,
    LFJ8_TORQUE_RELEASING,
    LFJ8_TORQUE_COMPLETE,
    LFJ8_TORQUE_FAILED,
} Lfj8TorquePhase;

typedef struct {
    uint32_t started_at;
    uint32_t submitted_at;
    uint32_t last_status_at;
    uint32_t progress_at;
    uint32_t release_at;
    uint16_t status_token;
    uint16_t token;
    uint8_t seq;
    uint8_t ack_seq;
    uint8_t tx_seq;
    uint8_t releases;
    uint8_t first_release_seq;
    uint8_t status_phase;
    uint8_t status_reduction;
    uint8_t phase;
    uint8_t from_gear;
    uint8_t to_gear;
    Lfj8TorqueProfile profile;
    bool armed;
    bool have_status;
    bool have_ack;
    bool full_reduction;
    bool reached_full;
    bool cooling_down;
    bool pending;
    bool failed;
} Lfj8H03Torque;

typedef bool (*Lfj8TorqueSubmit)(void *context, uint16_t id, const uint8_t data[8]);

/* One foreground owner performs all calls. now_us and captured_at_us are in
 * the same wrapping monotonic clock. Process arbitration completion before
 * delivering status, and discard lost, extended or remote frames upstream.
 * Keep callback transmission storage valid until the synchronous submit
 * callback returns. Exactly one completion is required after each accepted
 * submit, including TX abort during controller reset. No queueing by callback
 * before exclusive torque authority and an operational link are established.
 * A NULL input signals unavailable data. A NULL calibration or a zero profile
 * disables requests. Changing the selected profile ends the current pulse.
 * Poll can transmit CANCEL after input or profile loss when TX permits.
 */
void lfj8_h03_torque_init(Lfj8H03Torque *link);
void lfj8_h03_torque_poll(Lfj8H03Torque *link, const Lfj8TorqueInput *input,
                         const Lfj8TorqueCalibration *cal, uint32_t now_us,
                         Lfj8TorqueSubmit submit, void *context);
void lfj8_h03_torque_tx_done(Lfj8H03Torque *link, bool transmitted, uint32_t now_us);
bool lfj8_h03_torque_receive(Lfj8H03Torque *link, uint16_t standard_id, unsigned dlc,
                            const uint8_t *data, uint32_t received_at_us);
bool lfj8_h03_torque_applied(const Lfj8H03Torque *link, uint32_t now_us);

#endif
