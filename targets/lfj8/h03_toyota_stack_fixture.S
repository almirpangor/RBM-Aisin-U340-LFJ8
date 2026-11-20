/* Simulator call boundary. Measure the linked C function on the user
 * stack, leaving the caller frame and the ordinary test CRT on SPI.
 * The cycle passes its fifth word through the caller's stack. */

    .text
    .macro stack_probe name, stage, fifth=0
    .p2align 2
    .global __wrap_\name
    .type __wrap_\name,@function
__wrap_\name:
    push lr
    push r8
    push r9
    push r10
    push r11
    addi sp,#-16
    mv r8,sp
    st r0,@r8
    st r1,@(4,r8)
    st r2,@(8,r8)
    st r3,@(12,r8)
    mvfc r10,psw
    mvfc r11,cr3
    ldi r0,#\stage
    bl h03_stack_probe_prepare

    mvtc r0,cr3
    or3 r4,r10,#0x80
    mvtc r4,psw
    ld r0,@r8
    ld r1,@(4,r8)
    ld r2,@(8,r8)
    ld r3,@(12,r8)
    .if \fifth
    ld r5,@(36,r8)
    addi sp,#-4
    st r5,@sp
    .endif
    bl __real_\name
    .if \fifth
    addi sp,#4
    .endif

    mv r9,r0
    mvfc r1,cr3
    mvfc r2,cr2
    mvfc r3,psw
    mvtc r10,psw
    mvtc r11,cr3
    beq r2,r8,.Lsystem_stack_ok_\@
    ldi r0,#1
    ldi r1,#1
    trap #0
.Lsystem_stack_ok_\@:
    ldi r0,#\stage
    bl h03_stack_probe_observe
    mv r0,r9
    mvtc r10,psw
    addi sp,#16
    pop r11
    pop r10
    pop r9
    pop r8
    pop lr
    jmp lr
    .size __wrap_\name,.-__wrap_\name
    .endm

#ifdef H03_PROBE_CYCLE_ONLY
    stack_probe lfj8_h03_cycle_tick, 0, 1
#else
    stack_probe factory_hydraulics_control_main, 0
    stack_probe rbm_u340e_runtime_main_range, 1
    stack_probe rbm_u340e_runtime_gears_outputs, 2
    stack_probe rbm_u340e_range_fast, 3
    stack_probe rbm_u340e_runtime_main_range_complete, 4
    stack_probe rbm_u340e_hydraulics_control_main_workspace, 5
#endif
