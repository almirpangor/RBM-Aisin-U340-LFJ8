#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "lfj8_h03_application_binding.h"
#include "lfj8_h03_mmio.h"
#include "chery_dtc.h"

int rbm_h03_bench_prepare_startup_inputs(void *context);

CheryDtcState rbm_h03_dtc_state;
Lfj8H03Application rbm_h03_application;

static unsigned lock_depth;
static unsigned cold_checks;
static unsigned admission;
static unsigned ram_ok = 1u;
static unsigned clock_ok = 1u;

static uint32_t lock_enter(void *context)
{
    assert(context == NULL);
    return lock_depth++;
}

static void lock_leave(void *context, uint32_t saved)
{
    assert(context == NULL && lock_depth == saved + 1u);
    lock_depth = saved;
}

const Lfj8RegisterIo lfj8_h03_mmio = {
    .enter = lock_enter,
    .leave = lock_leave,
};

int rbm_h03_target_ram_owned(void *context)
{
    assert(context == NULL && lock_depth == 1u);
    return ram_ok;
}

int rbm_h03_target_clock_ready(void *context)
{
    assert(context == NULL && lock_depth == 1u);
    return clock_ok;
}

int rbm_h03_bench_consume_cold_admission_locked(void *context)
{
    assert(context == NULL && lock_depth == 1u);
    ++cold_checks;
    const unsigned current = admission;
    admission = 0u;
    return current;
}

void __init(void) {}
void __fini(void) {}

int main(void)
{
    CheryDtcState before;
    memset(&before, 0x5a, sizeof before);
    memcpy(&rbm_h03_dtc_state, &before, sizeof before);

    assert(rbm_h03_bench_prepare_startup_inputs(&before) == RBM_U340E_STARTUP_UNQUALIFIED);
    ram_ok = 0u;
    assert(rbm_h03_bench_prepare_startup_inputs(NULL) == RBM_U340E_STARTUP_UNQUALIFIED);
    ram_ok = 1u;
    clock_ok = 0u;
    assert(rbm_h03_bench_prepare_startup_inputs(NULL) == RBM_U340E_STARTUP_UNQUALIFIED);
    clock_ok = 1u;
    rbm_h03_application.running = 1u;
    assert(rbm_h03_bench_prepare_startup_inputs(NULL) == RBM_U340E_STARTUP_UNQUALIFIED);
    rbm_h03_application.running = 0u;
    assert(lock_depth == 0u && cold_checks == 0u);
    assert(rbm_h03_bench_prepare_startup_inputs(NULL) == RBM_U340E_STARTUP_UNQUALIFIED);
    assert(memcmp(&before, &rbm_h03_dtc_state, sizeof before) == 0);

    admission = 1u;
    const int kind = rbm_h03_bench_prepare_startup_inputs(NULL);
    assert(kind == RBM_U340E_STARTUP_S01_COLD && lock_depth == 0u && cold_checks == 2u);
    CheryDtcState empty_dtc;
    chery_dtc_init(&empty_dtc);
    assert(memcmp(&empty_dtc, &rbm_h03_dtc_state, sizeof empty_dtc) == 0);

    RbmU340eRuntime runtime;
    FactoryGearState cold_work;
    memset(&runtime, 0xa7, sizeof runtime);
    memset(&cold_work, 0x34, sizeof cold_work);
    const RbmU340eStartupSeed seed = {
        .gear = &rbm_h03_target_startup_gear,
        .gp = &rbm_h03_target_startup_gp,
        .cold_work = &cold_work,
        .kind = (RbmU340eStartupKind)kind,
    };
    const RbmU340eAdaptationResult status = rbm_u340e_runtime_start_from_seed(&runtime, &seed);
    assert(status == RBM_U340E_ADAPTATION_BASELINE_UNTRUSTED && runtime.initialized == 1u);
    for (unsigned i = 0; i < 6u; ++i) {
        assert(cold_work.periods[i] == UINT16_MAX);
    }
    memcpy(&rbm_h03_dtc_state, &before, sizeof before);
    assert(rbm_h03_bench_prepare_startup_inputs(NULL) == RBM_U340E_STARTUP_UNQUALIFIED);
    assert(memcmp(&before, &rbm_h03_dtc_state, sizeof before) == 0);
    assert(cold_checks == 3u && lock_depth == 0u);
    puts("PASS cold startup: typed read-only seeds, real runtime projection, DTC reset, and refuse gates");
    return 0;
}
