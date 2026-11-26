/* H03 output fault latches, entered by BRA. All four OEM sites set r0=1
 * and write through r4. Use r0 for the continuation until replay is done. */

    .section .text.rbm_h03_slt_fault_hook,"ax",@progbits
    .macro fault_site name
    .p2align 2
    .global rbm_h03_\name\()_fault_hook
rbm_h03_\name\()_fault_hook:
    ld24 r0,#.L\name\()_resume
    bra .Llatch
    .p2align 2
.L\name\()_resume:
    ldi r0,#1
    bra h03_\name\()_fault_resume
    .endm

    fault_site slt
    fault_site shift_d
    fault_site shift_e
    fault_site shift_f

    .p2align 2
.Llatch:
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
    jmp r0
