#include "lfj8_bridge.h"

static uint8_t flag(uint8_t value)
{
    return value != 0u;
}

typedef struct {
    uint64_t low;
    uint32_t high;
} VssProduct;

/* The complete numerator is below 2^89, and the denominator below 2^69.
 * All positive intermediate products fit in the same 96-bit representation. */
static VssProduct multiply_u96_by_u32(VssProduct value, uint32_t factor)
{
    const uint64_t low = (uint64_t)(uint32_t)value.low * factor;
    const uint64_t middle = (value.low >> 32) * factor + (low >> 32);
    return (VssProduct){
        .low = (middle << 32) | (uint32_t)low,
        .high = value.high * factor + (uint32_t)(middle >> 32),
    };
}

static uint8_t product_le(VssProduct left, VssProduct right)
{
    return left.high < right.high || (left.high == right.high && left.low <= right.low);
}

static VssProduct product_half(VssProduct value)
{
    return (VssProduct){
        .low = (value.low >> 1) | ((uint64_t)(value.high & 1u) << 63),
        .high = value.high >> 1,
    };
}

/* Quotient bound permits dividers on targets with no native wide division. */
static uint16_t speed_quotient(VssProduct numerator, VssProduct denominator)
{
    uint32_t bit = 1u;
    uint32_t quotient = 0u;
    if (!product_le(denominator, numerator)) {
        return 0u;
    }
    const VssProduct half = product_half(numerator);
    while (product_le(denominator, half)) {
        if (bit >= LFJ8_SPEED_WRAP / 2u) {
            return LFJ8_SPEED_UNAVAILABLE;
        }
        denominator.high = (denominator.high << 1) | (uint32_t)(denominator.low >> 63);
        denominator.low <<= 1;
        bit <<= 1;
    }
    do {
        if (product_le(denominator, numerator)) {
            numerator.high -= denominator.high + (numerator.low < denominator.low);
            numerator.low -= denominator.low;
            quotient |= bit;
        }
        denominator = product_half(denominator);
        bit >>= 1;
    } while (bit != 0u);
    return quotient < LFJ8_SPEED_WRAP ? (uint16_t)quotient : LFJ8_SPEED_UNAVAILABLE;
}

uint16_t lfj8_vss_raw_1ae(uint32_t ticks, uint8_t pulse_count, uint32_t tick_hz,
                        uint32_t wheel_um, uint16_t wheel_num, uint16_t wheel_den,
                        uint8_t capture_state)
{
    if (tick_hz == 0u || wheel_um == 0u || wheel_num == 0u || wheel_den == 0u) {
        return LFJ8_SPEED_UNAVAILABLE;
    }
    if (capture_state == LFJ8_VSS_STOPPED) {
        return 0u;
    }
    if (capture_state != LFJ8_VSS_VALID || ticks == 0u ||
        (pulse_count != 1u && pulse_count != 2u && pulse_count != 4u)) {
        return LFJ8_SPEED_UNAVAILABLE;
    }

    /* 360 * (22 / 100) * (1 / 1000000) == 99 / 1250000. */
    VssProduct numerator = {.low = UINT64_C(99) * pulse_count * tick_hz};
    numerator = multiply_u96_by_u32(numerator, wheel_um);
    numerator = multiply_u96_by_u32(numerator, wheel_num);
    const VssProduct denominator =
        multiply_u96_by_u32((VssProduct){.low = (uint64_t)ticks * wheel_den}, UINT32_C(1250000));
    return speed_quotient(numerator, denominator);
}

uint8_t lfj8_pack_1ae(uint8_t out[8], const Lfj8Chery1ae *status, uint16_t speed_raw)
{
    return lfj8_pack_1ae_with_counter(out, status, speed_raw, status->counter_f8e4);
}

uint8_t lfj8_pack_1ae_with_counter(uint8_t out[8], const Lfj8Chery1ae *status,
                                  uint16_t speed_raw, uint8_t previous_counter)
{
    const uint8_t enabled = flag(status->flag_fd18_4);
    const uint8_t next = enabled ? (uint8_t)(previous_counter + 1u) : 0u;
    const uint8_t integrity = (uint8_t)~(status->byte1 + status->byte4);
    const unsigned byte5 = 2u * status->raw_fa5f;

    out[0] = (uint8_t)(((unsigned)flag(status->flag_f842_5) << 4) | (integrity & 0x0Fu));
    out[1] = status->byte1;
    out[2] = (uint8_t)(enabled | ((unsigned)flag(status->flag_fd10_7) << 1) |
                       ((status->raw_f8e1 & 3u) << 2) | ((next & 7u) << 4) |
                       ((unsigned)flag(status->flag_f83e_4) << 7));
    out[3] = (uint8_t)(((status->byte3_high & 0x0Fu) << 4) | (integrity >> 4));
    out[4] = status->byte4;
    out[5] = flag(status->flag_e026_0) ? 0xFFu : (uint8_t)(byte5 > 254u ? 254u : byte5);
    out[6] = (uint8_t)(speed_raw >> 8);
    out[7] = (uint8_t)speed_raw;
    return next;
}

void lfj8_pack_300(uint8_t out[8], uint8_t byte0, uint8_t byte1, uint8_t flag_fd18_9,
                   int16_t atf_c, uint8_t atf_valid)
{
    uint8_t encoded_atf = 0xFFu;
    if (atf_valid != 0u) {
        if (atf_c < -40) {
            atf_c = -40;
        } else if (atf_c > 104) {
            atf_c = 104;
        }
        encoded_atf = (uint8_t)(atf_c + 40);
    }
    out[0] = byte0;
    out[1] = byte1;
    out[2] = flag_fd18_9 != 0u ? 0x40u : 0u;
    out[3] = encoded_atf;
    out[4] = 0u;
    out[5] = 0u;
    out[6] = 0u;
    out[7] = 0u;
}

void lfj8_schedule_init(Lfj8CherySchedule *schedule, uint32_t now_us,
                        uint32_t period_1ae_us, uint32_t period_300_us)
{
    schedule->last_1ae_us = now_us;
    schedule->last_300_us = now_us;
    schedule->period_1ae_us = period_1ae_us;
    schedule->period_300_us = period_300_us;
}

static uint32_t period_remainder(uint32_t elapsed, uint32_t period)
{
    uint32_t shifted = period;
    while (shifted <= (elapsed >> 1)) {
        shifted <<= 1;
    }
    while (shifted > period) {
        if (elapsed >= shifted) {
            elapsed -= shifted;
        }
        shifted >>= 1;
    }
    return elapsed >= period ? elapsed - period : elapsed;
}

static uint8_t elapsed_period(uint32_t now_us, uint32_t *phase_us, uint32_t period_us)
{
    const uint32_t elapsed = now_us - *phase_us;
    if (period_us == 0u || elapsed < period_us) {
        return 0u;
    }
    *phase_us = now_us - period_remainder(elapsed, period_us);
    return 1u;
}

uint8_t lfj8_schedule_poll(Lfj8CherySchedule *schedule, uint32_t now_us)
{
    uint8_t due = 0u;
    if (elapsed_period(now_us, &schedule->last_1ae_us, schedule->period_1ae_us)) {
        due |= LFJ8_DUE_1AE;
    }
    if (elapsed_period(now_us, &schedule->last_300_us, schedule->period_300_us)) {
        due |= LFJ8_DUE_300;
    }
    return due;
}

uint8_t lfj8_relay_mask(uint8_t selector)
{
    switch (selector) {
    case 'R':
        return LFJ8_REVERSE_RELAY | LFJ8_AUX_RELAY;
    case 'L':
        return LFJ8_AUX_RELAY;
    default:
        return 0u;
    }
}
