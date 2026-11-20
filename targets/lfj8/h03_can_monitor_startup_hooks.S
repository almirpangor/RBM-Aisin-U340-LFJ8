/* App-only H03 call sites. Absolute continuations are pinned by the linker. */

    .macro save_context
    push lr
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
    pop lr
    .endm

    .section .text.rbm_h03_can_monitor_hooks,"ax",@progbits
    .p2align 2
    .global rbm_h03_can_monitor_cold_hook
rbm_h03_can_monitor_cold_hook:
    save_context
    bl.l rbm_h03_can_monitor_rearm
    beqz r0,.Lcold_failure
    restore_context
    bra.l h03_application_start
.Lcold_failure:
    restore_context
    bra.l h03_boot_recovery

    .p2align 2
    .global rbm_h03_can_monitor_prepare_hook
rbm_h03_can_monitor_prepare_hook:
    save_context
    bl.l rbm_h03_can_monitor_prepare_recovery
    beqz r0,.Lprepare_failure
    restore_context
    /* Preserve the original call's LR. The copy ends with CAN0 in reset. */
    bra.l rbm_h03_stock_can0_setup_parked
.Lprepare_failure:
    restore_context
    /* Match the displaced native lock release before returning to the
     * state machine without running the CAN setup or receive permit. */
    bl.l h03_stock_leave
    bra.l h03_can0_recovery_skip

    .macro guarded_release symbol, reg, continuation, failure
    .p2align 2
    .global \symbol
\symbol:
    save_context
    bl.l rbm_h03_can_monitor_runtime_rearm
    beqz r0,.Lpermit_failure\@
    restore_context
    ldi \reg,#8
    bra.l \continuation
.Lpermit_failure\@:
    restore_context
    bra.l \failure
    .endm

    /* Replays the displaced LDI but performs the SFR write only in the
     * C guard, after filter readback and with both channels still parked. */
    guarded_release rbm_h03_can_monitor_start_permit, r1, h03_can0_start_continuation, h03_can0_start_continuation
    guarded_release rbm_h03_can_monitor_recovery_permit, r0, h03_can0_recovery_continuation, h03_can0_recovery_skip
