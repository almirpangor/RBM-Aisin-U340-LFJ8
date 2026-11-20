#include "lfj8_h03_mmio.h"

#define H03_TML0CT UINT32_C(0x8003E0)

static uint8_t read_byte(void *context, uint32_t address)
{
    (void)context;
    return *(volatile const uint8_t *)(uintptr_t)address;
}

static uint16_t read_halfword(void *context, uint32_t address)
{
    (void)context;
    return *(volatile const uint16_t *)(uintptr_t)address;
}

static uint32_t read_word(void *context, uint32_t address)
{
    (void)context;
    return *(volatile const uint32_t *)(uintptr_t)address;
}

static void write_byte(void *context, uint32_t address, uint8_t value)
{
    (void)context;
    *(volatile uint8_t *)(uintptr_t)address = value;
}

static uint32_t enter(void *context)
{
    (void)context;
    uint32_t saved;
    uint32_t masked;
    __asm__ volatile ("mvfc %0,psw\n\tand3 %1,%0,#0xbf\n\tmvtc %1,psw"
                      : "=&r"(saved), "=&r"(masked) : : "memory", "cc");
    return saved;
}

static void leave(void *context, uint32_t saved)
{
    (void)context;
    __asm__ volatile ("mvtc %0,psw" : : "r"(saved) : "memory", "cc");
}

const Lfj8RegisterIo lfj8_h03_mmio = {
    .read8 = read_byte,
    .read16 = read_halfword,
    .read32 = read_word,
    .write8 = write_byte,
    .enter = enter,
    .leave = leave,
};

unsigned lfj8_h03_engine_rx_m32r(Lfj8H03EngineRx *rx, uint8_t slots_owned,
                                Ta2005CherySnapshot *snapshot)
{
    return lfj8_h03_engine_rx_poll(rx, &lfj8_h03_mmio, read_word(0, H03_TML0CT),
                                   slots_owned, snapshot);
}
