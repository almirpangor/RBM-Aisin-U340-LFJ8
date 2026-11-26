/* Run only with the simulator linker layout. MMIO and CAN ownership are RAM shadows. */
#include "lfj8_h03_can_owner.h"

    .macro set_byte addr,val
    ld24 r1,#\addr
    ldi r2,#\val
    stb r2,@r1
    .endm

    .macro set_half addr,val
    ld24 r1,#\addr
    ld24 r2,#\val
    sth r2,@r1
    .endm

    .macro set_word addr,val
    ld24 r1,#\addr
    ld24 r2,#\val
    st r2,@r1
    .endm

    .macro check_byte addr,val
    ld24 r1,#\addr
    ldub r2,@r1
    ldi r3,#\val
    bne r2,r3,test_failed
    .endm

    .section .fixture,"ax",@progbits
    .global _start
_start:
    ldi r0,#0x40
    mvtc r0,psw
    ld24 sp,#0x9ffffc
    ld24 fp,#0x808000
    set_word 0x809f9c,0x809f9c
    set_word 0x8066bc,0x032ab4
    set_byte 0x806ae6,7
    set_byte 0x806b22,0x20
    set_byte 0x806b23,0
    set_byte 0x80801c,0
    set_half 0x801010,0x8003
    set_half 0x80100c,4
    set_byte h03_can_owner+LFJ8_CAN_OWNER_GRANT_OFFSET,LEASE_VALUE
    set_byte h03_can_owner+LFJ8_CAN_OWNER_TX13_FENCE_OFFSET,FENCE_VALUE

    /* First matching OEM descriptor under mask 20 is 0x218.
     * The payload record is 14 bytes past the table's first record. */
    set_byte 0x8066d4,0x08
    set_byte 0x8066d5,0x18
    set_byte 0x8066d6,0x08
    set_byte 0x8066d7,0x42

    set_byte 0x80105d,INITIAL_CONTROL
    set_byte 0x8011d0,0x17
    set_byte 0x8011d1,0x28
    set_byte 0x8011d5,8
    set_byte 0x8011d6,0xa4

#if IRQ_PATH
    bl h03_irq
    /* The stock ISR consumes SLIST bit 2 even when SLIMK masks it. */
    ld24 r1,#0x80100c
    lduh r2,@r1
    ld24 r3,#0xfffb
    bne r2,r3,test_failed
#else
    /* The original C338 call site is inside a function with LR and R8 saved. */
    ld24 lr,#resume_foreground
    push lr
    push r8
    bra h03_foreground_call
    .p2align 2
resume_foreground:
#endif
    ld24 r1,#0x9ffffc
    bne sp,r1,test_failed
#if HOOKED && (LEASE_VALUE == 1 || FENCE_VALUE == 1)
    check_byte 0x80105d,INITIAL_CONTROL
    check_byte 0x8011d0,0x17
    check_byte 0x8011d1,0x28
    check_byte 0x8011d6,0xa4
    check_byte 0x806b23,0
#else
    check_byte 0x80105d,0x80
    check_byte 0x8011d0,0x08
    check_byte 0x8011d1,0x18
    check_byte 0x8011d6,0x42
    check_byte 0x806b23,2
#endif
    ldi r1,#0
    bra test_exit
test_failed:
    ldi r1,#1
test_exit:
    ldi r0,#1
    trap #0

#if !HOOKED
    .section .tx_entry,"ax",@progbits
    .balign 4
    .incbin "tx-entry.bin"
#endif
