#include "lfj8_h03_range_pn.h"

#define HALF_CLOCK UINT32_C(0x80000000)

int lfj8_h03_range_qualify_pn(const Lfj8H03RangeBit *contact, const Lfj8H03PnSelector *selector,
    const Lfj8H03PnLimits *limits, uint32_t generation, uint32_t now_us, Lfj8H03RangeBit *out)
{
    if (!out) {
        return 0;
    }
    *out = (Lfj8H03RangeBit){0};
    if (!contact || !selector || !limits ||
        !limits->max_age_us || limits->max_age_us >= HALF_CLOCK || limits->max_skew_us >= HALF_CLOCK ||
        contact->valid != 1u || contact->asserted > 1u ||
        contact->generation != generation || selector->generation != generation ||
        selector->position < RBM_U340E_SELECTOR_P || selector->position > RBM_U340E_SELECTOR_L) {
        return 0;
    }

    const uint32_t contact_age = now_us - contact->captured_us;
    const uint32_t selector_age = now_us - selector->captured_us;
    const uint32_t oldest = contact_age > selector_age ? contact_age : selector_age;
    const uint32_t newest = contact_age < selector_age ? contact_age : selector_age;
    const int in_pn = selector->position == RBM_U340E_SELECTOR_P || selector->position == RBM_U340E_SELECTOR_N;
    if (oldest >= limits->max_age_us || oldest - newest > limits->max_skew_us || contact->asserted != in_pn) {
        return 0;
    }

    out->captured_us = now_us - oldest;
    out->generation = generation;
    out->asserted = contact->asserted;
    out->valid = 1u;
    return 1;
}
