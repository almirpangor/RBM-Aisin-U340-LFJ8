#ifndef RBM_LFJ8_H03_CAN_OWNER_H
#define RBM_LFJ8_H03_CAN_OWNER_H

#define LFJ8_CAN_OWNER_SETUP_GENERATION_OFFSET 0
#define LFJ8_CAN_OWNER_GRANT_OFFSET 4

#ifndef __ASSEMBLER__
#include "lfj8_h03_dtc_foreground.h"

typedef struct {
    volatile uint32_t setup_generation; /* Incremented by native setup. */
    volatile uint8_t grant;              /* Read by OEM TX gate and CAN0 IRQ. */
    bool initialized;
    uint32_t admitted_generation;       /* Last generation granted to the broker. */
} Lfj8H03CanOwner;

/* The application/linker binds this symbol to its single CAN owner. */
extern Lfj8H03CanOwner h03_can_owner;

/* Cold startup, before native setup/IRQ can reference the owner. Initialize
 * the RX queue separately; neither component clears hardware during init. */
void lfj8_h03_can_owner_init(Lfj8H03CanOwner *owner);

/* Call from the serialized CAN0 RX callback before publishing to the queue.
 * If this fails, leave acknowledgement and any retry to the OEM handler. */
bool lfj8_h03_can_owner_rx_epoch(const Lfj8H03CanOwner *owner, uint32_t *generation);

/* One foreground caller, serialized with the native setup and OEM foreground
 * writer. io enter/leave must mask CAN0 IRQ and support nesting. native_ready
 * means that the OEM setup tail completed and the TX13 gate is installed.
 * Pair can_now with input->now_us in the application's shared clock domain.
 * The caller supplies diagnostic_tick in the diagnostic timer's own domain.
 * The owner overrides input->generation and input->owns_slot13 for the
 * broker call and restores them before returning. */
Lfj8H03Can13Result lfj8_h03_can_owner_poll(
    Lfj8H03CanOwner *owner, Lfj8H03Can13 *broker, Lfj8H03DtcRxQueue *queue,
    const Lfj8RegisterIo *io, Lfj8H03Can13Input *input, const uint16_t *can_now,
    bool native_ready);
#endif

#endif
