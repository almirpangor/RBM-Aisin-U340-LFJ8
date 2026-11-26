/* Replace the stock store bundle via a long BRA in the address model.
 * Resume symbols are resolved by the linker to 0x00AA10 and 0x00AA74. */
    .section .text.rbm_h03_sensor_hooks,"ax",@progbits

    .macro sensor_hook name, source, destination
    .p2align 2
    .global rbm_h03_\name\()_capture_hook
rbm_h03_\name\()_capture_hook:
    push lr
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
    st \source,@\destination
    bl rbm_h03_\name\()_capture_callback
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
    bra h03_sensor_after_\name
    .endm

    sensor_hook s51,r2,r4
    sensor_hook s83,r0,r5
