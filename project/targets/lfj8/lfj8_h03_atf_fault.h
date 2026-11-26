#ifndef RBM_LFJ8_H03_ATF_FAULT_H
#define RBM_LFJ8_H03_ATF_FAULT_H

#include "lfj8_donor_io.h"

typedef enum {
    LFJ8_H03_ATF_CIRCUIT_UNKNOWN = 0,
    LFJ8_H03_ATF_CIRCUIT_LOW = 1,
    LFJ8_H03_ATF_CIRCUIT_HIGH = 2,
    LFJ8_H03_ATF_CIRCUIT_BOTH = LFJ8_H03_ATF_CIRCUIT_LOW | LFJ8_H03_ATF_CIRCUIT_HIGH,
    LFJ8_H03_ATF_CIRCUIT_NO_CURRENT_FAULT = 4,
} Lfj8H03AtfCircuitStatus;

/* Sample only after a completed OEM 0x0753A4 monitor call on H03. Bind io
 * to the verified H03 map and serialize with the monitor and service reset.
 * The result is the debounced status. BOTH means stock retained both
 * directions before a qualified recovery, possibly across a service reset.
 * UNKNOWN supplies no transition. The caller owns freshness and DTC policy.
 */
Lfj8H03AtfCircuitStatus lfj8_h03_atf_circuit_after_monitor(const Lfj8RegisterIo *io);

#endif
