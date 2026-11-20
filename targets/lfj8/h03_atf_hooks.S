/* Candidate H03 hooks. Enter by BRA, with the original registers intact.
 * The callbacks run with IE clear and must balance their own stack and keep
 * the current stack mode. The application owns their clock and ATF state.
 * The simulator supplies fixture callbacks. */

    .section .text.rbm_h03_atf_hooks,"ax",@progbits
    .equ saved_r0,40
    .equ source_valid,48
    .equ source_time,52

    .macro atf_entry name
    .p2align 2
    .global rbm_h03_atf_\name
rbm_h03_atf_\name:
    .endm

    .macro atf_lock
    push lr
    .irp reg,r0,r1,r2,r3,r4,r5,r6,r7
    push \reg
    .endr
    mvfc r7,psw
    clrpsw #0x40
    push r7
    mvfachi r7
    push r7
    mvfaclo r7
    push r7
    .endm

    .macro atf_unlock
    pop r7
    mvtaclo r7
    pop r7
    mvtachi r7
    pop r7
    mvtc r7,psw
    .irp reg,r7,r6,r5,r4,r3,r2,r1,r0
    pop \reg
    .endr
    pop lr
    .endm

    /* 03B110: keep the OEM save pair and add a per-call source record. */
    atf_entry begin
    push lr
    push r8
    addi sp,#-8
    push r0
    ldi r0,#0
    st r0,@(4,sp)
    pop r0
    bra h03_atf_after_begin

    /* 040178: publish after the original store, within the same exclusion. */
    atf_entry adc
    atf_lock
    sth r0,@r5
    bl rbm_h03_atf_adc_callback
    atf_unlock
    pop lr
    bra h03_atf_after_adc

    /* 03B138: load AN1 and capture its timestamp before reopening IRQs. */
    atf_entry read
    atf_lock
    lduh r0,@r4
    st r0,@(saved_r0,sp)
    add3 r1,sp,#source_time
    bl rbm_h03_atf_source_callback
    st r0,@(source_valid,sp)
    atf_unlock
    bra h03_atf_after_read

    .macro atf_publish name,site,ptr
    atf_entry \name
    atf_lock
    st r0,@\ptr
    ld24 r0,#\site
    ldi r1,#0
    .ifnc \name,fault
    ld r2,@(source_valid,sp)
    beqz r2,1f
    add3 r1,sp,#source_time
1:
    .endif
    bl rbm_h03_atf_publish_callback
    atf_unlock
    bra h03_atf_resume_done
    .endm

    atf_publish fault,0x03b178,r6
    atf_publish direct,0x03b1a4,r4
    atf_publish filtered,0x03b218,r4

    /* 03B21C: release the source record and execute the OEM pop pair. */
    atf_entry end
    addi sp,#8
    pop r8
    pop lr
    bra h03_atf_after_end
