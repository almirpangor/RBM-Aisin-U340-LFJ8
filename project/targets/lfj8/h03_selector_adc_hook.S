/* H03 0x040370 (2024 6103): enter by BRA with the OEM registers intact.
 * After the OEM AN2 store, call rbm_h03_selector_adc_capture(uint16_t raw)
 * with IE clear. The application supplies the C ABI callback and owns the
 * clock and mailbox. The callback must preserve the current stack mode.
 */
    .section .text.rbm_h03_selector_adc_hook,"ax",@progbits
    .p2align 2
    .global rbm_h03_selector_adc_hook
rbm_h03_selector_adc_hook:
    push lr
    .irp reg,r0,r2,r3,r4,r5,r6,r7
    push \reg
    .endr
    mvfc r7,psw
    clrpsw #0x40
    push r7
    mvfachi r7
    push r7
    mvfaclo r7
    push r7

    sth r0,@r4
    bl rbm_h03_selector_adc_capture

    pop r7
    mvtaclo r7
    pop r7
    mvtachi r7
    /* The OEM bundle overwrites r1. Restore IE after releasing the frame. */
    pop r1
    .irp reg,r7,r6,r5,r4,r3,r2,r0
    pop \reg
    .endr
    pop lr

    mvtc r1,psw
    ldi r1,#3
    bra h03_selector_adc_resume
