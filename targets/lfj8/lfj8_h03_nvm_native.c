#include "lfj8_h03_nvm_native.h"
#include "lfj8_h03_mmio.h"

#define H03_FMOD UINT32_C(0x8007E0)
#define H03_FSTAT UINT32_C(0x8007E1)
#define H03_FCNT1 UINT32_C(0x8007E2)
#define H03_FELBANK0 UINT32_C(0x8007E8)
#define H03_FELBANK1 UINT32_C(0x8007EA)
#define H03_FESBANK0 UINT32_C(0x8007F0)
#define H03_FESBANK1 UINT32_C(0x8007F2)

enum { FAENS = 0x10, FBUSY_READY = 0x80, ERASE_ERROR = 0x20, WRITE_ERROR = 0x10,
       FLASH_BANK_ENABLE = 0x8000 };

static bool array_ready(void)
{
    const Lfj8RegisterIo *const io = &lfj8_h03_mmio;
    void *const context = io->context;
    const unsigned status_mask = FBUSY_READY | ERASE_ERROR | WRITE_ERROR;
    /* Require normal array access and reject bank enables independently of
     * FCNT1, as in the H03 RAM owner's plain-Flash gate. */
    return io->read8(context, H03_FCNT1) == 0u &&
        (io->read8(context, H03_FMOD) & FAENS) != 0u &&
        (io->read8(context, H03_FSTAT) & status_mask) == FBUSY_READY &&
        !((io->read16(context, H03_FELBANK0) | io->read16(context, H03_FELBANK1) |
           io->read16(context, H03_FESBANK0) | io->read16(context, H03_FESBANK1)) & FLASH_BANK_ENABLE);
}

static bool read_array(void *context, uint32_t address, uint8_t *data, size_t size)
{
    (void)context;
    const Lfj8RegisterIo *const io = &lfj8_h03_mmio;
    if ((address & 1u) || (size & 1u) || !array_ready()) {
        return false;
    }
    /* The startup reader supplies a validated block start and record length. */
    for (size_t i = 0; i < size; i += 2u, address += 2u) {
        const uint16_t word = io->read16(io->context, address);
        data[i] = (uint8_t)(word >> 8);
        data[i + 1u] = (uint8_t)word;
    }
    return array_ready();
}

Lfj8H03NvmResult lfj8_h03_nvm_native_restore_dtc(const uint8_t blocks[2], CheryDtcState *state)
{
    if (!blocks || !state) {
        return lfj8_h03_nvm_restore_dtc(NULL, state);
    }
    const Lfj8H03Nvm nvm = {
        .blocks = {blocks[0], blocks[1]},
        .read = read_array,
    };
    const Lfj8RegisterIo *const io = &lfj8_h03_mmio;
    const uint32_t saved = io->enter(io->context);
    const Lfj8H03NvmResult result = lfj8_h03_nvm_restore_dtc(&nvm, state);
    io->leave(io->context, saved);
    return result;
}

bool lfj8_h03_nvm_native_read_adaptation(const uint8_t blocks[2],
    uint8_t slots[2][FACTORY_ADAPT_RECORD_BYTES])
{
    Lfj8H03NvmBlock first, second;
    if (!blocks || !slots || blocks[0] == blocks[1] ||
        !lfj8_h03_nvm_block(blocks[0], &first) || !lfj8_h03_nvm_block(blocks[1], &second) ||
        FACTORY_ADAPT_RECORD_BYTES > first.end - first.first ||
        FACTORY_ADAPT_RECORD_BYTES > second.end - second.first) {
        return false;
    }

    const Lfj8RegisterIo *const io = &lfj8_h03_mmio;
    const uint32_t saved = io->enter(io->context);
    const bool readable = read_array(NULL, first.first, slots[0], sizeof slots[0]) &&
        read_array(NULL, second.first, slots[1], sizeof slots[1]);
    io->leave(io->context, saved);
    return readable;
}
