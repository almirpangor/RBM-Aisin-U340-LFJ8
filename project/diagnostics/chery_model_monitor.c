#include "chery_model_monitor.h"

enum {
    DTC_MODEL_NOW = 0x12,
    DTC_MODEL_LIMIT = 0x10,
    DEFAULT_MODEL_CODE = 50,
    FAULT_THRESHOLD = 100,
    RESTORE_THRESHOLD = 250
};

typedef enum { HOLD, COUNTING_FAULT, RAISED, GOOD, RESTORED } SampleResult;

void chery_model_monitor_init(CheryModelMonitor *monitor)
{
    *monitor = (CheryModelMonitor){.now_code = DEFAULT_MODEL_CODE, .limit_code = DEFAULT_MODEL_CODE};
}

static SampleResult qualify(CheryDtcState *dtc, uint8_t index, uint8_t *count,
                            uint8_t raw, bool check_fault, bool inhibit_history)
{
    bool latched = (dtc->current[index / 8u] & (1u << (index % 8u))) != 0u;
    if (raw == UINT8_MAX) {
        if (!check_fault) {
            return HOLD;
        }
        if (latched) {
            *count = 0;
            return HOLD;
        }
        if (*count <= FAULT_THRESHOLD) {
            ++*count;
            return COUNTING_FAULT;
        }
        *count = 0;
        chery_dtc_raise_c0(dtc, index, inhibit_history);
        return RAISED;
    }

    if (latched && *count <= RESTORE_THRESHOLD) {
        ++*count;
        return HOLD;
    }
    *count = 0;
    if (latched) {
        chery_dtc_set_current(dtc, index, false);
        return RESTORED;
    }
    return GOOD;
}

void chery_model_monitor_task2(CheryModelMonitor *monitor, CheryDtcState *dtc,
                               const Ta2005CherySnapshot *engine,
                               const CheryModelContext *context)
{
    /* E02B.7/.2 exit both windows. The active RPM DTC in E02A.5 admits
     * invalid-field monitoring even in F83B.0 mode. */
    if ((dtc->current[3] & 0x84u) != 0u) {
        monitor->now_failed = true;
        return;
    }
    bool check_fault = !context->mode_f83b_0 || (dtc->current[2] & 0x20u) != 0u;
    SampleResult now = qualify(dtc, DTC_MODEL_NOW, &monitor->now_count, engine->model.f9d8,
                               check_fault, context->inhibit_history_fd00_5);
    if (now == RAISED) {
        monitor->now_failed = true;
    } else if (now == GOOD || now == RESTORED) {
        bool use_default = now == GOOD && (context->engine_flags_e026 & 6u) == 0u &&
                           context->check_low_speed_fd1c_11 && (context->engine_speed_fa62 >> 8) < 12u;
        monitor->now_code = use_default ? DEFAULT_MODEL_CODE : engine->model.f9d8;
        monitor->now_failed = false;
    }

    /* Stored S03 calibration 3356.6 enables this independent monitor. */
    SampleResult limit = qualify(dtc, DTC_MODEL_LIMIT, &monitor->limit_count, engine->model.f914,
                                 check_fault, context->inhibit_history_fd00_5);
    if (limit == COUNTING_FAULT) {
        monitor->limit_pending = true;
    } else if (limit == RAISED || limit == GOOD) {
        monitor->limit_pending = false;
    }
    if (limit == GOOD || limit == RESTORED) {
        monitor->limit_code = engine->model.f914;
    }
}
