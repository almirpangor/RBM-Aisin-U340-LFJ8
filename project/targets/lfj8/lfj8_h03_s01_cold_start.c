#include "lfj8_h03_application_binding.h"
#include "lfj8_h03_mmio.h"
#include "chery_dtc.h"

_Static_assert(sizeof(FactoryGearState) == 360u, "Checked S01 gear ABI");
_Static_assert(sizeof(FactoryHydraulics) == 561u, "Checked S01 GP ABI");

extern CheryDtcState rbm_h03_dtc_state;

/* The H03 boot owner provides this one-shot admission under the native lock.
 * Admit only a proven cold initialization with an independently qualified
 * P/N input. A warm, repeated, unknown or stale initialization must refuse.
 * The admission never supplies physical sensor or communication values. */
extern int rbm_h03_bench_consume_cold_admission_locked(void *context);

int rbm_h03_bench_prepare_startup_inputs(void *context)
{
    const Lfj8RegisterIo *const io = &lfj8_h03_mmio;
    if (context != io->context) {
        return RBM_U340E_STARTUP_UNQUALIFIED;
    }

    const uint32_t saved = io->enter(context);
    const int admitted = rbm_h03_target_ram_owned(context) == 1 &&
                         rbm_h03_target_clock_ready(context) == 1 &&
                         rbm_h03_application.running == 0u &&
                         rbm_h03_bench_consume_cold_admission_locked(context) == 1;
    if (admitted) {
        chery_dtc_init(&rbm_h03_dtc_state);
    }
    io->leave(context, saved);

    return admitted ? RBM_U340E_STARTUP_S01_COLD : RBM_U340E_STARTUP_UNQUALIFIED;
}
