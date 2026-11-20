/* Replace the entry word at 0x00C34C with a wide BRA to this routine.
 * Bind h03_tx_writer_resume to OEM 0x00C350 and h03_can_owner to the
 * application's initialized owner. The foreground owner is serialized
 * with the OEM foreground caller and masks CAN0 IRQ when granting TX13.
 * The fence continues to exclude the writer after software lease loss
 * until the outgoing slot is known to be idle. */
#include "lfj8_h03_can_owner.h"

    .section .text.h03_can13_tx_gate,"ax",@progbits
    .p2align 2
    .global h03_can13_tx_gate
h03_can13_tx_gate:
    push r0
    push r1
    mvfc r0,psw
    push r0
    ld24 r1,#h03_can_owner
    ldub r0,@(LFJ8_CAN_OWNER_TX13_FENCE_OFFSET,r1)
    bnez r0,.Lgrant_held
    ldub r0,@(LFJ8_CAN_OWNER_GRANT_OFFSET,r1)
    ldi r1,#1
    beq r0,r1,.Lgrant_held

    pop r0
    mvtc r0,psw
    pop r1
    pop r0
    /* Replay the displaced OEM entry instructions, including their packet. */
    .long 0x2E7F2A7F
    bra h03_tx_writer_resume

    .p2align 2
.Lgrant_held:
    pop r0
    mvtc r0,psw
    pop r1
    pop r0
    jmp lr
