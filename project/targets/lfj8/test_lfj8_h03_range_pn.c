#include "lfj8_h03_range_pn.h"

#include <stddef.h>

#define CHECK(condition) do { if (!(condition)) return __LINE__; } while (0)

static int rejected(const Lfj8H03RangeBit *contact, const Lfj8H03PnSelector *selector,
                    const Lfj8H03PnLimits *limits, uint32_t now)
{
    Lfj8H03RangeBit out = {.captured_us = 1, .generation = 1, .asserted = 1, .valid = 1};
    return !lfj8_h03_range_qualify_pn(contact, selector, limits, 0, now, &out) &&
           !out.captured_us && !out.generation && !out.asserted && !out.valid;
}

int check_independent_pn(void)
{
    const uint32_t now = 2u;
    const Lfj8H03PnLimits limits = {.max_age_us = 8, .max_skew_us = 4};
    const Lfj8H03RangeBit valid_contact = {.captured_us = now - 5u, .asserted = 1, .valid = 1};
    const Lfj8H03PnSelector valid_selector = {.captured_us = now - 1u, .position = RBM_U340E_SELECTOR_N};
    Lfj8H03RangeBit contact = valid_contact;
    Lfj8H03PnSelector selector = valid_selector;
    Lfj8H03RangeBit out;

    for (uint8_t position = RBM_U340E_SELECTOR_P; position <= RBM_U340E_SELECTOR_L; ++position) {
        selector.position = position;
        const int expected_pn = position == RBM_U340E_SELECTOR_P || position == RBM_U340E_SELECTOR_N;
        for (uint8_t asserted = 0; asserted <= 1; ++asserted) {
            contact.asserted = asserted;
            const int matched = expected_pn == asserted;
            CHECK(lfj8_h03_range_qualify_pn(&contact, &selector, &limits, 0, now, &out) == matched);
            CHECK(out.valid == matched && out.asserted == (matched ? asserted : 0));
            CHECK(out.captured_us == (matched ? contact.captured_us : 0));
        }
    }

    selector = valid_selector;
    contact = valid_contact;
    contact.captured_us = now;
    CHECK(lfj8_h03_range_qualify_pn(&contact, &selector, &limits, 0, now, &out));
    CHECK(out.captured_us == selector.captured_us);

    contact = valid_contact;
    CHECK(lfj8_h03_range_qualify_pn(&contact, &selector, &limits, 0, now, &out));
    Lfj8H03RangeInputs inputs = {.inhibit_5250_2 = {.captured_us = now, .valid = 1}};
    const Lfj8H03RangeAgeLimits ages = {.range_5722_us = {8, 8, 8, 8}, .inhibit_5250_2_us = 8};
    for (unsigned i = 0; i < 4; ++i) {
        inputs.range_5722[i] = (Lfj8H03RangeBit){.captured_us = now, .valid = 1};
    }
    inputs.range_5722[2] = out;
    Lfj8H03RangeSnapshot range;
    CHECK(lfj8_h03_range_snapshot(&inputs, &ages, 0, now, &range));
    CHECK(range.range_5722 == 4u && range.oldest_us == valid_contact.captured_us);
    CHECK(!lfj8_h03_range_snapshot(&inputs, &ages, 0, now + 3u, &range));

    contact.valid = 0;
    CHECK(rejected(&contact, &selector, &limits, now));
    contact = valid_contact;
    contact.asserted = 2;
    CHECK(rejected(&contact, &selector, &limits, now));
    contact = valid_contact;
    contact.generation = UINT32_MAX;
    CHECK(rejected(&contact, &selector, &limits, now));
    contact = valid_contact;
    selector.generation = UINT32_MAX;
    CHECK(rejected(&contact, &selector, &limits, now));
    selector = valid_selector;
    selector.position = RBM_U340E_SELECTOR_UNKNOWN;
    CHECK(rejected(&contact, &selector, &limits, now));
    selector.position = RBM_U340E_SELECTOR_L + 1u;
    CHECK(rejected(&contact, &selector, &limits, now));

    selector = valid_selector;
    contact.captured_us = now + 1u;
    CHECK(rejected(&contact, &selector, &limits, now));
    contact.captured_us = now - limits.max_age_us;
    CHECK(rejected(&contact, &selector, &limits, now));
    contact = valid_contact;
    selector.captured_us = now + 1u;
    CHECK(rejected(&contact, &selector, &limits, now));
    selector.captured_us = now - limits.max_age_us;
    CHECK(rejected(&contact, &selector, &limits, now));
    /* Both captures are fresh but five ticks apart. */
    selector.captured_us = now;
    CHECK(rejected(&contact, &selector, &limits, now));

    selector = valid_selector;
    const Lfj8H03PnLimits zero_age = {.max_skew_us = 4};
    const Lfj8H03PnLimits bad_skew = {.max_age_us = 8, .max_skew_us = UINT32_C(0x80000000)};
    CHECK(rejected(&contact, &selector, &zero_age, now));
    CHECK(rejected(&contact, &selector, &bad_skew, now));
    CHECK(rejected(NULL, &selector, &limits, now));
    CHECK(rejected(&contact, NULL, &limits, now));
    CHECK(rejected(&contact, &selector, NULL, now));
    CHECK(!lfj8_h03_range_qualify_pn(&contact, &selector, &limits, 0, now, NULL));
    return 0;
}
