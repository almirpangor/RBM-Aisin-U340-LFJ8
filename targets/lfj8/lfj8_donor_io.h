#ifndef RBM_LFJ8_DONOR_IO_H
#define RBM_LFJ8_DONOR_IO_H

#include <stdint.h>

typedef struct {
    void *context;
    uint8_t (*read8)(void *context, uint32_t address);
    uint16_t (*read16)(void *context, uint32_t address);
    uint32_t (*read32)(void *context, uint32_t address);
    void (*write8)(void *context, uint32_t address, uint8_t value);
    uint32_t (*enter)(void *context);
    void (*leave)(void *context, uint32_t saved_state);
} Lfj8RegisterIo;

typedef struct {
    uint32_t interval_ticks;
    uint16_t pulse_window;
    uint8_t state; /* LFJ8_VSS_VALID or LFJ8_VSS_UNAVAILABLE. */
} Lfj8CaptureSnapshot;

typedef struct {
    uint32_t last_edge;
    uint32_t interval_ticks;
    uint8_t primed;
} Lfj8RawVss;

typedef enum {
    LFJ8_CAN_SUBMITTED,
    LFJ8_CAN_SLOT_BUSY,
    LFJ8_CAN_CONTROLLER_UNAVAILABLE,
    LFJ8_CAN_SLOT_NOT_STANDARD,
    LFJ8_CAN_WRONG_FRAME,
    LFJ8_CAN_SLOT_NOT_OWNED,
} Lfj8CanResult;

/* Call with the 9E1B address map bound and producer interrupts maskable. */
Lfj8CaptureSnapshot lfj8_9e1b_capture_snapshot(const Lfj8RegisterIo *io);

/* Initialize before subscribing to the one-positive-edge TIN23 producer. */
void lfj8_9e1b_raw_vss_init(volatile Lfj8RawVss *vss);
/* Hook after OEM has read and acknowledged the capture. No new SFR writes. */
void lfj8_9e1b_raw_vss_edge(volatile Lfj8RawVss *vss, uint32_t captured_ticks,
                           uint32_t timeout_ticks);
/* Read private capture state and live TML0CT in one critical section. */
Lfj8CaptureSnapshot lfj8_9e1b_raw_vss_snapshot(volatile Lfj8RawVss *vss,
                                             const Lfj8RegisterIo *io,
                                             uint32_t timeout_ticks);

/* Submission only. The owner checks completion separately. */
Lfj8CanResult lfj8_can0_slot13_submit(const Lfj8RegisterIo *io, uint8_t slot13_owned,
                                     uint16_t id, const uint8_t payload[8]);

#endif
