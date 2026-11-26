#include "lfj8_h03_can_monitor_startup.h"
#include "lfj8_h03_application.h"
#include "lfj8_h03_can_owner.h"
#include "lfj8_h03_dtc_native.h"

#define H03_FCNT1 UINT32_C(0x8007E2)
#define H03_FELBANK0 UINT32_C(0x8007E8)
#define H03_FELBANK1 UINT32_C(0x8007EA)
#define H03_FESBANK0 UINT32_C(0x8007F0)
#define H03_FESBANK1 UINT32_C(0x8007F2)
#define H03_SERVICE_MODE UINT32_C(0x804887)
#define H03_PROGRAMMING_GATE UINT32_C(0x80801C)

/* Link to the existing fast_output field of the communication storage. */
extern Lfj8H03FastOutput rbm_h03_fast_output;

int rbm_h03_can_monitor_cold_owner_init_locked(void)
{
    const Lfj8H03ApplicationBinding *const app = &rbm_h03_application_binding;
    if (!app->ram_owned || app->ram_owned(app->takeover_ops->io->context) != 1) {
        return 0;
    }
    /* Cold ownership covers both the CAN owner and the resident IRQ pointer. */
    lfj8_h03_dtc_native_cold_init();
    return 1;
}

void rbm_h03_can_monitor_revoke_locked(void)
{
    const Lfj8H03ApplicationBinding *const app = &rbm_h03_application_binding;
    const Lfj8H03TakeoverOps *const ops = app->takeover_ops;
    const Lfj8RegisterIo *const io = ops->io;
    void *const context = io->context;

    /* The RAM owner must remain valid while CAN is parked. Never use
     * retained application state as evidence that we own its storage. */
    if (app->ram_owned(context) != 1) {
        return;
    }

    /* A failed setup must leave this generation revoked. */
    h03_can_owner.setup_permitted = false;
    h03_can_owner.grant = 0u;
    app->main->valid = 0u;
    rbm_h03_fast_output.valid = 0u;

    Lfj8H03Takeover *const takeover = app->takeover;
    if (rbm_h03_application.running != 1u || takeover->ops != ops ||
        !ops->inhibit || io->read8(context, H03_FCNT1) != 0u ||
        io->read8(context, H03_SERVICE_MODE) == 4u ||
        io->read8(context, H03_PROGRAMMING_GATE) != 0u) {
        /* Shut off later prepare/apply calls as well. Reentry requires the
         * normal application initializer. A service owner must already have
         * fenced the physical outputs before acquiring the actuator I/O. */
        rbm_h03_application.running = 0u;
        takeover->ops = 0;
        takeover->pending = 0u;
        return;
    }
    lfj8_h03_takeover_revoke_locked(takeover);
}

void rbm_h03_can_monitor_publish_setup_locked(void)
{
    const Lfj8H03ApplicationBinding *const app = &rbm_h03_application_binding;
    const Lfj8RegisterIo *const io = app->takeover_ops->io;
    if (app->ram_owned(io->context) == 1 && h03_can_owner.initialized && h03_can_owner.grant == 0u) {
        ++h03_can_owner.setup_generation;
        h03_can_owner.setup_permitted = true;
        if (h03_can_owner.tx13_fenced && lfj8_h03_can0_epoch_drained(io)) {
            h03_can_owner.tx13_fenced = 0u;
        }
    }
}

void rbm_h03_can_monitor_retire_tx13_locked(void)
{
    if (!h03_can_owner.tx13_fenced || h03_can_owner.grant) {
        return;
    }
    const Lfj8RegisterIo *const io = rbm_h03_application_binding.takeover_ops->io;
    void *const context = io->context;
    if (io->read8(context, H03_FCNT1) == 0u &&
        io->read8(context, H03_SERVICE_MODE) != 4u &&
        io->read8(context, H03_PROGRAMMING_GATE) == 0u &&
        !((io->read16(context, H03_FELBANK0) | io->read16(context, H03_FELBANK1) |
           io->read16(context, H03_FESBANK0) | io->read16(context, H03_FESBANK1)) & 0x8000u) &&
        lfj8_h03_can0_retire_tx13_locked(io)) {
        h03_can_owner.tx13_fenced = 0u;
    }
}
