/* M32R H03 call-site wrappers. Link only against a verified H03 address map.
 * Callbacks have the C ABI, take no arguments and return a decision in R0.
 * Decision 1 forwards coherent Toyota data to the next OEM call.
 * Decision 2 resumes OEM execution after completed callback handling.
 * Return 2 if the callback already performed the operation or verified inhibit.
 * The bench-only build accepts decision 0 for intact Mazda hardware.
 * Unknown decisions resume OEM execution without dispatching a stock routine.
 * Callbacks must restore their stack, interrupts and control mode under the C ABI.
 */

#include "h03_native_hooks.h"

#if defined(RBM_H03_ALLOW_LEGACY_BENCH) && RBM_H03_ALLOW_LEGACY_BENCH == 1
#define H03_LEGACY_BENCH_ENABLED 1
#endif

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

    .section .text.rbm_h03_strategy_hook,"ax",@progbits
    .p2align 2
    .global rbm_h03_strategy_hook
    .type rbm_h03_strategy_hook,@function
rbm_h03_strategy_hook:
    save_context
    bl rbm_h03_strategy_callback
    ldi r1,#RBM_H03_HOOK_OEM
    beq r0,r1,.Lstrategy_arbiter
#ifdef H03_LEGACY_BENCH_ENABLED
    beqz r0,.Lstrategy_legacy
#endif
    restore_context
    jmp lr
.Lstrategy_arbiter:
    restore_context
    bra h03_stock_arbiter
#ifdef H03_LEGACY_BENCH_ENABLED
.Lstrategy_legacy:
    restore_context
    bra h03_stock_strategy
#endif
    .size rbm_h03_strategy_hook,.-rbm_h03_strategy_hook

    .section .text.rbm_h03_commit_hook,"ax",@progbits
    .p2align 2
    .global rbm_h03_commit_hook
    .type rbm_h03_commit_hook,@function
rbm_h03_commit_hook:
    save_context
    bl rbm_h03_commit_callback
    ldi r1,#RBM_H03_HOOK_OEM
    beq r0,r1,.Lcommit
#ifdef H03_LEGACY_BENCH_ENABLED
    beqz r0,.Lcommit
#endif
    restore_context
    jmp lr
.Lcommit:
    restore_context
    bra h03_stock_commit
    .size rbm_h03_commit_hook,.-rbm_h03_commit_hook
