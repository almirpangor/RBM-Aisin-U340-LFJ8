#ifndef RBM_LFJ8_H03_NVM_NATIVE_H
#define RBM_LFJ8_H03_NVM_NATIVE_H

#include "lfj8_h03_nvm.h"

/* Cold-start reader for the internal M32176F4 array. The startup owner
 * provides two exclusively reserved erase blocks and owns the DTC RAM.
 * Call in normal executable Flash mode before starting DTC producers and
 * the service writer. The native IRQ lock covers both journal reads.
 *
 * Returns the journal restore status. A busy, inaccessible, errored or
 * emulated array fails closed. There are no erase or program operations. */
Lfj8H03NvmResult lfj8_h03_nvm_native_restore_dtc(const uint8_t blocks[2], CheryDtcState *state);

#endif
