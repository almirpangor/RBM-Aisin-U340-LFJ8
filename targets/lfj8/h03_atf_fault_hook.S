/* Replace the aligned BL at 0x0725B0. The link supplies the pinned
 * OEM monitor at 0x0753A4. The incoming LR is the OEM continuation.
 * Keep the native post-call register, PSW and accumulator state. */
    .section .text.rbm_h03_atf_fault_hook,"ax",@progbits
    .p2align 2
    .global rbm_h03_atf_fault_hook
    .type rbm_h03_atf_fault_hook,@function
rbm_h03_atf_fault_hook:
    push lr
    bl h03_oem_atf_circuit_monitor

    .irp reg,r0,r1,r2,r3,r4,r5,r6,r7
    push \reg
    .endr
    mvfc r7,psw
    clrpsw #0x40
    push r7
    mvfachi r7
    push r7
    mvfaclo r7
    push r7

    ld24 r0,#lfj8_h03_mmio
    bl lfj8_h03_atf_circuit_after_monitor
    bl rbm_h03_dtc_atf_capture

    pop r7
    mvtaclo r7
    pop r7
    mvtachi r7
    pop r7
    mvtc r7,psw
    .irp reg,r7,r6,r5,r4,r3,r2,r1,r0
    pop \reg
    .endr
    pop lr
    jmp lr
    .size rbm_h03_atf_fault_hook,.-rbm_h03_atf_fault_hook
