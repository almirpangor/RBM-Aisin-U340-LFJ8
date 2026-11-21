#ifndef RBM_LFJ8_H03_LOAD_RAW_H
#define RBM_LFJ8_H03_LOAD_RAW_H

#include <stdbool.h>
#include <stdint.h>

/* RBM first-bench extension. Chery arbitration IDs and payloads are unchanged. */
enum {
    LFJ8_H03_BOSCH_RAW_LOAD_ID = 0x6b2,
    LFJ8_H03_BOSCH_RAW_LOAD_V1 = 0x10,
    LFJ8_H03_BOSCH_RAW_A88B_0 = 0x01,
    LFJ8_H03_BOSCH_RAW_T2_5 = 0x02,
    LFJ8_H03_BOSCH_RAW_VALID = 0x04,
};

typedef struct {
    uint32_t max_age_us;         /* Exclusive lifetime of the oldest source. */
    uint32_t producer_bound_us;  /* Worst case from the oldest producer store to RX timestamp. */
    uint16_t max_can_age_bits;   /* Exclusive limit of the 16-bit hardware timestamp difference. */
    uint16_t bit_time_us;        /* CAN timestamp period in qualified TML0 microseconds. */
} Lfj8H03RawLoadConfig;

typedef struct {
    uint16_t load_f8d6;
    uint16_t divisor_f4686;
    uint16_t model_9680;
    uint8_t source_bits; /* Bosch A88B.0 and T2.5; these are not Toyota mode bits. */
    uint8_t sequence;
    uint32_t oldest_us;
} Lfj8H03RawLoadSample;

typedef struct {
    Lfj8H03RawLoadSample sample;
    uint32_t sensor_epoch;
    uint32_t can_generation;
    uint32_t enabled_at_us;
    uint32_t received_at_us; /* Conservative hardware RX timestamp, without producer bound. */
    bool enabled;
    bool seen;
    bool valid;
} Lfj8H03RawLoadRx;

typedef enum {
    LFJ8_H03_RAW_LOAD_OTHER,
    LFJ8_H03_RAW_LOAD_REJECTED,
    LFJ8_H03_RAW_LOAD_RECEIVED,
} Lfj8H03RawLoadResult;

bool lfj8_h03_raw_load_config_valid(const Lfj8H03RawLoadConfig *config);
void lfj8_h03_raw_load_reset(Lfj8H03RawLoadRx *rx, uint32_t enabled_at_us);

/* Consume the OEM owner's stable 16-byte BasicCAN copy, with TRFIN held.
 * The clock pair is from this capture: now_us is the earlier TML0 bound
 * around CAN0TSTMP. Publishers/readers must share the native IRQ exclusion.
 * The CAN owner drains the slot at admission and bounds residence to less
 * than half a CAN timestamp wrap. This code never writes or acknowledges CAN. */
Lfj8H03RawLoadResult lfj8_h03_raw_load_receive_basic(
    Lfj8H03RawLoadRx *rx, const Lfj8H03RawLoadConfig *config, const uint8_t slot[16],
    uint8_t control, bool extended, uint32_t sensor_epoch, uint32_t can_generation,
    uint32_t now_us, uint16_t can_now);

/* On failure returns NULL. The pointer is valid only under the same IRQ lock. */
const Lfj8H03RawLoadSample *lfj8_h03_raw_load_snapshot(
    const Lfj8H03RawLoadRx *rx, const Lfj8H03RawLoadConfig *config,
    uint32_t sensor_epoch, uint32_t can_generation, uint32_t now_us);

#endif
