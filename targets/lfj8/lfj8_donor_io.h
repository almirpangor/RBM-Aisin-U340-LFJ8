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
} Lfj8RawCapture;

typedef Lfj8RawCapture Lfj8RawVss;

typedef struct {
    Lfj8CaptureSnapshot vss;
    Lfj8CaptureSnapshot nt;
    uint32_t now_tml0;
    uint32_t vss_at_tml0;
    uint32_t nt_at_tml0;
    uint32_t nt_edge_tml1;
    uint16_t nt_alignment_error_ticks;
} Lfj8CapturePair;

typedef enum {
    LFJ8_CAN_SUBMITTED,
    LFJ8_CAN_SLOT_BUSY,
    LFJ8_CAN_CONTROLLER_UNAVAILABLE,
    LFJ8_CAN_SLOT_NOT_STANDARD,
    LFJ8_CAN_WRONG_FRAME,
    LFJ8_CAN_SLOT_NOT_OWNED,
} Lfj8CanResult;

typedef struct {
    uint16_t id;
    uint16_t timestamp;
    uint8_t payload[8];
} Lfj8CanData8;

typedef enum {
    LFJ8_CAN_RX_RECEIVED,
    LFJ8_CAN_RX_IDLE,
    LFJ8_CAN_RX_RETRY,
    LFJ8_CAN_RX_LOST,
    LFJ8_CAN_RX_BAD_LENGTH,
    LFJ8_CAN_RX_UNAVAILABLE,
    LFJ8_CAN_RX_WRONG_SLOT,
} Lfj8CanRxResult;

/* Call with the 9E1B address map bound and producer interrupts maskable. */
Lfj8CaptureSnapshot lfj8_9e1b_capture_snapshot(const Lfj8RegisterIo *io);
/* OEM interval, pulse window and freshness from the selected 9E1C software. */
Lfj8CaptureSnapshot lfj8_9e1c_capture_snapshot(const Lfj8RegisterIo *io);

/* Initialize before subscribing to the one-positive-edge TIN23 producer. */
void lfj8_9e1b_raw_vss_init(volatile Lfj8RawVss *vss);
/* Hook after OEM has read and acknowledged the capture. No new SFR writes. */
void lfj8_9e1b_raw_vss_edge(volatile Lfj8RawVss *vss, uint32_t captured_ticks,
                           uint32_t timeout_ticks);
/* Read private capture state and live TML0CT in one critical section. */
Lfj8CaptureSnapshot lfj8_9e1b_raw_vss_snapshot(volatile Lfj8RawVss *vss,
                                             const Lfj8RegisterIo *io,
                                             uint32_t timeout_ticks);

void lfj8_9e1c_raw_vss_init(volatile Lfj8RawVss *vss);
/* Run once from the confirmed TIN23 branch after the 0x00AA0C store,
 * with the OEM producer lock held. read32 reads the published timestamp.
 * The caller still runs the OEM update and interrupt acknowledgement.
 */
void lfj8_9e1c_raw_vss_after_capture_store(volatile Lfj8RawVss *vss,
                                         const Lfj8RegisterIo *io,
                                         uint32_t timeout_ticks);
/* Both verified versions use TML0CT at 0x8003E0 for the live timer. */
Lfj8CaptureSnapshot lfj8_raw_vss_snapshot(volatile Lfj8RawVss *vss,
                                         const Lfj8RegisterIo *io,
                                         uint32_t timeout_ticks);

void lfj8_9e1c_raw_nt_init(volatile Lfj8RawCapture *nt);
/* Call once after the H03 S83 store at 0x00AA70 with its producer lock held.
 * Run the normal OEM update and interrupt acknowledgement as usual. */
void lfj8_9e1c_raw_nt_after_capture_store(volatile Lfj8RawCapture *nt,
                                        const Lfj8RegisterIo *io, uint32_t timeout_ticks);
/* One S83 edge interval in TML1CT ticks. Confirm the physical edges per
 * revolution and timer frequency separately before converting to RPM. */
Lfj8CaptureSnapshot lfj8_9e1c_raw_nt_snapshot(volatile Lfj8RawCapture *nt,
                                            const Lfj8RegisterIo *io, uint32_t timeout_ticks);

/* Use on H03 where TML0 and TML1 run from the same clock bus. Convert both
 * edge times to the TML0 epoch and reject an excessively wide counter read. */
int lfj8_h03_capture_pair(volatile Lfj8RawVss *vss, volatile Lfj8RawCapture *nt,
                          const Lfj8RegisterIo *io, uint32_t vss_timeout_ticks,
                          uint32_t nt_timeout_ticks, uint16_t max_read_span_ticks,
                          Lfj8CapturePair *pair);

/* Submission only. The owner checks completion separately. */
Lfj8CanResult lfj8_can0_slot13_submit(const Lfj8RegisterIo *io, uint8_t slot13_owned,
                                     uint16_t id, const uint8_t payload[8]);

/* Poll a caller-owned 32176 FullCAN slot (0..13) configured to receive standard data frames.
 * The hardware timestamp stays in the CAN counter's 16-bit clock domain.
 * A lost message or a receive during the copy invalidates the copy. */
Lfj8CanRxResult lfj8_can0_receive8(const Lfj8RegisterIo *io, uint8_t slot, uint8_t slot_owned,
                                 Lfj8CanData8 *frame);

enum {
    LFJ8_H03_CAN0_RPM_SLOT = 11,
    LFJ8_H03_CAN0_COOLANT_SLOT = 12,
};

/* Run after stock CAN initialization or reinitialization in approved H03,
 * with exclusive polling ownership of both confirmed idle slots. */
int lfj8_h03_can0_arm_engine_rx(const Lfj8RegisterIo *io, uint8_t slots_owned);

/* Read the 16-bit CAN0 clock when the H03 owner is operational (state 6 or 7)
 * and the controller runs in the one-count-per-bit mode. */
int lfj8_h03_can0_read_timestamp(const Lfj8RegisterIo *io, uint16_t *timestamp);

#endif
