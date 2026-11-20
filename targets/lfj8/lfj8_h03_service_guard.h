#ifndef RBM_LFJ8_H03_SERVICE_GUARD_H
#define RBM_LFJ8_H03_SERVICE_GUARD_H
#include <stdint.h>

enum { LFJ8_H03_SERVICE_RANGES = 8 };
typedef struct { uint32_t first, end; } Lfj8H03ServiceRange;
typedef struct {
    uint32_t count;
    Lfj8H03ServiceRange ranges[LFJ8_H03_SERVICE_RANGES];
} Lfj8H03ServicePolicy;

/* Immutable and resident even while stock service/Virtual Flash runs.
 * The final linker supplies ALL protected RAM, stack and binding ranges.
 * Empty, unordered or invalid policies refuse writes. No RAM gate is used. */
extern const Lfj8H03ServicePolicy rbm_h03_service_policy;

int lfj8_h03_service_span_allowed(const Lfj8H03ServicePolicy *policy,
                                  uint32_t address, uint32_t count);
int lfj8_h03_service_copy_allowed(const Lfj8H03ServicePolicy *policy,
                                  uint32_t destination, uint32_t total, uint32_t remaining);
#endif
