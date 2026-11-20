#ifndef RBM_LFJ8_CHERY_TX_H
#define RBM_LFJ8_CHERY_TX_H

#include "lfj8_bridge.h"
#include "lfj8_donor_io.h"

typedef struct {
    Lfj8CherySchedule schedule;
    uint8_t pending;
    uint8_t last_submitted;
    uint8_t counter_f8e4;
} Lfj8CheryTx;

typedef struct {
    uint32_t tick_hz;
    uint32_t vss_timeout_ticks;
    uint32_t wheel_um;
    uint16_t wheel_num;
    uint16_t wheel_den;
} Lfj8VehicleCalibration;

typedef struct {
    Lfj8Chery1ae status_1ae;
    uint8_t status0_300;
    uint8_t status1_300;
    uint8_t flag_fd18_9;
    int16_t atf_c;
    uint8_t atf_valid;
    uint8_t stopped; /* Exactly 1 for independently confirmed standstill at this poll. */
} Lfj8CheryTxInputs;

void lfj8_chery_tx_init(Lfj8CheryTx *tx, uint32_t now_us, uint32_t period_1ae_us,
                       uint32_t period_300_us);

/* Reports the driver's result and sets submitted to the admitted due-mask bit
 * or zero. Returns LFJ8_CAN_READY when no frame is due. */
Lfj8CanResult lfj8_chery_tx_poll_status(Lfj8CheryTx *tx, const Lfj8RegisterIo *io,
                                       uint32_t now_us, uint8_t slot13_owned,
                                       volatile Lfj8RawVss *vss, const Lfj8VehicleCalibration *cal,
                                       const Lfj8CheryTxInputs *inputs, uint8_t *submitted);

/* Returns a due-mask bit once a request has been accepted by slot 13, or zero. */
uint8_t lfj8_chery_tx_poll(Lfj8CheryTx *tx, const Lfj8RegisterIo *io, uint32_t now_us,
                          uint8_t slot13_owned, volatile Lfj8RawVss *vss,
                          const Lfj8VehicleCalibration *cal,
                          const Lfj8CheryTxInputs *inputs);

#endif
