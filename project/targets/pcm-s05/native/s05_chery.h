#ifndef RBM_S05_CHERY_H
#define RBM_S05_CHERY_H

#include "lfj8_bridge.h"

typedef struct {
    Lfj8CherySchedule schedule;
    uint8_t pending;
    uint8_t last_submitted;
    uint8_t counter_f8e4;
} S05CheryTransport;

typedef struct {
    Lfj8Chery1ae status_1ae;
    uint16_t speed_raw;
    int16_t atf_c;
    uint8_t status0_300;
    uint8_t status1_300;
    uint8_t flag_fd18_9;
    uint8_t atf_valid;
} S05CheryInputs;

/* Copy all eight bytes before returning. A zero result queues no frame. */
typedef uint8_t (*S05CanSubmit)(void *channel, uint16_t std_id, const uint8_t payload[8]);

void s05_chery_init(S05CheryTransport *transport, uint32_t now_us,
                    uint32_t period_1ae_us, uint32_t period_300_us);

/* Returns LFJ8_DUE_1AE or LFJ8_DUE_300 after the callback accepts the frame. */
uint8_t s05_chery_poll(S05CheryTransport *transport, uint32_t now_us,
                      const S05CheryInputs *inputs, S05CanSubmit submit, void *channel);

#endif
