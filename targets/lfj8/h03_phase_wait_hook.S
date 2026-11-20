/* Candidate for the foreground wait at H03 008150. The platform callback
 * checks deadlines without consuming the phase. It must return with IRQ
 * configuration and PSW control bits intact. The linker supplies an aligned
 * running 32-bit clock address and an interval in [1, 0xffffff] ticks.
 * The callback uses the M32R C ABI, including preservation of r8. */
    .text
    .p2align 2
    .global rbm_h03_phase_wait_hook
rbm_h03_phase_wait_hook:
    .irp reg,r0,r1,r2,r3,r4,r5,r6,r7,r8,r9,r10,r11,r12,r13,lr
    push \reg
    .endr
    mvfc r0,psw
    push r0
    mvfachi r0
    push r0
    mvfaclo r0
    push r0
.Lcheck:
    ld24 r4,#h03_phase_wait_ticks
    ld r8,@r4
    bl rbm_h03_phase_wait_callback
    ld24 r4,#0x804ade
    ldub r0,@r4
    bnez r0,.Lready

.Lwait:
    ldub r0,@r4
    bnez r0,.Lcheck
    ld24 r4,#h03_phase_wait_ticks
    .global rbm_h03_phase_wait_tick_sample
rbm_h03_phase_wait_tick_sample:
    ld r0,@r4
    sub r0,r8
    ld24 r1,#h03_phase_wait_interval_ticks
    cmpu r0,r1
    bnc .Lcheck
    ld24 r4,#0x804ade
    bra .Lwait

.Lready:
    pop r0
    mvtaclo r0
    pop r0
    mvtachi r0
    pop r0
    and3 r0,r0,#1
    ldi r1,#0
    cmpu r1,r0
    .irp reg,lr,r13,r12,r11,r10,r9,r8,r7,r6,r5,r4,r3,r2,r1,r0
    pop \reg
    .endr

    ld24 r4,#0x804ade
    bra h03_stock_phase_clear
