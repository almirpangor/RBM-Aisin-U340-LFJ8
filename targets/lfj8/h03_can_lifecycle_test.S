    .equ SNAPSHOT_BYTES, 172

/* Addresses below are simulated RAM or ROM. No device interface is linked. */

    .section .test_start,"ax",@progbits
    .global _start
_start:
    ldi r0,#0x40
    mvtc r0,psw
    ld24 sp,#0x9ffffc
    ld24 fp,#0x808000
    ld24 r0,#0x809f9c
    st r0,@r0
    ld24 r0,#0x801000
    ldi r1,#9
    sth r1,@r0
    ld24 r1,#TEST_STATUS
    sth r1,@(2,r0)
    ld24 r0,#0x801010
    ld24 r1,#TEST_MASK
    sth r1,@r0
    ld24 r0,#0x80105d
    ldi r1,#TEST_SLOT13
    stb r1,@r0
    ld24 r0,#0x806ae6
    ldi r1,#TEST_STATE
    stb r1,@r0
    ld24 r0,#0x80105b
    ldi r1,#0x40
    stb r1,@r0
    addi r0,#1
    stb r1,@r0
    ld24 r0,#0x80105e
    ldi r1,#0x41
    stb r1,@r0
    ldi r1,#0x45
    stb r1,@(1,r0)
    ld24 r0,#h03_can13_grant
    ldi r1,#1
    stb r1,@r0
    ld24 r0,#h03_can0_generation
    ldi r1,#TEST_GENERATION
    st r1,@r0
    ld24 lr,#test_done
    push lr
    bra test_site

    .section .test_site,"ax",@progbits
test_site:
#if WRAPPED
    bl test_wrapper
#else
    .incbin "call.dat"
#endif
#if RUN_TAIL
    .incbin "tail.dat"
#else
    bra test_done
#endif

    .section .oem_guards,"ax",@progbits
    .incbin "guards.dat"
    .section .oem_select,"ax",@progbits
    .incbin "select.dat"
    .section .oem_config,"ax",@progbits
oem_config:
    .incbin "config.dat"
    .section .oem_variant,"a",@progbits
    .incbin "variant.dat"
    .section .oem_config_mask,"a",@progbits
    .incbin "config-mask.dat"
    .section .oem_slot_tables,"a",@progbits
    .incbin "slot-tables.dat"
    .section .oem_rx_table,"a",@progbits
    .incbin "rx-table.dat"

    .section .mock_bad4,"ax",@progbits
    jmp lr
    nop
    .section .mock_b800,"ax",@progbits
    jmp lr
    nop
    .section .mock_8a04,"ax",@progbits
    jmp lr
    nop

    .macro byte_to_snapshot address,offset
    ld24 r1,#\address
    ldub r1,@r1
    st r1,@(\offset,r0)
    .endm

    .macro half_to_snapshot address,offset
    ld24 r1,#\address
    lduh r1,@r1
    st r1,@(\offset,r0)
    .endm

    .macro word_to_snapshot address,offset
    ld24 r1,#\address
    ld r1,@r1
    st r1,@(\offset,r0)
    .endm

    .section .test_code,"ax",@progbits
    .p2align 2
    .global h03_oem_can0_setup
h03_oem_can0_setup:
    /* Read the owner shadows just before executing the original routine. */
    push r0
    push r1
    ld24 r0,#snapshot
    byte_to_snapshot h03_can13_grant,140
    word_to_snapshot h03_can0_generation,144
    pop r1
    pop r0
    bra oem_config

    .p2align 2
test_wrapper:
    push lr
    bl h03_can0_setup_hook
    /* This observer uses r0/r1 and leaves CR0 and ACC alone. */
    push r0
    push r1
    ld24 r0,#snapshot
    ldi r1,#1
    st r1,@(96,r0)
    half_to_snapshot 0x801000,100
    half_to_snapshot 0x801002,104
    byte_to_snapshot 0x806ae6,108
    byte_to_snapshot 0x80105b,112
    byte_to_snapshot 0x80105c,116
    mv r1,sp
    st r1,@(120,r0)
    half_to_snapshot 0x801010,132
    byte_to_snapshot 0x80105d,136
    byte_to_snapshot 0x80105e,156
    byte_to_snapshot 0x80105f,160
    pop r1
    pop r0
    pop lr
    jmp lr

    .p2align 2
test_done:
    push r0
    ld24 r0,#snapshot
    .set reg_offset,4
    .irp reg,r1,r2,r3,r4,r5,r6,r7,r8,r9,r10,r11,r12,fp,lr
    st \reg,@(reg_offset,r0)
    .set reg_offset,reg_offset+4
    .endr
    add3 r1,sp,#4
    st r1,@(60,r0)
    ld r1,@sp
    st r1,@r0
    mvfc r1,psw
    st r1,@(64,r0)
    half_to_snapshot 0x801000,68
    half_to_snapshot 0x801002,72
    byte_to_snapshot 0x806ae6,76
    byte_to_snapshot 0x80105a,80
    byte_to_snapshot 0x80105b,84
    byte_to_snapshot 0x80105c,88
    ld24 r1,#0x809f9c
    ld r1,@r1
    st r1,@(92,r0)

    half_to_snapshot 0x801010,124
    byte_to_snapshot 0x80105d,128
    byte_to_snapshot h03_can13_grant,148
    word_to_snapshot h03_can0_generation,152
    byte_to_snapshot 0x80105e,164
    byte_to_snapshot 0x80105f,168

    /* Escape the binary snapshot as ASCII for the simulator stdout. */
    ld24 r1,#snapshot
    ld24 r2,#hex_buffer
    ld24 r3,#hex_digits
    ldi r4,#SNAPSHOT_BYTES
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
    ld24 r3,#(2*SNAPSHOT_BYTES)
    trap #0
    ldi r0,#1
    ldi r1,#0
    trap #0

    .section .test_data,"aw",@progbits
    .p2align 2
snapshot:
    .space SNAPSHOT_BYTES
hex_buffer:
    .space 2*SNAPSHOT_BYTES
hex_digits:
    .ascii "0123456789abcdef"

    .p2align 2
    .global h03_can_owner
h03_can_owner:
h03_can0_generation:
    .long 0
    .global h03_can13_grant
h03_can13_grant:
    .byte 0
