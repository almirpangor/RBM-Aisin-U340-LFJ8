/* Replace the first word of the H03 DMA4 setter at 0x00CF0C with BRA.l.
 * This also covers callers using the unchanged OEM dispatch table. */
    .section .text.rbm_h03_dma4_guard,"ax",@progbits
    .p2align 2
    .global rbm_h03_dma4_guard
    .type rbm_h03_dma4_guard,@function
rbm_h03_dma4_guard:
    push lr
    push r8
    mvfc r8,psw
    clrpsw #0x40
    .irp reg,r0,r1,r2,r3,r4,r5,r6,r7
    push \reg
    .endr

    /* OEM writes (R0 - 1) to the 8-bit count register and the low half
     * of R1 to the destination register. 0xff encodes 256 byte transfers. */
    addi r0,#-1
    and3 r2,r0,#0xff
    addi r2,#1
    and3 r1,r1,#0xffff
    ld24 r3,#0x800000
    or r1,r3
    mv r4,r1
    add r4,r2
    ld24 r3,#0x810000
    cmpu r3,r4
    bc .Ldma4_deny
    ld24 r0,#rbm_h03_service_policy
    bl lfj8_h03_service_span_allowed
    beqz r0,.Ldma4_deny

    .macro restore_dma4_context
    .irp reg,r7,r6,r5,r4,r3,r2,r1,r0
    pop \reg
    .endr
    mvtc r8,psw
    pop r8
    pop lr
    .endm

    restore_dma4_context
    push lr -> push r10
    bra.l h03_dma4_after_entry
.Ldma4_deny:
    /* The stock setter returns no result. Leave the previous channel
     * configuration and SIO0 registers intact when refusing a new write. */
    restore_dma4_context
    jmp lr
    .size rbm_h03_dma4_guard,.-rbm_h03_dma4_guard
