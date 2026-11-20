#ifndef RBM_LFJ8_H03_SENSOR_TARGET_H
#define RBM_LFJ8_H03_SENSOR_TARGET_H

#include "lfj8_h03_sensor_feed.h"

typedef struct {
    Lfj8H03SensorFeed feed;
    volatile Lfj8RawVss s51;
    volatile Lfj8RawCapture s83;
} Lfj8H03SensorTarget;

/* The application allocates one instance and supplies qualified timeouts. */
extern Lfj8H03SensorTarget rbm_h03_sensor_state;
extern const Lfj8H03SensorFeedConfig rbm_h03_sensor_config;

/* The foreground clock owner starts with zeroed state. Call with 0 before
 * changing or restarting either timer and with 1 after independently
 * qualifying both clocks. Each call opens a new epoch and clears prior data.
 * IRQ callbacks and snapshots may revoke on an observed register mismatch. */
int rbm_h03_sensor_clock_rebase(uint8_t physical_1mhz);

void rbm_h03_s51_capture_callback(void);
void rbm_h03_s83_capture_callback(void);

/* Foreground calls after OEM input collection. standstill_confirmed must
 * be an independent observation for this epoch. */
Lfj8H03SensorResult rbm_h03_sensor_foreground(uint8_t standstill_confirmed,
                                             Lfj8H03SensorSnapshot *snapshot);

#endif
