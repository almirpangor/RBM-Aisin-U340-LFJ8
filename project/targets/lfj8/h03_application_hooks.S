/* H03 application entry at 008100 and foreground input call at 00816C.
 * Bind the continuation and original call destination to the pinned H03. */
    .macro save_context
    .irp reg,r0,r1,r2,r3,r4,r5,r6,r7,r8,r9,r10,r11,r12,r13
    push \reg
    .endr
    mvfc r0,psw
    push r0
    mvfachi r0
    push r0
    mvfaclo r0
    push r0
    .endm

    .macro restore_context
    pop r0
    mvtaclo r0
    pop r0
    mvtachi r0
    pop r0
    and3 r0,r0,#1
    ldi r1,#0
    cmpu r1,r0
    .irp reg,r13,r12,r11,r10,r9,r8,r7,r6,r5,r4,r3,r2,r1,r0
    pop \reg
    .endr
    .endm

    .section .text.rbm_h03_application_cold_hook,"ax",@progbits
    .p2align 2
    .global rbm_h03_application_cold_hook
    .type rbm_h03_application_cold_hook,@function
rbm_h03_application_cold_hook:
    push lr
    save_context
    bl rbm_h03_application_cold_gate
    restore_context
    pop lr
    /* Displaced OEM word: save the caller's LR and allocate one local. */
    push lr -> addi sp,#-4
    bra.l h03_stock_application_after_entry
    .size rbm_h03_application_cold_hook,.-rbm_h03_application_cold_hook

    .section .text.rbm_h03_application_foreground_hook,"ax",@progbits
    .p2align 2
    .global rbm_h03_application_foreground_hook
    .type rbm_h03_application_foreground_hook,@function
rbm_h03_application_foreground_hook:
    push lr
    bl.l h03_stock_foreground_inputs
    save_context
    bl rbm_h03_application_foreground_callback
    restore_context
    pop lr
    jmp lr
    .size rbm_h03_application_foreground_hook,.-rbm_h03_application_foreground_hook
