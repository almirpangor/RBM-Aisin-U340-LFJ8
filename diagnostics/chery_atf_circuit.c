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

void chery_atf_circuit_step_qualified(CheryAtfCircuit *monitor, CheryDtcState *dtc,
                                      CheryAtfCircuitQualifiedSample sample,
                                      bool inhibit_history)
{
    CheryAtfCircuitSample accepted = CHERY_ATF_CIRCUIT_SKIPPED;

    if (sample.qualified &&
        sample.max_age < UINT32_C(0x80000000) &&
        sample.now - sample.sampled_at <= sample.max_age) {
        accepted = sample.sample;
        if (accepted != CHERY_ATF_CIRCUIT_IN_RANGE &&
            accepted != CHERY_ATF_CIRCUIT_OUT_OF_RANGE &&
            accepted != CHERY_ATF_CIRCUIT_SKIPPED) {
            accepted = CHERY_ATF_CIRCUIT_SKIPPED;
        }
    }

    chery_atf_circuit_step(monitor, dtc, accepted, inhibit_history);
}
