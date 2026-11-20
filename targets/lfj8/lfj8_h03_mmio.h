#ifndef RBM_LFJ8_H03_MMIO_H
#define RBM_LFJ8_H03_MMIO_H

#include "lfj8_h03_engine_rx.h"

extern const Lfj8RegisterIo lfj8_h03_mmio;

/* Foreground entry for the verified H03 map with TML0CT running at 1 MHz.
 * Initialize the caller-owned state once before startup. The owner must
 * qualify the clock, assign RX11/12 and serialize execution outside the ISR. */
unsigned lfj8_h03_engine_rx_m32r(Lfj8H03EngineRx *rx, uint8_t slots_owned,
                                Ta2005CherySnapshot *snapshot);

#endif
