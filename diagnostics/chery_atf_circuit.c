#include "chery_atf_circuit.h"

enum {
    DTC_ATF_CIRCUIT = 0x04,
    FAULT_SAMPLES = 127,
    RECOVERY_COUNT = 125
};

void chery_atf_circuit_reset(CheryAtfCircuit *monitor)
{
    monitor->count = 0;
}

void chery_atf_circuit_step(CheryAtfCircuit *monitor, CheryDtcState *dtc,
                            CheryAtfCircuitSample sample, bool inhibit_history)
{
    bool active = (dtc->current[0] & (1u << DTC_ATF_CIRCUIT)) != 0u;

    switch (sample) {
    case CHERY_ATF_CIRCUIT_OUT_OF_RANGE:
        if (active || monitor->count >= FAULT_SAMPLES - 1u) {
            monitor->count = RECOVERY_COUNT;
            chery_dtc_raise_c0(dtc, DTC_ATF_CIRCUIT, inhibit_history);
        } else {
            ++monitor->count;
        }
        break;
    case CHERY_ATF_CIRCUIT_IN_RANGE:
        if (active && monitor->count != 0u) {
            --monitor->count;
        } else {
            monitor->count = 0;
            chery_dtc_set_current(dtc, DTC_ATF_CIRCUIT, false);
        }
        break;
    case CHERY_ATF_CIRCUIT_SKIPPED:
        break;
    }
}
