/* Candidate hook at H03 03484C, entered by BRA. Replay the OEM latch
 * store under exclusion, then revoke through the application owner. */

    .section .text.rbm_h03_slt_fault_hook,"ax",@progbits
    .p2align 2
    .global rbm_h03_slt_fault_hook
rbm_h03_slt_fault_hook:
    push lr
    .irp reg,r0,r1,r2,r3,r4,r5,r6,r7
    push \reg
    .endr
    mvfc r7,psw
h03_slt_fault_mask_irq:
    clrpsw #0x40
    push r7
    mvfachi r7
    push r7
    mvfaclo r7
    push r7

    ldi r0,#1
    stb r0,@r4
    ld24 r0,#rbm_h03_takeover_state
    bl lfj8_h03_takeover_revoke_locked

    pop r7
    mvtaclo r7
    pop r7
    mvtachi r7
    pop r7
h03_slt_fault_restore_irq:
    mvtc r7,psw
    .irp reg,r7,r6,r5,r4,r3,r2,r1,r0
    pop \reg
    .endr
    pop lr
    ldi r0,#1
    bra h03_slt_fault_resume
