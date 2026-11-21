#include "lfj8_h03_load_raw.h"

#define HALF_RANGE UINT32_C(0x80000000)

static uint16_t be16(const uint8_t *data)
{
    return (uint16_t)((uint16_t)data[0] << 8 | data[1]);
}

bool lfj8_h03_raw_load_config_valid(const Lfj8H03RawLoadConfig *config)
{
    return config && config->max_age_us && config->max_age_us < HALF_RANGE &&
        config->bit_time_us && config->max_can_age_bits && config->max_can_age_bits < 0x8000u &&
        config->producer_bound_us && config->producer_bound_us < config->max_age_us &&
        (uint32_t)config->max_can_age_bits * config->bit_time_us <
            config->max_age_us - config->producer_bound_us;
}

void lfj8_h03_raw_load_reset(Lfj8H03RawLoadRx *rx, uint32_t enabled_at_us)
{
    *rx = (Lfj8H03RawLoadRx){.enabled_at_us = enabled_at_us, .enabled = true};
}

static bool current(const Lfj8H03RawLoadRx *rx, uint32_t sensor_epoch, uint32_t can_generation)
{
    return rx->seen && rx->sensor_epoch == sensor_epoch && rx->can_generation == can_generation;
}

Lfj8H03RawLoadResult lfj8_h03_raw_load_receive_basic(
    Lfj8H03RawLoadRx *rx, const Lfj8H03RawLoadConfig *config, const uint8_t slot[16],
    uint8_t control, bool extended, uint32_t sensor_epoch, uint32_t can_generation,
    uint32_t now_us, uint16_t can_now)
{
    /* ID bit distribution follows the existing H03 BasicCAN 1F3F mask. */
    if (!slot || extended || (be16(slot) & 0x1f3fu) !=
        ((LFJ8_H03_BOSCH_RAW_LOAD_ID >> 6) << 8 | (LFJ8_H03_BOSCH_RAW_LOAD_ID & 0x3fu))) {
        return LFJ8_H03_RAW_LOAD_OTHER;
    }
    if (!rx || !rx->enabled) {
        return LFJ8_H03_RAW_LOAD_REJECTED;
    }
    const uint8_t flags = slot[6];
    const uint16_t divisor = be16(&slot[10]);
    if (!lfj8_h03_raw_load_config_valid(config) || control != 0x41u ||
        (slot[5] & 0x0fu) != 8u || !divisor ||
        (flags & ~(LFJ8_H03_BOSCH_RAW_A88B_0 | LFJ8_H03_BOSCH_RAW_T2_5)) !=
            (LFJ8_H03_BOSCH_RAW_LOAD_V1 | LFJ8_H03_BOSCH_RAW_VALID)) {
        rx->valid = false;
        return LFJ8_H03_RAW_LOAD_REJECTED;
    }
    const uint16_t age_bits = (uint16_t)(can_now - be16(&slot[14]));
    if (age_bits >= config->max_can_age_bits) {
        return LFJ8_H03_RAW_LOAD_REJECTED;
    }
    /* Include one CAN clock tick of uncertainty in the earliest RX time. */
    const uint32_t received_at = now_us - ((uint32_t)age_bits + 1u) * config->bit_time_us;
    const uint32_t oldest = received_at - config->producer_bound_us;
    if (!rx->seen && received_at - rx->enabled_at_us >= HALF_RANGE) {
        return LFJ8_H03_RAW_LOAD_REJECTED;
    }
    if (current(rx, sensor_epoch, can_generation)) {
        const uint32_t advance = received_at - rx->received_at_us;
        const uint8_t steps = (uint8_t)(slot[7] - rx->sample.sequence);
        if (advance == 0u || advance >= HALF_RANGE ||
            (now_us - rx->sample.oldest_us < config->max_age_us && (steps == 0u || steps >= 128u))) {
            return LFJ8_H03_RAW_LOAD_REJECTED;
        }
    }
    rx->sample = (Lfj8H03RawLoadSample){
        .load_f8d6 = be16(&slot[8]),
        .divisor_f4686 = divisor,
        .model_9680 = be16(&slot[12]),
        .source_bits = (uint8_t)(flags & (LFJ8_H03_BOSCH_RAW_A88B_0 | LFJ8_H03_BOSCH_RAW_T2_5)),
        .sequence = slot[7],
        .oldest_us = oldest,
    };
    rx->sensor_epoch = sensor_epoch;
    rx->can_generation = can_generation;
    rx->received_at_us = received_at;
    rx->seen = true;
    rx->valid = true;
    return LFJ8_H03_RAW_LOAD_RECEIVED;
}

const Lfj8H03RawLoadSample *lfj8_h03_raw_load_snapshot(
    const Lfj8H03RawLoadRx *rx, const Lfj8H03RawLoadConfig *config,
    uint32_t sensor_epoch, uint32_t can_generation, uint32_t now_us)
{
    return rx && rx->valid && lfj8_h03_raw_load_config_valid(config) &&
        current(rx, sensor_epoch, can_generation) &&
        now_us - rx->sample.oldest_us < config->max_age_us ? &rx->sample : 0;
}
