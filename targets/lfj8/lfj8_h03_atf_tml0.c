/* Optional native implementation of the ATF time provider on H03. */
#include "lfj8_h03_atf_target.h"
#include "lfj8_h03_mmio.h"

#define H03_PRS1 UINT32_C(0x800203)
#define H03_TML0CR UINT32_C(0x8003EB)
#define H03_TML0CT UINT32_C(0x8003E0)

int rbm_h03_atf_now_us(uint32_t *now_us)
{
    if (!now_us || rbm_h03_tml0_1mhz_qualified != 1u) {
        return 0;
    }
    const Lfj8RegisterIo *io = &lfj8_h03_mmio;
    if (io->read8(io->context, H03_PRS1) != 9u ||
        !(io->read8(io->context, H03_TML0CR) & 1u)) {
        return 0;
    }
    *now_us = io->read32(io->context, H03_TML0CT);
    return 1;
}
