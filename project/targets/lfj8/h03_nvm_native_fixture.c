/* Run only in the M32R simulator, where the array and SFRs are RAM. */
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_nvm_native.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>

#define REG8(address) (*(volatile uint8_t *)(uintptr_t)(address))
#define REG16(address) (*(volatile uint16_t *)(uintptr_t)(address))

enum { FMOD = 0x8007E0, FSTAT = 0x8007E1, FCNT1 = 0x8007E2 };
enum { FIRST = 0x006000, SECOND = 0x020000, SLOT_BYTES = 34, PUBLISHED = 30, RETIRED = 32 };

static const uint8_t test_blocks[2] = {4, 7};

#define RBM_H03_PROFILE_ADAPTATION_BLOCKS test_blocks
#include "lfj8_h03_toyota_nvm_profile.h"

Lfj8H03CycleWorkspace rbm_h03_cycle_workspace;

_Static_assert(sizeof(Lfj8H03CycleWorkspace) == sizeof(union { FactoryGearState gear; FactoryHydraulics gp; }),
               "Adaptation snapshots must fit the existing workspace");

static void seed_slot(uint32_t address, const CheryDtcState *source, uint32_t generation)
{
    uint8_t slot[SLOT_BYTES];
    memset(slot, UINT8_MAX, sizeof slot);
    assert(chery_dtc_journal_encode(source, generation, slot));
    slot[PUBLISHED] = slot[PUBLISHED + 1] = 0u;
    for (unsigned i = 0; i < sizeof slot; ++i) {
        REG8(address + i) = slot[i];
    }
}

static void erase_slot_in_simulator(uint32_t address)
{
    for (unsigned i = 0; i < SLOT_BYTES; ++i) {
        REG8(address + i) = UINT8_MAX;
    }
}

static unsigned irq_enabled(void)
{
    uint32_t psw;
    __asm__ volatile ("mvfc %0,psw" : "=r"(psw));
    return (psw & 0x40u) != 0u;
}

static void expect_restore(const uint8_t blocks[2], Lfj8H03NvmResult result,
                           const CheryDtcState *expected, const CheryDtcState *dirty)
{
    CheryDtcState restored = *dirty;
    restored.clear_pending = true;
    const unsigned ie = irq_enabled();
    assert(lfj8_h03_nvm_native_restore_dtc(blocks, &restored) == result);
    assert(irq_enabled() == ie && !restored.clear_pending);
    const uint8_t no_current[CHERY_DTC_BITMAP_BYTES] = {0};
    assert(memcmp(restored.current, no_current, sizeof no_current) == 0);
    assert(memcmp(restored.history, expected->history, sizeof restored.history) == 0);
    assert(memcmp(restored.snapshot_index, expected->snapshot_index, sizeof restored.snapshot_index) == 0);
}

static void seed_adaptation(uint32_t address, const FactoryAdaptation *data, uint32_t generation)
{
    uint8_t record[FACTORY_ADAPT_RECORD_BYTES];
    assert(factory_adaptation_encode(record, data, generation));
    for (unsigned i = 0; i < sizeof record; ++i) {
        REG8(address + i) = record[i];
    }
}

static void check_adaptation(void)
{
    const FactoryAdaptation *const baseline = rbm_u340e_s01_adaptation_baseline();
    const FactoryAdaptation saved = {.down = {-40, 40}, .down_seen = 1u};
    static FactoryGearState gear;
    static FactoryHydraulics gp;
    static RbmU340eRuntime runtime;
    assert(factory_hydraulics_set(&gp, 1492, 2u, 0x5a5au));
    const RbmU340eStartupSeed seed = {
        .gear = &gear, .gp = &gp,
        .cold_work = &rbm_h03_cycle_workspace.gear,
        .kind = RBM_U340E_STARTUP_S01_COLD,
        .read_adaptation = RBM_H03_PROFILE_READ_ADAPTATION,
    };

    seed_adaptation(FIRST, baseline, UINT32_MAX);
    seed_adaptation(SECOND, &saved, 0u);
    const unsigned ie = irq_enabled();
    const uint8_t *const first = seed.read_adaptation(NULL, 0u);
    REG8(SECOND) ^= 1u;
    const uint8_t *const second = seed.read_adaptation(NULL, 1u);
    FactoryAdaptation decoded;
    uint32_t generation;
    assert(first && second && first != second && irq_enabled() == ie);
    assert(factory_adaptation_decode(first, &decoded, &generation) && generation == UINT32_MAX);
    assert(factory_adaptation_decode(second, &decoded, &generation) && generation == 0u);
    assert(!seed.read_adaptation(NULL, 1u) && !seed.read_adaptation(NULL, 2u));
    REG8(SECOND) ^= 1u;

    assert(rbm_u340e_runtime_start_from_seed(&runtime, &seed) == RBM_U340E_ADAPTATION_LOADED);
    uint32_t fast_filter;
    assert(factory_hydraulics_get(&runtime.gp, 1492, 2u, &fast_filter) && fast_filter == 0u);
    factory_hydraulics_capture(&runtime.gp, &decoded);
    assert(decoded.down_seen == saved.down_seen && decoded.down[0] == saved.down[0]);
    assert(irq_enabled() == ie);

    /* A subsequent start must never use the pair captured by an earlier start. */
    REG8(FCNT1) = 1u;
    assert(rbm_u340e_runtime_start_from_seed(&runtime, &seed) == RBM_U340E_ADAPTATION_BASELINE_UNTRUSTED);
    assert(!seed.read_adaptation(NULL, 1u) && REG8(FCNT1) == 1u && irq_enabled() == ie);
    REG8(FCNT1) = 0u;
    REG16(0x8007F0) = 0x8000u;
    assert(!seed.read_adaptation(NULL, 0u) && !seed.read_adaptation(NULL, 1u));
    assert(REG16(0x8007F0) == 0x8000u);
    REG16(0x8007F0) = 0u;

    uint8_t (*const slots)[FACTORY_ADAPT_RECORD_BYTES] = rbm_h03_cycle_workspace.adaptation.slots;
    const uint8_t duplicate[] = {4, 4};
    const uint8_t out_of_range[] = {4, LFJ8_H03_NVM_BLOCK_COUNT};
    assert(!lfj8_h03_nvm_native_read_adaptation(duplicate, slots));
    assert(!lfj8_h03_nvm_native_read_adaptation(out_of_range, slots));
    assert(!lfj8_h03_nvm_native_read_adaptation(NULL, slots));
    assert(!lfj8_h03_nvm_native_read_adaptation(test_blocks, NULL));
    puts("PASS native H03 array: TOY-05 startup pair, wrap, unavailable array and invalid ownership input");
}

int main(void)
{
    CheryDtcState empty, learned;
    chery_dtc_init(&empty);
    chery_dtc_init(&learned);
    assert(chery_dtc_raise_c0(&learned, 0x14u, false));
    REG8(FMOD) = 0x10u;
    REG8(FSTAT) = 0x80u;
    REG8(FCNT1) = 0u;

    const uint32_t saved = lfj8_h03_mmio.enter(lfj8_h03_mmio.context);
    erase_slot_in_simulator(FIRST);
    erase_slot_in_simulator(SECOND);
    expect_restore(test_blocks, LFJ8_H03_NVM_EMPTY, &empty, &learned);
    seed_slot(FIRST, &learned, UINT32_MAX);
    expect_restore(test_blocks, LFJ8_H03_NVM_SLOT_0, &learned, &learned);

    seed_slot(SECOND, &empty, 0u);
    expect_restore(test_blocks, LFJ8_H03_NVM_SLOT_1, &empty, &learned);
    REG8(SECOND + 10) ^= 1u;
    expect_restore(test_blocks, LFJ8_H03_NVM_CORRUPT, &empty, &learned);
    REG8(FIRST + RETIRED + 1) = 0x7Fu;
    erase_slot_in_simulator(SECOND);
    expect_restore(test_blocks, LFJ8_H03_NVM_EMPTY, &empty, &learned);

    seed_slot(SECOND, &learned, 0u);
    /* FP high does not prohibit reading. Reserved FSTAT bits are ignored. */
    REG8(FMOD) = 0x11u;
    REG8(FSTAT) = 0x8Fu;
    __asm__ volatile ("setpsw #0x40" : : : "memory", "cc");
    assert(irq_enabled());
    expect_restore(test_blocks, LFJ8_H03_NVM_SLOT_1, &learned, &learned);
    lfj8_h03_mmio.leave(lfj8_h03_mmio.context, saved);
    puts("PASS native H03 array: blank, both slots, rollover, CRC, retirement and IRQ state");

    static const struct { uint8_t mode, status, control; } denied[] = {
        {0x00, 0x80, 0x00}, /* Flash inaccessible */
        {0x10, 0x00, 0x00}, /* FBUSY active */
        {0x10, 0xA0, 0x00}, /* Erase error */
        {0x10, 0x90, 0x00}, /* Program error */
        {0x10, 0x80, 0x10}, /* E/W */
        {0x10, 0x80, 0x01}, /* Virtual Flash */
    };
    for (unsigned i = 0; i < sizeof denied / sizeof denied[0]; ++i) {
        REG8(FMOD) = denied[i].mode;
        REG8(FSTAT) = denied[i].status;
        REG8(FCNT1) = denied[i].control;
        expect_restore(test_blocks, LFJ8_H03_NVM_READ_FAILED, &empty, &learned);
        assert(REG8(FMOD) == denied[i].mode && REG8(FSTAT) == denied[i].status &&
               REG8(FCNT1) == denied[i].control);
    }
    REG8(FMOD) = 0x10u;
    REG8(FSTAT) = 0x80u;
    REG8(FCNT1) = 0u;
    /* Leave a valid published slot in the backing memory. A bank enable
     * alone must prevent its contents from being accepted as physical Flash. */
    static const uint32_t banks[] = {0x8007E8, 0x8007EA, 0x8007F0, 0x8007F2};
    const uint16_t page = 0x0020u;
    const uint16_t enabled = (uint16_t)(0x8000u | page);
    for (unsigned i = 0; i < sizeof banks / sizeof banks[0]; ++i) {
        REG16(banks[i]) = page;
    }
    expect_restore(test_blocks, LFJ8_H03_NVM_SLOT_1, &learned, &learned);
    for (unsigned i = 0; i < sizeof banks / sizeof banks[0]; ++i) {
        REG16(banks[i]) = enabled;
        expect_restore(test_blocks, LFJ8_H03_NVM_READ_FAILED, &empty, &learned);
        assert(REG8(FCNT1) == 0u && REG16(banks[i]) == enabled);
        REG16(banks[i]) = page;
        expect_restore(test_blocks, LFJ8_H03_NVM_SLOT_1, &learned, &learned);
    }

    const uint8_t duplicate[] = {4, 4};
    const uint8_t out_of_range[] = {4, LFJ8_H03_NVM_BLOCK_COUNT};
    expect_restore(NULL, LFJ8_H03_NVM_INVALID, &empty, &learned);
    expect_restore(duplicate, LFJ8_H03_NVM_INVALID, &empty, &learned);
    expect_restore(out_of_range, LFJ8_H03_NVM_INVALID, &empty, &learned);
    assert(lfj8_h03_nvm_native_restore_dtc(test_blocks, NULL) == LFJ8_H03_NVM_INVALID);
    expect_restore(test_blocks, LFJ8_H03_NVM_SLOT_1, &learned, &learned);
    puts("PASS native H03 array: inaccessible, busy, erase/program error, E/W, Virtual Flash bank enable with FCNT1 clear, invalid blocks");
    check_adaptation();
    return 0;
}
