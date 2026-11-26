#include "lfj8_h03_atf_fault.h"

#define ATF_CIRCUIT_ACTIVE UINT32_C(0x8063E7)
#define ATF_CIRCUIT_HIGH UINT32_C(0x8065EB)
#define ATF_CIRCUIT_LOW UINT32_C(0x8065EC)
#define ATF_CIRCUIT_RECOVERED UINT32_C(0x8065F0)

Lfj8H03AtfCircuitStatus lfj8_h03_atf_circuit_after_monitor(const Lfj8RegisterIo *io)
{
    if (!io || !io->enter || !io->leave || !io->read8) {
        return LFJ8_H03_ATF_CIRCUIT_UNKNOWN;
    }

    const uint32_t saved = io->enter(io->context);
    const uint8_t active = io->read8(io->context, ATF_CIRCUIT_ACTIVE);
    const uint8_t high = io->read8(io->context, ATF_CIRCUIT_HIGH);
    const uint8_t low = io->read8(io->context, ATF_CIRCUIT_LOW);
    const uint8_t recovered = io->read8(io->context, ATF_CIRCUIT_RECOVERED);
    io->leave(io->context, saved);

    if (active == 1 && recovered == 0 && low <= 1 && high <= 1) {
        return (Lfj8H03AtfCircuitStatus)(low | (high << 1));
    }
    if (active == 0 && recovered == 1 && low == 0 && high == 0) {
        return LFJ8_H03_ATF_CIRCUIT_NO_CURRENT_FAULT;
    }
    return LFJ8_H03_ATF_CIRCUIT_UNKNOWN;
}
