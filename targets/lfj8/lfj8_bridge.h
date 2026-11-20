#ifndef RBM_LFJ8_BRIDGE_H
#define RBM_LFJ8_BRIDGE_H

#include <stdint.h>

enum {
    LFJ8_VSS_UNAVAILABLE = 0,
    LFJ8_VSS_VALID = 1,
    LFJ8_VSS_STOPPED = 2,
    LFJ8_SPEED_UNAVAILABLE = 0xFFFF,
    LFJ8_SPEED_WRAP = 51200,
    LFJ8_CAN_1AE = 0x1AE,
    LFJ8_CAN_300 = 0x300,
    LFJ8_DUE_1AE = 1,
    LFJ8_DUE_300 = 2,
    LFJ8_REVERSE_RELAY = 1,
    LFJ8_AUX_RELAY = 2,
};

typedef struct {
    uint8_t byte1;
    uint8_t byte3_high;
    uint8_t byte4;
    uint8_t raw_fa5f;
    uint8_t raw_f8e1;
    uint8_t counter_f8e4;
    uint8_t flag_f842_5;
    uint8_t flag_fd18_4;
    uint8_t flag_fd10_7;
    uint8_t flag_f83e_4;
    uint8_t flag_e026_0;
} Lfj8Chery1ae;

typedef struct {
    uint32_t last_1ae_us;
    uint32_t last_300_us;
    uint32_t period_1ae_us;
    uint32_t period_300_us;
} Lfj8CherySchedule;

/* Coherent capture from one producer update. Pulse count is 1, 2 or 4. */
uint16_t lfj8_vss_raw_1ae(uint32_t ticks, uint8_t pulse_count, uint32_t tick_hz,
                        uint32_t wheel_um, uint16_t wheel_num, uint16_t wheel_den,
                        uint8_t capture_state);

/* Returns the next F8E4 counter. Flag bytes use 0 or 1. */
uint8_t lfj8_pack_1ae(uint8_t out[8], const Lfj8Chery1ae *status, uint16_t speed_raw);
uint8_t lfj8_pack_1ae_with_counter(uint8_t out[8], const Lfj8Chery1ae *status,
                                  uint16_t speed_raw, uint8_t previous_counter);
void lfj8_pack_300(uint8_t out[8], uint8_t byte0, uint8_t byte1, uint8_t flag_fd18_9,
                   int16_t atf_c, uint8_t atf_valid);

/* Start one period from now. A zero period disables the corresponding frame. */
void lfj8_schedule_init(Lfj8CherySchedule *schedule, uint32_t now_us,
                        uint32_t period_1ae_us, uint32_t period_300_us);
/* Coalesces missed periods and preserves phase. Call within one uint32_t wrap. */
uint8_t lfj8_schedule_poll(Lfj8CherySchedule *schedule, uint32_t now_us);

/* Takes a decoded selector, using ASCII R and L. */
uint8_t lfj8_relay_mask(uint8_t selector);

#endif
