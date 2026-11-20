    .section .oem_prefix,"ax",@progbits
    .incbin "h03.dat",0,0x008150
    .global phase_fixture_consume
phase_fixture_consume:
    .incbin "h03.dat",0x008150,0x10
    jmp lr || nop
    .incbin "h03.dat",0x008164,0x020000-0x008164

    .section .oem_suffix,"ax",@progbits
    .incbin "h03.dat",0x030000,0x040424-0x030000
phase_fixture_site:
#if PHASE_HOOK_ENABLED
    bl rbm_h03_phase_release_hook
#else
    .incbin "h03.dat",0x040424,4
#endif
    jmp r9 || nop
    .incbin "h03.dat",0x04042c

    .section .fixture,"ax",@progbits
    .global _start
    .global phase_fixture_done
_start:
    ld24 sp,#0x9ffffc
    ld24 fp,#0x808000
    ldi r0,#0x40
    mvtc r0,psw
    ld24 r0,#0x804864
    ldi r1,#5
    stb r1,@r0
    ld24 r0,#0x804861
    ldi r1,#7
    stb r1,@r0
    ld24 r0,#0x800706
    ldi r1,#-126
    stb r1,@r0
    ldi r0,#PHASE_HOOK_ENABLED
    bl phase_fixture_main
phase_fixture_done:
    bra phase_fixture_done

    .p2align 2
    .global phase_fixture_release
phase_fixture_release:
    push lr
    push r8
    push r9
    push r10
    push r11
    push r12
    push r13
    ld24 r9,#0x8003e0
    st r0,@r9
    ld24 r9,#0x804862
    ldi r0,#0
    stb r0,@r9
    ld24 r9,#0x800745
    slli r2,#4
    stb r2,@r9
    cmpu r0,r2
    mv r8,r1
    ld24 r9,#.Lafter_stock
    seth r0,#0x1234
    or3 r0,r0,#0x5678
    mvtaclo r0
    ld24 r0,#0x1234
    mvtachi r0
    ldi r0,#0x10
    ldi r1,#0x11
    ldi r2,#0x12
    ldi r3,#0x13
    ldi r4,#0x14
    ldi r5,#0x15
    ldi r6,#0x16
    ldi r7,#0x17
    ldi r10,#0x1a
    ldi r11,#0x1b
    ldi r12,#0x1c
    ld24 r13,#0x808000
    bra phase_fixture_site

    .p2align 2
.Lafter_stock:
    .set offset,0
    .irp reg,r0,r1,r2,r3,r4,r5,r6,r7,r8,r9,r10,r11,r12,r13,lr,sp
    st \reg,@(offset,r8)
    .set offset,offset+4
    .endr
    mvfc r0,psw
    st r0,@(64,r8)
    mvfachi r0
    st r0,@(68,r8)
    mvfaclo r0
    st r0,@(72,r8)
    ld24 r0,#0x804ade
    ldub r0,@r0
    st r0,@(76,r8)
    ld24 r0,#0x804862
    ldub r0,@r0
    st r0,@(80,r8)
    ld24 r0,#0x804861
    ldub r0,@r0
    st r0,@(84,r8)
    ld24 r0,#0x800706
    ldub r0,@r0
    st r0,@(88,r8)
    pop r13
    pop r12
    pop r11
    pop r10
    pop r9
    pop r8
    pop lr
    jmp lr

    .p2align 2
    .global rbm_h03_phase_release_callback
rbm_h03_phase_release_callback:
    push lr
    bl phase_fixture_publish
    ldi r0,#0
    mvtaclo r0
    mvtachi r0
    ldi r1,#1
    cmpu r0,r1
    ldi r0,#-1
    ldi r1,#-2
    ldi r2,#-3
    ldi r3,#-4
    ldi r4,#-5
    ldi r5,#-6
    ldi r6,#-7
    ldi r7,#-8
    pop lr
    jmp lr
