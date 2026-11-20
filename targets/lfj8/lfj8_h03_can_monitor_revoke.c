#include "lfj8_h03_can_monitor_startup.h"
#include "lfj8_h03_application.h"
#include "lfj8_h03_can_owner.h"

#define H03_FCNT1 UINT32_C(0x8007E2)
#define H03_SERVICE_MODE UINT32_C(0x804887)
#define H03_PROGRAMMING_GATE UINT32_C(0x80801C)

/* Link to the existing fast_output field of the communication storage. */
extern Lfj8H03FastOutput rbm_h03_fast_output;

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

    /* Do not advance or consume the epoch here. The native setup permits
     * and CAN owner are responsible for announcing and admitting a new one. */
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
