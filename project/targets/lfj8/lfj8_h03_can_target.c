#include "lfj8_h03_can_target.h"
#include "lfj8_h03_can_owner.h"
#include "lfj8_h03_dtc_native.h"
#include "lfj8_h03_mmio.h"

Lfj8H03Can13Result lfj8_h03_can_target_poll(Lfj8H03DtcTarget *target,
                                         Lfj8H03Can13Input *input, bool tx_gate_ready)
{
    const Lfj8RegisterIo *const io = &lfj8_h03_mmio;
    const uint32_t saved = io->enter(io->context);
    const bool ready = tx_gate_ready && h03_can_owner.setup_permitted;
    const Lfj8H03Can13Result result = lfj8_h03_dtc_native_poll(target, input, ready);
    io->leave(io->context, saved);
    return result;
}
