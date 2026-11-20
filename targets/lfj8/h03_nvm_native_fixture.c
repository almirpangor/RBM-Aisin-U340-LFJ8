/* Run only in the M32R simulator, where the array and SFRs are RAM. */
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_nvm_native.h"

#undef NDEBUG
#include <assert.h>
#include <stdio.h>
#include <string.h>

#define REG8(address) (*(volatile uint8_t *)(uintptr_t)(address))

enum { FMOD = 0x8007E0, FSTAT = 0x8007E1, FCNT1 = 0x8007E2 };
enum { FIRST = 0x006000, SECOND = 0x020000, SLOT_BYTES = 34, PUBLISHED = 30, RETIRED = 32 };

static const uint8_t test_blocks[2] = {4, 7};

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
    const uint8_t duplicate[] = {4, 4};
    const uint8_t out_of_range[] = {4, LFJ8_H03_NVM_BLOCK_COUNT};
    expect_restore(NULL, LFJ8_H03_NVM_INVALID, &empty, &learned);
    expect_restore(duplicate, LFJ8_H03_NVM_INVALID, &empty, &learned);
    expect_restore(out_of_range, LFJ8_H03_NVM_INVALID, &empty, &learned);
    assert(lfj8_h03_nvm_native_restore_dtc(test_blocks, NULL) == LFJ8_H03_NVM_INVALID);
    expect_restore(test_blocks, LFJ8_H03_NVM_SLOT_1, &learned, &learned);
    puts("PASS native H03 array: inaccessible, busy, erase/program error, E/W, Virtual Flash and invalid blocks");
    return 0;
}
