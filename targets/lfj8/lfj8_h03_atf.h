#ifndef RBM_LFJ8_H03_ATF_H
#define RBM_LFJ8_H03_ATF_H

#include "lfj8_donor_io.h"

enum {
    LFJ8_H03_ATF_ADC_STORE = 0x040178,
    LFJ8_H03_ATF_FAULT_STORE = 0x03B178,
    LFJ8_H03_ATF_DIRECT_STORE = 0x03B1A4,
    LFJ8_H03_ATF_FILTERED_STORE = 0x03B218,
};

typedef struct {
    uint32_t last_adc_us;
    uint32_t last_publication_us;
    uint32_t sampled_adc_us;
    uint16_t adc;
    uint16_t toyota_gp_m7184;
    uint8_t adc_seen;
    uint8_t publication_seen;
    uint8_t pending_adc;
    uint8_t valid;
} Lfj8H03Atf;

typedef struct {
    uint32_t acquired_us;
    int16_t atf_c; /* Whole degrees for lfj8_pack_300, truncated toward zero. */
    uint16_t toyota_gp_m7184; /* Measured H03 temperature in Toyota scale (C + 40) * 256. */
} Lfj8H03AtfSample;

/* Initialize before use and reset after a clock change or a gap of half a wrap. */
void lfj8_h03_atf_init(volatile Lfj8H03Atf *state);

/* Call once after each actual AN1 acquisition store at 0x040178 in H03.
 * The timestamp refers to that event. ADC tracking and OEM reads are serialized
 * by the platform. Returns 1 for an accepted event, even if its ADC is invalid. */
int lfj8_h03_atf_after_adc_store(volatile Lfj8H03Atf *state, const Lfj8RegisterIo *io,
                                uint32_t acquired_us);

/* Capture the tracked timestamp for the raw value OEM read at 0x03B138.
 * The caller must exclude ADC publication across both the OEM read and this
 * call. On failure, pass NULL to lfj8_h03_atf_after_store. The ROM-voltage
 * path bypasses the raw ADC read, so it never supplies this timestamp. */
static inline int lfj8_h03_atf_capture_source(const volatile Lfj8H03Atf *state,
                                              uint16_t oem_adc, uint32_t *source_acquired_us)
{
    if (!state || !source_acquired_us || !state->adc_seen || state->adc != oem_adc) {
        return 0;
    }
    *source_acquired_us = state->last_adc_us;
    return 1;
}

/* Call after the actual 0x805028 store at the stated H03 site, before another
 * producer can touch these fields. Capture source_acquired_us under the same
 * exclusion as the OEM raw ADC read at 0x03B138. NULL means the origin is unknown.
 * All timestamps share the same wrapping monotonic clock. One ADC acquisition
 * can qualify one temperature publication. Returns 1 for an accepted event,
 * even if it leaves temperature unavailable. */
int lfj8_h03_atf_after_store(volatile Lfj8H03Atf *state, const Lfj8RegisterIo *io,
                            uint32_t store_site, const uint32_t *source_acquired_us,
                            uint32_t published_us);

/* max_age_us applies from the underlying ADC acquisition. It must be positive
 * and less than 2^31. A live fault or expiry invalidates the sample. Returns
 * 1 only for a fresh qualified measurement and clears sample on failure. */
int lfj8_h03_atf_snapshot(volatile Lfj8H03Atf *state, const Lfj8RegisterIo *io,
                         uint32_t now_us, uint32_t max_age_us,
                         Lfj8H03AtfSample *sample);

#endif
