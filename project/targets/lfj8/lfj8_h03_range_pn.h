#ifndef RBM_LFJ8_H03_RANGE_PN_H
#define RBM_LFJ8_H03_RANGE_PN_H

#include "lfj8_range_control.h"

typedef struct {
    uint32_t captured_us;
    uint32_t generation;
    uint8_t position; /* Confirmed AN2 selector, or RBM_U340E_SELECTOR_UNKNOWN. */
} Lfj8H03PnSelector;

typedef struct {
    uint32_t max_age_us; /* Exclusive for both sources, positive and below half-wrap. */
    uint32_t max_skew_us; /* Inclusive separation of the two captures, below half-wrap. */
} Lfj8H03PnLimits;

/* Qualify a distinct, normalized P/N contact against the confirmed selector.
 * The caller verifies the contact's independent origin and polarity. An
 * asserted contact means P/N and supplies GP-5722.2 only on agreement.
 * Both samples use the current wrapping clock and generation. On success,
 * out carries the older timestamp for range_5722[2]. Failure clears out.
 * The output must be disjoint from the inputs. No starter I/O is performed. */
int lfj8_h03_range_qualify_pn(const Lfj8H03RangeBit *contact, const Lfj8H03PnSelector *selector,
    const Lfj8H03PnLimits *limits, uint32_t generation, uint32_t now_us, Lfj8H03RangeBit *out);

#endif
