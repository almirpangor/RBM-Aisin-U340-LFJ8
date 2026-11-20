/* H03 040424: preserve the original call and timestamp each release after
 * stock 040468 returns. The callback is an IRQ leaf at the application level:
 * it may publish clock state, but must not reconfigure the timer, PSW or IRQs.
 * The owner provides that state only after startup and service isolation. */

    .section .text.rbm_h03_phase_release_hook,"ax",@progbits
    .p2align 2
    .global rbm_h03_phase_release_hook
    .type rbm_h03_phase_release_hook,@function
rbm_h03_phase_release_hook:
    push lr
    bl h03_stock_phase_release

    .irp reg,r0,r1,r2,r3,r4,r5,r6,r7,r8,r9,r10,r11,r12,r13
    push \reg
    .endr
    mvfc r0,psw
    push r0
    mvfachi r0
    push r0
    mvfaclo r0
    push r0

    ld24 r0,#0x8003e0
    ld r0,@r0
    bl rbm_h03_phase_release_callback

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
    pop lr
    jmp lr
    .size rbm_h03_phase_release_hook,.-rbm_h03_phase_release_hook
