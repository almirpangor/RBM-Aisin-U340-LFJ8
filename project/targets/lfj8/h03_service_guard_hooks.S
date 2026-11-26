/* H03 2924/294C/2D1C/2E9C only. The address model binds stock continuation
 * symbols and verifies all displaced words against the pinned ROM.
 * The entire bounded writer runs with maskable IRQs disabled, including
 * the guard and original stores. Caller PSW and callee-saved registers
 * are restored. SBI/DMA and physical execution time remain separate gates. */
    .section .text.rbm_h03_service_hooks,"ax",@progbits
    .p2align 2
    .global rbm_h03_service_direct_hook
rbm_h03_service_direct_hook:
    push lr
    push r8
    mvfc r8,psw
    clrpsw #0x40
    bl .Ldirect_original
    mvtc r8,psw
    pop r8
    pop lr
    jmp lr
.Ldirect_original:
    push lr -> addi sp,#-8
    bra.l h03_service_direct_after_entry

    .p2align 2
    .global rbm_h03_service_span_hook
rbm_h03_service_span_hook:
    push lr
    .irp reg,r0,r1,r2,r3,r4,r5,r6,r7
    push \reg
    .endr
    and3 r2,r1,#0xff
    mv r1,r0
    ld24 r0,#rbm_h03_service_policy
    bl lfj8_h03_service_span_allowed
    beqz r0,.Lspan_denied
    .irp reg,r7,r6,r5,r4,r3,r2,r1,r0
    pop \reg
    .endr
    pop lr
    bra.l h03_service_stock_span_check
.Lspan_denied:
    .irp reg,r7,r6,r5,r4,r3,r2,r1
    pop \reg
    .endr
    addi sp,#4
    pop lr
    ldi r0,#0
    jmp lr

    .p2align 2
    .global rbm_h03_service_copy_hook
rbm_h03_service_copy_hook:
    push lr
    push r8
    mvfc r8,psw
    clrpsw #0x40
    .irp reg,r0,r1,r2,r3,r4,r5,r6,r7
    push \reg
    .endr
    ld24 r0,#rbm_h03_service_policy
    ld24 r4,#0x808578
    ld r1,@(16,r4)
    ld r2,@(2100,r4)
    ld r3,@(2096,r4)
    bl lfj8_h03_service_copy_allowed
    beqz r0,.Lcopy_held
    .irp reg,r7,r6,r5,r4,r3,r2,r1,r0
    pop \reg
    .endr
    bl .Lcopy_original
    bra .Lcopy_return
.Lcopy_held:
    /* Return the stock busy indication. Keep all pending state unchanged;
     * no completion/positive acknowledgement and no partial copy occurs.
     * The accepted session-close path below retires a held operation. */
    .irp reg,r7,r6,r5,r4,r3,r2,r1
    pop \reg
    .endr
    addi sp,#4
    ldi r0,#1
.Lcopy_return:
    mvtc r8,psw
    pop r8
    pop lr
    jmp lr
.Lcopy_original:
    push lr -> push r9
    bra.l h03_service_copy_after_entry

    /* Only the accepted OEM close path reaches this final flag store. R0
     * holds its stock flags and R10 points to the resident monitor state. */
    .p2align 2
    .global rbm_h03_service_close_hook
rbm_h03_service_close_hook:
    push lr
    push r8
    mvfc r8,psw
    clrpsw #0x40
    .irp reg,r0,r1,r2,r3,r4,r5,r6,r7
    push \reg
    .endr
    ld r3,@(2096,r10)
    beqz r3,.Lclose_restore
    ld24 r0,#rbm_h03_service_policy
    ld r1,@(16,r10)
    ld r2,@(2100,r10)
    bl lfj8_h03_service_copy_allowed
    bnez r0,.Lclose_restore
    /* Zero the pending and original counts without entering the copy
     * completion path. The independent checksum and its cursor survive. */
    st r0,@(2096,r10)
    st r0,@(2100,r10)
.Lclose_restore:
    .irp reg,r7,r6,r5,r4,r3,r2,r1,r0
    pop \reg
    .endr
    stb r0,@(8,r10)
    mvtc r8,psw
    pop r8
    pop lr
    bra.l h03_service_close_after_store
