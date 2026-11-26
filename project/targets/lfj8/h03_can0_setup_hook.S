/* Replace either wide BL to OEM CAN setup with a BL to this entry.
 * The linker binds h03_oem_can0_setup to the original 0x00BAF4 entry
 * and supplies the shared h03_can_owner object initialized by the application.
 * The foreground owner must verify or drain BasicCAN and defer capture
 * and TX13 regrant until the OEM tail completes. */

#include "lfj8_h03_can_owner.h"

    .section .text.h03_can0_setup_hook,"ax",@progbits
    .p2align 2
    .global h03_can0_setup_hook
h03_can0_setup_hook:
    push lr
    push r0
    push r1
    ld24 r0,#h03_can_owner
    ldi r1,#0
    stb r1,@(LFJ8_CAN_OWNER_GRANT_OFFSET,r0)
    pop r1
    pop r0
    bl h03_oem_can0_setup

    /* Captures during setup still belong to the discarded generation. */
    push r0
    push r1
    push r2
    mvfc r2,psw
    clrpsw #0x40
    ld24 r0,#h03_can_owner
    ld r1,@(LFJ8_CAN_OWNER_SETUP_GENERATION_OFFSET,r0)
    addi r1,#1
    st r1,@(LFJ8_CAN_OWNER_SETUP_GENERATION_OFFSET,r0)
    mvtc r2,psw
    pop r2
    pop r1
    pop r0
    pop lr
    jmp lr
