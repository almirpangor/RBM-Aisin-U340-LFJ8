#include "bench_engine_profile.h"
#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_sensor_target.h"

enum {
    H03_CAN0CONF = 0x801006,
    H03_CAN0BRP = 0x801016,
    H03_STOCK_CAN0CONF = 0x95a0,
    H03_STOCK_CAN0BRP = 4,
    H03_FCNT1 = 0x8007e2,
    H03_SERVICE_MODE = 0x804887,
    H03_PROGRAMMING_GATE = 0x80801c,
    H03_SERVICE_ACTIVE = 4,
};

int rbm_h03_engine_context_for_task2(void *context, const Lfj8H03SensorSnapshot *sensors,
    Ta2005EngineQualificationContext *engine, bool *inhibit_history, uint32_t *oldest_us)
{
    (void)context;
    uint32_t now;
    const Lfj8RegisterIo *const io = &lfj8_h03_mmio;
    if (!sensors || !engine || !inhibit_history || !oldest_us ||
        !rbm_h03_atf_now_us(&now) || sensors->epoch != rbm_h03_sensor_state.feed.epoch ||
        now - sensors->capture.now_tml0 >= RBM_H03_PROFILE_ENGINE_MAX_POLL_GAP_US ||
        io->read8(io->context, H03_FCNT1) != 0u ||
        io->read8(io->context, H03_SERVICE_MODE) == H03_SERVICE_ACTIVE ||
        io->read8(io->context, H03_PROGRAMMING_GATE) != 0u) {
        return 0;
    }

    const bool can_admitted = h03_can_owner.initialized && h03_can_owner.grant == 1u &&
        h03_can_owner.setup_generation == h03_can_owner.admitted_generation;
    if (can_admitted && (io->read16(io->context, H03_CAN0CONF) != H03_STOCK_CAN0CONF ||
                         io->read8(io->context, H03_CAN0BRP) != H03_STOCK_CAN0BRP)) {
        return 0;
    }

    /* Only FD10.12 and E026.1 are consumed by the Toyota projection;
     * these bits belong to the qualifier. No auxiliary E02B flags are
     * injected. The engine feed combines the shared DTC byte and native
     * ownership/clock faults. CAN is the only ECT source in this profile. */
    *engine = (Ta2005EngineQualificationContext){
        .fallback_fa7b = UINT8_MAX,
        .coolant_can_enabled = (uint8_t)can_admitted,
        .coherent = 1u,
    };
    *inhibit_history = !can_admitted;
    *oldest_us = sensors->capture.now_tml0;
    return 1;
}
