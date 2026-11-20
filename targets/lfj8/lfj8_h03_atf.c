#include "lfj8_h03_atf.h"

#define ATF_ADC_ADDRESS UINT32_C(0x804BC4)
#define ATF_VOLTS_ADDRESS UINT32_C(0x804F04)
#define ATF_TEMPERATURE_ADDRESS UINT32_C(0x805028)
#define ATF_FAULT_ADDRESS UINT32_C(0x8063E7)

/* H03 ROM 0x0165DC and 0x0165D8 give a strict voltage range which
 * corresponds to these inclusive ADC counts after multiplying by 5/1024. */
#define ATF_ADC_MIN 13u
#define ATF_ADC_MAX 956u
#define CLOCK_HALF_RANGE UINT32_C(0x80000000)
#define Q8_ONE 256
#define TOYOTA_ATF_OFFSET_Q8 (40 * Q8_ONE)

static int fresh_timestamp(uint32_t current, uint32_t previous)
{
    const uint32_t delta = current - previous;
    return delta != 0 && delta < CLOCK_HALF_RANGE;
}

static uint32_t voltage_bits(uint16_t counts)
{
    uint32_t significand = (uint32_t)counts * 5u;
    /* The eligible range starts at 13, so this is strictly positive. */
    uint32_t exponent = 140u; /* 127 + 23 - 10 before normalization. */
    while (significand < UINT32_C(0x800000)) {
        significand <<= 1;
        --exponent;
    }
    return (exponent << 23) | (significand & UINT32_C(0x7FFFFF));
}

static int measured_toyota_q8(uint32_t bits, uint16_t *result)
{
    const uint32_t magnitude = bits & UINT32_C(0x7FFFFFFF);
    const uint32_t negative = bits >> 31;
    /* -40 to +150 C are the measured curve endpoints. These unsigned
     * bounds also reject infinities and NaNs in either sign. */
    const uint32_t limit = negative ? UINT32_C(0x42200000) : UINT32_C(0x43160000);
    if (magnitude > limit) {
        return 0;
    }

    const unsigned exponent = (unsigned)(magnitude >> 23);
    uint32_t absolute_q8 = 0;
    if (exponent > 118u) {
        const uint32_t significand = (magnitude & UINT32_C(0x7FFFFF)) | UINT32_C(0x800000);
        absolute_q8 = significand >> (142u - exponent);
    }
    const int32_t signed_q8 = negative ? -(int32_t)absolute_q8 : (int32_t)absolute_q8;
    *result = (uint16_t)(signed_q8 + TOYOTA_ATF_OFFSET_Q8);
    return 1;
}

void lfj8_h03_atf_init(volatile Lfj8H03Atf *state)
{
    if (state) {
        state->last_adc_us = 0;
        state->last_publication_us = 0;
        state->sampled_adc_us = 0;
        state->adc = 0;
        state->toyota_gp_m7184 = 0;
        state->adc_seen = 0;
        state->publication_seen = 0;
        state->pending_adc = 0;
        state->valid = 0;
    }
}

int lfj8_h03_atf_after_adc_store(volatile Lfj8H03Atf *state, const Lfj8RegisterIo *io,
                                uint32_t acquired_us)
{
    if (!state || !io || !io->enter || !io->leave || !io->read8 || !io->read16) {
        return 0;
    }
    const uint32_t saved = io->enter(io->context);
    if (state->adc_seen && !fresh_timestamp(acquired_us, state->last_adc_us)) {
        io->leave(io->context, saved);
        return 0;
    }
    const uint16_t counts = io->read16(io->context, ATF_ADC_ADDRESS);
    const uint8_t eligible = (uint8_t)(counts >= ATF_ADC_MIN && counts <= ATF_ADC_MAX &&
                                       io->read8(io->context, ATF_FAULT_ADDRESS) == 0);
    state->last_adc_us = acquired_us;
    state->adc_seen = 1;
    state->adc = counts;
    state->pending_adc = eligible;
    if (!eligible) {
        state->valid = 0;
    }
    io->leave(io->context, saved);
    return 1;
}

int lfj8_h03_atf_after_store(volatile Lfj8H03Atf *state, const Lfj8RegisterIo *io,
                            uint32_t store_site, const uint32_t *source_acquired_us,
                            uint32_t published_us)
{
    if (!state || !io || !io->enter || !io->leave || !io->read8 || !io->read32 ||
        (store_site != LFJ8_H03_ATF_FAULT_STORE &&
         store_site != LFJ8_H03_ATF_DIRECT_STORE &&
         store_site != LFJ8_H03_ATF_FILTERED_STORE)) {
        return 0;
    }
    const uint32_t saved = io->enter(io->context);
    if (state->publication_seen && !fresh_timestamp(published_us, state->last_publication_us)) {
        io->leave(io->context, saved);
        return 0;
    }
    state->last_publication_us = published_us;
    state->publication_seen = 1;

    if (store_site == LFJ8_H03_ATF_FAULT_STORE || io->read8(io->context, ATF_FAULT_ADDRESS) != 0) {
        state->valid = 0;
        state->pending_adc = 0;
    } else if (!state->adc_seen || !source_acquired_us || *source_acquired_us != state->last_adc_us ||
               published_us - *source_acquired_us >= CLOCK_HALF_RANGE) {
        state->valid = 0;
    } else if (state->pending_adc) {
        uint16_t temperature = 0;
        state->pending_adc = 0;
        /* Match the voltage used by OEM against its associated ADC event. */
        const int valid = io->read32(io->context, ATF_VOLTS_ADDRESS) == voltage_bits(state->adc) &&
            measured_toyota_q8(io->read32(io->context, ATF_TEMPERATURE_ADDRESS), &temperature);
        state->valid = (uint8_t)valid;
        state->sampled_adc_us = *source_acquired_us;
        state->toyota_gp_m7184 = temperature;
    }

    io->leave(io->context, saved);
    return 1;
}

int lfj8_h03_atf_snapshot(volatile Lfj8H03Atf *state, const Lfj8RegisterIo *io,
                         uint32_t now_us, uint32_t max_age_us,
                         Lfj8H03AtfSample *sample)
{
    if (!sample) {
        return 0;
    }
    sample->acquired_us = 0;
    sample->atf_c = 0;
    sample->toyota_gp_m7184 = 0;
    if (!state || !io || !io->enter || !io->leave || !io->read8 ||
        max_age_us == 0 || max_age_us >= CLOCK_HALF_RANGE) {
        return 0;
    }

    const uint32_t saved = io->enter(io->context);
    if ((state->valid || state->pending_adc) && io->read8(io->context, ATF_FAULT_ADDRESS) != 0) {
        state->valid = 0;
        state->pending_adc = 0;
    }
    if (state->pending_adc && now_us - state->last_adc_us >= max_age_us) {
        state->pending_adc = 0;
    }
    if (state->valid && now_us - state->sampled_adc_us >= max_age_us) {
        state->valid = 0;
    }
    const int valid = state->valid != 0;
    if (valid) {
        sample->acquired_us = state->sampled_adc_us;
        sample->toyota_gp_m7184 = state->toyota_gp_m7184;
    }
    io->leave(io->context, saved);

    if (valid) {
        sample->atf_c = (int16_t)(((int32_t)sample->toyota_gp_m7184 - TOYOTA_ATF_OFFSET_Q8) / Q8_ONE);
    }
    return valid;
}
