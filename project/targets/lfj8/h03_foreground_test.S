/* GNU M32R simulator fixture. The loader and hardware are outside this test. */

    .section .fixture_start,"ax",@progbits
    .global _start
_start:
    ldi r0,#0x40
    mvtc r0,psw
    ld24 sp,#0x9ffffc
    ld24 r13,#0x808000

    ld24 r0,#0x804ae6
    ldi r1,#INITIAL_FLAG
    stb r1,@r0
    ld24 r0,#0x789abc
    mvtaclo r0
    ldi r0,#0
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
    ldi r10,#0x2a
    ldi r11,#0x2b
    ldi r12,#0x2c
    bra h03_call_site

    .section .h03_call,"ax",@progbits
h03_call_site:
#ifdef WRAPPED
    bl verify_wrapper
#else
    .incbin "call-site.dat"
#endif
    /* This point models the return to the next original instruction. */
    bra snapshot_return

    .section .h03_oem_pieces,"ax",@progbits
h03_oem_task:
    .incbin "stock-task.dat"

/* Only the conversion peripheral is replaced. The stock words perform the
   actual shifting and all three RAM writes at their original addresses. */
    .section .h03_mock_adc,"ax",@progbits
    ld24 r2,#mock_adc_results
    mv r3,r1
    slli r3,#1
    add r2,r3
    lduh r3,@r2
    sth r3,@r0
    ld24 r2,#snapshot
    ld r3,@(76,r2)
    addi r3,#1
    st r3,@(76,r2)
    ld r3,@(80,r2)
    slli r3,#8
    or r3,r1
    st r3,@(80,r2)
    jmp lr

    .macro stub suffix
    .section .h03_mock_\suffix,"ax",@progbits
    jmp lr
    nop
    .endm
    stub a0cc
    stub bed8
    stub d108
    stub 4039c
    stub 403c0

    .section .fixture_code,"ax",@progbits
    .p2align 2
verify_wrapper:
    push lr
    bl h03_oem_task
    push r0
    push r1
    push r2
    push r3
    push r4
    push r5
    push r6
    push r7
    push r8
    push r9
    push r10
    push r11
    push r12
    push r13
    mvfc r0,psw
    push r0
    mvfachi r0
    push r0
    mvfaclo r0
    push r0
    bl observe_and_clobber
    pop r0
    mvtaclo r0
    pop r0
    mvtachi r0
    pop r0
    mvtc r0,psw
    pop r13
    pop r12
    pop r11
    pop r10
    pop r9
    pop r8
    pop r7
    pop r6
    pop r5
    pop r4
    pop r3
    pop r2
    pop r1
    pop r0
    pop lr
    jmp lr

    .p2align 2
observe_and_clobber:
    ld24 r0,#snapshot
    ld r1,@(96,r0)
    addi r1,#1
    st r1,@(96,r0)
    ld24 r1,#0x804bc6
    lduh r1,@r1
    st r1,@(100,r0)
    mv r1,sp
    st r1,@(104,r0)
    mvfc r0,psw
    xor3 r0,r0,#1
    mvtc r0,psw
    ldi r0,#1
    mvtachi r0
    mvtaclo r0
    ldi r1,#1
    ldi r2,#1
    ldi r3,#1
    ldi r4,#1
    ldi r5,#1
    ldi r6,#1
    ldi r7,#1
    ldi r8,#1
    ldi r9,#1
    ldi r10,#1
    ldi r11,#1
    ldi r12,#1
    ldi r13,#1
    jmp lr

    .p2align 2
snapshot_return:
    push r0
    ld24 r0,#snapshot
    st r1,@(4,r0)
    st r2,@(8,r0)
    st r3,@(12,r0)
    st r4,@(16,r0)
    st r5,@(20,r0)
    st r6,@(24,r0)
    st r7,@(28,r0)
    st r8,@(32,r0)
    st r9,@(36,r0)
    st r10,@(40,r0)
    st r11,@(44,r0)
    st r12,@(48,r0)
    st r13,@(52,r0)
    st lr,@(56,r0)
    add3 r1,sp,#4
    st r1,@(60,r0)
    ld r1,@sp
    st r1,@r0
    mvfc r1,psw
    st r1,@(64,r0)
    mvfachi r1
    st r1,@(68,r0)
    mvfaclo r1
    st r1,@(72,r0)
    ld24 r1,#0x804bc6
    lduh r1,@r1
    st r1,@(84,r0)
    ld24 r1,#0x804bc0
    lduh r1,@r1
    st r1,@(88,r0)
    ld24 r1,#0x804bca
    lduh r1,@r1
    st r1,@(92,r0)
    ld24 r1,#0x804ae6
    ldub r1,@r1
    st r1,@(108,r0)

    /* Write ASCII hex through the GNU simulator's syscall interface. */
    ld24 r1,#snapshot
    ld24 r2,#hex_buffer
    ld24 r3,#hex_digits
    ldi r4,#112
hex_next:
    ldub r5,@r1
    addi r1,#1
    mv r6,r5
    srli r6,#4
    add r6,r3
    ldub r6,@r6
    stb r6,@r2
    addi r2,#1
    and3 r5,r5,#15
    add r5,r3
    ldub r5,@r5
    stb r5,@r2
    addi r2,#1
    addi r4,#-1
    bnez r4,hex_next
    ldi r0,#5
    ldi r1,#1
    ld24 r2,#hex_buffer
    ld24 r3,#224
    trap #0
    ldi r0,#1
    ldi r1,#0
    trap #0

    .section .fixture_data,"aw",@progbits
    .p2align 2
snapshot:
    .space 112
hex_buffer:
    .space 224
mock_adc_results:
    .short 0, 0, (ADC2_SAMPLE << 6) | 0x3f, 0x7d3b, (100 << 6) | 0x1f
hex_digits:
    .ascii "0123456789abcdef"
