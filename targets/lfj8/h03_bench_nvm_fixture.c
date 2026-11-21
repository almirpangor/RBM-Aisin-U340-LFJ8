/* M32R simulator only: data Flash and SFRs are simulator memory. */
#include "bench_nvm_profile.h"
#include "lfj8_h03_mmio.h"
#include "rbm_u340e_runtime.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>

#define REG8(address) (*(volatile uint8_t *)(uintptr_t)(address))
#define REG16(address) (*(volatile uint16_t *)(uintptr_t)(address))

enum {
    FMOD = 0x8007E0, FSTAT = 0x8007E1, FCNT1 = 0x8007E2,
    FELBANK0 = 0x8007E8, FELBANK1 = 0x8007EA,
    FESBANK0 = 0x8007F0, FESBANK1 = 0x8007F2,
};

static unsigned irq_enabled(void)
{
    uint32_t psw;
    __asm__ volatile ("mvfc %0,psw" : "=r"(psw));
    return psw & 0x40u;
}

static void check_cold_start(void)
{
    static FactoryGearState gear, cold_work;
    static FactoryHydraulics gp;
    static RbmU340eRuntime runtime;
    const RbmU340eStartupSeed seed = {
        .gear = &gear,
        .gp = &gp,
        .cold_work = &cold_work,
        .kind = RBM_U340E_STARTUP_S01_COLD,
        .read_adaptation = RBM_H03_PROFILE_READ_ADAPTATION,
    };
    assert(seed.read_adaptation == NULL);
    assert(rbm_u340e_runtime_start_from_seed(&runtime, &seed) ==
           RBM_U340E_ADAPTATION_BASELINE_UNTRUSTED);
    assert(runtime.initialized == 1u);

    FactoryAdaptation restored;
    factory_hydraulics_capture(&runtime.gp, &restored);
    const FactoryAdaptation *const baseline = rbm_u340e_s01_adaptation_baseline();
    uint8_t actual_record[FACTORY_ADAPT_RECORD_BYTES], baseline_record[FACTORY_ADAPT_RECORD_BYTES];
    assert(factory_adaptation_encode(actual_record, &restored, 0u));
    assert(factory_adaptation_encode(baseline_record, baseline, 0u));
    assert(memcmp(actual_record, baseline_record, sizeof actual_record) == 0);

    CheryDtcState dtc, empty;
    chery_dtc_init(&dtc);
    chery_dtc_init(&empty);
    assert(chery_dtc_raise_c0(&dtc, 0x14u, false));
    dtc.clear_pending = true;
    RBM_H03_BENCH_NVM_DTC_COLD_INIT(&dtc);
    assert(memcmp(dtc.current, empty.current, sizeof dtc.current) == 0);
    assert(memcmp(dtc.history, empty.history, sizeof dtc.history) == 0);
    assert(memcmp(dtc.snapshot_index, empty.snapshot_index, sizeof dtc.snapshot_index) == 0);
    assert(!dtc.clear_pending);
}

static void check_inspection(void)
{
    REG8(FMOD) = 0x11u;
    REG8(FSTAT) = 0x80u;
    REG8(FCNT1) = 0u;
    REG16(FELBANK0) = 0x0010u;
    REG16(FELBANK1) = 0x0011u;
    REG16(FESBANK0) = 0x0020u;
    REG16(FESBANK1) = 0x0021u;

    __asm__ volatile ("setpsw #0x40" : : : "memory", "cc");
    const unsigned ie = irq_enabled();
    assert(ie);
    Lfj8H03NvmBenchStatus status;
    assert(!lfj8_h03_nvm_native_bench_status(NULL));
    assert(lfj8_h03_nvm_native_bench_status(&status) && irq_enabled() == ie);
    assert(status.persistence_status == LFJ8_H03_NVM_BENCH_NO_ASSIGNED_MEDIA);
    assert(status.fmod == 0x11u && status.fstat == 0x80u && status.fcnt1 == 0u);
    assert(status.felbank0 == 0x0010u && status.felbank1 == 0x0011u &&
           status.fesbank0 == 0x0020u && status.fesbank1 == 0x0021u);

    /* Exercise real byte offsets at both ends of the on-chip array. */
    uint8_t count = UINT8_MAX;
    for (unsigned block = 0; block < LFJ8_H03_NVM_BLOCK_COUNT; ++block) {
        Lfj8H03NvmBlock bounds;
        assert(lfj8_h03_nvm_block(block, &bounds));
        const uint16_t chunks = (bounds.end - bounds.first) / LFJ8_H03_NVM_BENCH_SAMPLE_BYTES;
        for (unsigned offset = 0; offset < LFJ8_H03_NVM_BENCH_SAMPLE_BYTES; offset += 2u) {
            REG16(bounds.first + offset) = UINT16_MAX;
            REG16(bounds.end - LFJ8_H03_NVM_BENCH_SAMPLE_BYTES + offset) = UINT16_MAX;
        }
        assert(lfj8_h03_nvm_native_bench_inspect(block, 0, &count) == LFJ8_H03_NVM_INSPECT_OK);
        assert(count == 0u && irq_enabled() == ie);
        REG16(bounds.end - LFJ8_H03_NVM_BENCH_SAMPLE_BYTES) = 0xFF34u;
        REG16(bounds.end - 2u) = 0x12FFu;
        assert(lfj8_h03_nvm_native_bench_inspect(block, chunks - 1u, &count) == LFJ8_H03_NVM_INSPECT_OK);
        assert(count == 2u && irq_enabled() == ie);
        assert(lfj8_h03_nvm_native_bench_inspect(block, chunks, &count) == LFJ8_H03_NVM_INSPECT_INVALID);
        assert(count == 2u);
        assert(REG16(bounds.end - LFJ8_H03_NVM_BENCH_SAMPLE_BYTES) == 0xFF34u &&
               REG16(bounds.end - 2u) == 0x12FFu);
    }
    assert(lfj8_h03_nvm_native_bench_inspect(LFJ8_H03_NVM_BLOCK_COUNT, 0, &count) == LFJ8_H03_NVM_INSPECT_INVALID);
    assert(lfj8_h03_nvm_native_bench_inspect(0, UINT16_MAX, &count) == LFJ8_H03_NVM_INSPECT_INVALID);
    assert(lfj8_h03_nvm_native_bench_inspect(0, 0, NULL) == LFJ8_H03_NVM_INSPECT_INVALID);

    const uint32_t saved = lfj8_h03_mmio.enter(lfj8_h03_mmio.context);
    REG16(FESBANK1) = 0x8021u;
    assert(lfj8_h03_nvm_native_bench_status(&status) && !irq_enabled());
    assert(status.fesbank1 == 0x8021u && status.persistence_status == LFJ8_H03_NVM_BENCH_NO_ASSIGNED_MEDIA);
    assert(lfj8_h03_nvm_native_bench_inspect(0, 0, &count) == LFJ8_H03_NVM_INSPECT_UNAVAILABLE);
    assert(count == 2u && !irq_enabled() && REG16(FESBANK1) == 0x8021u);
    REG16(FESBANK1) = 0x0021u;
    REG8(FSTAT) = 0u;
    assert(lfj8_h03_nvm_native_bench_inspect(0, 0, &count) == LFJ8_H03_NVM_INSPECT_UNAVAILABLE);
    assert(count == 2u && !irq_enabled() && REG8(FSTAT) == 0u);
    lfj8_h03_mmio.leave(lfj8_h03_mmio.context, saved);
    assert(irq_enabled() == ie);
}

int main(void)
{
    check_cold_start();
    puts("PASS H03 no-media bench: S01 adaptation baseline and empty DTC on cold boot");
    check_inspection();
    puts("PASS H03 no-media bench: SFR status, 13 erase boundaries, no writes and IRQ preservation");
    return 0;
}
