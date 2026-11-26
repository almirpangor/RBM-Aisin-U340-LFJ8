#undef NDEBUG
#include <assert.h>
#include <stdio.h>

#include "lfj8_h03_mmio.h"

#define INTERRUPTS_ENABLED UINT32_C(0x40)

static uint32_t read_psw(void)
{
    uint32_t psw;
    __asm__ volatile ("mvfc %0,psw" : "=r"(psw));
    return psw;
}

static void write_psw(uint32_t psw)
{
    __asm__ volatile ("mvtc %0,psw" : : "r"(psw) : "memory", "cc");
}

int main(void)
{
    const Lfj8RegisterIo *io = &lfj8_h03_mmio;
    const uint32_t original = read_psw();
    write_psw(original | INTERRUPTS_ENABLED);
    const uint32_t outer = io->enter(io->context);
    assert((outer & INTERRUPTS_ENABLED) != 0u);
    assert((read_psw() & INTERRUPTS_ENABLED) == 0u);
    const uint32_t inner = io->enter(io->context);
    assert((inner & INTERRUPTS_ENABLED) == 0u);
    io->leave(io->context, inner);
    assert((read_psw() & INTERRUPTS_ENABLED) == 0u);
    io->leave(io->context, outer);
    assert((read_psw() & INTERRUPTS_ENABLED) != 0u);
    write_psw(original);

    uint32_t scratch = 0x10203040u;
    const uint32_t address = (uint32_t)(uintptr_t)&scratch;
    assert(io->read8(io->context, address) == 0x10u);
    assert(io->read16(io->context, address + 2u) == 0x3040u);
    assert(io->read32(io->context, address) == 0x10203040u);
    io->write8(io->context, address + 2u, 0xabu);
    assert(io->read32(io->context, address) == 0x1020ab40u);
    puts("H03 M32R MMIO width, byte order and nested PSW restore passed.");
    return 0;
}
