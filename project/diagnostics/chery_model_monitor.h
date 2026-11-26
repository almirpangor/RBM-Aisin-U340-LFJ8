#ifndef RBM_CHERY_MODEL_MONITOR_H
#define RBM_CHERY_MODEL_MONITOR_H

#include "chery_dtc.h"
#include "ta2005_chery_inputs.h"

typedef struct {
    uint8_t now_code;       /* F9C4 */
    uint8_t limit_code;     /* F9F3 */
    uint8_t now_count;      /* E016 */
    uint8_t limit_count;    /* E018 */
    bool now_failed;        /* E027.0 */
    bool limit_pending;     /* FD14.1 */
} CheryModelMonitor;

typedef struct {
    uint16_t engine_speed_fa62;
    uint8_t engine_flags_e026;
    bool check_low_speed_fd1c_11;
    bool mode_f83b_0;
    bool inhibit_history_fd00_5;
} CheryModelContext;

void chery_model_monitor_init(CheryModelMonitor *monitor);

/* Dispatch once per normal C0 task 2 release, after RPM qualification. Use
 * the current CAN snapshot (expired fields carry FF) and the common DTC
 * store shared with the scanner. Serialize with DTC clear/read. The codes
 * are qualified TA2005 model operands, not hydraulic or torque commands. */
void chery_model_monitor_task2(CheryModelMonitor *monitor, CheryDtcState *dtc,
                               const Ta2005CherySnapshot *engine,
                               const CheryModelContext *context);

#endif
