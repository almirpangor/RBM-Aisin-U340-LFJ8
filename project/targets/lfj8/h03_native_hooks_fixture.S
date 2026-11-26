#include "h03_native_hooks.h"

#ifdef FIXTURE_CONTEXT_CARRY
/* This probe runs without debugger breakpoints, which alter the simulator PSW. */
    .text
    .global _start
    .global rbm_h03_strategy_callback
    .global rbm_h03_commit_callback
    .global h03_stock_arbiter
    .global h03_stock_commit
_start:
    ld24 sp,#0x9ffffc
    ldi r0,#(0x40 | FIXTURE_CONTEXT_CARRY)
    mvtc r0,psw
    bl rbm_h03_strategy_hook
    mvfc r0,psw
    ldi r1,#(0x40 | FIXTURE_CONTEXT_CARRY)
    bne r0,r1,.Lcontext_fail
    bl rbm_h03_commit_hook
    mvfc r0,psw
    ldi r1,#(0x40 | FIXTURE_CONTEXT_CARRY)
    bne r0,r1,.Lcontext_fail
    ldi r1,#0
    bra .Lcontext_exit
h03_stock_arbiter:
h03_stock_commit:
.Lcontext_fail:
    ldi r1,#1
.Lcontext_exit:
    ldi r0,#1
    trap #0

    .p2align 2
rbm_h03_strategy_callback:
rbm_h03_commit_callback:
    ldi r0,#RBM_H03_HOOK_HANDLED
    ldi r1,#0
    ldi r2,#(1 - FIXTURE_CONTEXT_CARRY)
    cmpu r1,r2
    jmp lr
#else
/* The test runner enters the chosen OEM BL after stopping at fixture_ready. */

    .section .fixture_start,"ax",@progbits
    .global _start
#ifndef H03_FULL_PHASE_FIXTURE
    .global fixture_ready
#endif
_start:
#ifdef H03_FULL_PHASE_FIXTURE
    ld24 sp,#0x9ffffc
    ld24 r1,#0x9fc000
    seth r0,#0xa55a
    or3 r0,r0,#0x6996
.Lseed_stack:
    st r0,@r1
    addi r1,#4
    bne r1,sp,.Lseed_stack
    ld24 fp,#0x808000
    ldi r0,#0x40
    mvtc r0,psw
    bl h03_phase_fixture
    .global h03_phase_fixture_exit
h03_phase_fixture_exit:
    mv r1,r0
    ldi r0,#1
    trap #0
#else
    ld24 sp,#0x9ffffc
    ld24 r0,#0x809f9c
    st r0,@r0
    ldi r0,#0x41
    mvtc r0,psw
    seth r0,#0x1234
    or3 r0,r0,#0x5678
    mvtaclo r0
    ld24 r0,#0x005a2d11
    mvtachi r0
    ldi r0,#0x10
    ldi r1,#0x11
    ldi r2,#0x12
    ldi r3,#0x13
    ldi r4,#0x14
    ldi r5,#0x15
    ldi r6,#0x16
    ldi r7,#0x17
    ldi r8,#0x18
    ldi r9,#0x19
    ldi r10,#0x1a
    ldi r11,#0x1b
    ldi r12,#0x1c
    ld24 fp,#0x808000
    .p2align 2
fixture_ready:
    push r0
    ld24 r0,#fixture_commit_site
    ld r0,@r0
    bnez r0,.Ltest_commit
    pop r0
    bra fixture_strategy_site
.Ltest_commit:
    pop r0
    bra fixture_commit_site_call
#endif

    .section .strategy_site,"ax",@progbits
fixture_strategy_site:
#ifdef FIXTURE_STOCK
    .incbin "strategy-site.dat"
#else
    bl rbm_h03_strategy_hook
#endif

    .section .commit_site,"ax",@progbits
fixture_commit_site_call:
#ifdef FIXTURE_STOCK
    .incbin "commit-site.dat"
#else
    bl rbm_h03_commit_hook
#endif

#ifdef H03_FULL_PHASE_FIXTURE
    .section .oem_prefix,"ax",@progbits
    .incbin "oem-prefix.dat"
    .section .oem_before,"ax",@progbits
    .incbin "oem-before-tail.dat"
#else
    .section .oem_before,"ax",@progbits
    .incbin "oem-before.dat"
#endif
    .section .oem_between,"ax",@progbits
    .incbin "oem-between.dat"
    .section .oem_after,"ax",@progbits
    .incbin "oem-after.dat"
#endif
