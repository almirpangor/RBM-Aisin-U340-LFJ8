/* Enter by BRA at H03 0x001534, with IE already masked by the OEM.
 * The callback takes the RX slot in R0 and obeys the M32R C ABI.
 * OEM alone acknowledges TRFIN and decides whether to retry. */

    .equ rx_saved_r0,40

    .macro save_rx_context
    push lr
    .irp reg,r0,r1,r2,r3,r4,r5,r6,r7
    push \reg
    .endr
    mvfc r0,psw
    push r0
    mvfachi r0
    push r0
    mvfaclo r0
    push r0
    .endm

    .macro restore_rx_context high_label
    pop r0
    mvtaclo r0
    pop r0
\high_label:
    mvtachi r0
    pop r0
    mvtc r0,psw
    .irp reg,r7,r6,r5,r4,r3,r2,r1,r0
    pop \reg
    .endr
    pop lr
    .endm

    .section .text.rbm_h03_dtc_rx_hook,"ax",@progbits
    .p2align 2
    .global rbm_h03_dtc_rx_hook
    .type rbm_h03_dtc_rx_hook,@function
rbm_h03_dtc_rx_hook:
    save_rx_context
    and3 r0,r8,#0xff
    bl rbm_h03_dtc_rx_observe
    restore_rx_context rbm_h03_dtc_rx_restore_high
    and3 r0,r8,#0xff
    bra h03_dtc_rx_resume
    .size rbm_h03_dtc_rx_hook,.-rbm_h03_dtc_rx_hook

/* Replace the OEM BL at 0x004738. R0 holds the original CAN0SLIST.
 * Restore the call-site context, then tail-call OEM with LR still 0x00473c. */
    .section .text.rbm_h03_dtc_rx_dispatch_hook,"ax",@progbits
    .p2align 2
    .global rbm_h03_dtc_rx_dispatch_hook
    .type rbm_h03_dtc_rx_dispatch_hook,@function
rbm_h03_dtc_rx_dispatch_hook:
    save_rx_context
    clrpsw #0x40
    ld r0,@(rx_saved_r0,sp)
    bl rbm_h03_dtc_rx_begin
    restore_rx_context rbm_h03_dtc_rx_dispatch_restore_high
    bra h03_dtc_rx_entry
    .size rbm_h03_dtc_rx_dispatch_hook,.-rbm_h03_dtc_rx_dispatch_hook
