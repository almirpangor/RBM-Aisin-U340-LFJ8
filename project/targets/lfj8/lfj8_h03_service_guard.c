#include "lfj8_h03_service_guard.h"

int lfj8_h03_service_span_allowed(const Lfj8H03ServicePolicy *policy,
                                  uint32_t address, uint32_t count)
{
    if (!policy || !policy->count || policy->count > LFJ8_H03_SERVICE_RANGES ||
        count > UINT32_MAX - address) {
        return 0;
    }
    uint32_t previous = 0x804000u;
    for (uint32_t i = 0; i < policy->count; ++i) {
        const Lfj8H03ServiceRange range = policy->ranges[i];
        if (range.first < previous || range.first >= range.end || range.end > 0x80a000u ||
            (count && address < range.end && address + count > range.first)) {
            return 0;
        }
        previous = range.end;
    }
    return 1;
}

int lfj8_h03_service_copy_allowed(const Lfj8H03ServicePolicy *policy,
                                  uint32_t destination, uint32_t total, uint32_t remaining)
{
    if (remaining > total) {
        return 0;
    }
    /* Check the whole original transaction on every slice, before checksum,
     * pointer or remaining-count updates. A zero pending count writes nothing. */
    return lfj8_h03_service_span_allowed(policy, destination, remaining ? total : 0u);
}
