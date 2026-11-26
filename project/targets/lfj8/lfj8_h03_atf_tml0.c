/* Native TML0 time provider and common S51/S83/ATF clock checks. */
#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_mmio.h"

#define H03_PRS1 UINT32_C(0x800203)
#define H03_TML0CR UINT32_C(0x8003EB)
#define H03_TML1CR UINT32_C(0x800FEB)
#define H03_TML0CT UINT32_C(0x8003E0)

int lfj8_h03_sensor_clock_registers_match(void)
{
    const Lfj8RegisterIo *io = &lfj8_h03_mmio;
    return io->read8(io->context, H03_PRS1) == 9u &&
           io->read8(io->context, H03_TML0CR) == 0x01u &&
           io->read8(io->context, H03_TML1CR) == 0x31u;
}

int lfj8_h03_sensor_clock_ready_locked(void)
{
    if (rbm_h03_tml0_1mhz_qualified != 1u) {
        return 0;
    }
    if (!lfj8_h03_sensor_clock_registers_match()) {
        rbm_h03_tml0_1mhz_qualified = 0u;
        return 0;
    }
    return 1;
}

int rbm_h03_atf_now_us(uint32_t *now_us)
{
    if (!now_us || !lfj8_h03_sensor_clock_ready_locked()) {
        return 0;
    }
    const Lfj8RegisterIo *io = &lfj8_h03_mmio;
    *now_us = io->read32(io->context, H03_TML0CT);
    return 1;
}
