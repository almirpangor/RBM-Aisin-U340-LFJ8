/* Fixed OEM entry word, linked at 0x00C34C by the H03 address model. */
    .section .text.h03_can13_tx_redirect,"ax",@progbits
    .balign 4
    .global h03_can13_tx_redirect
    .type h03_can13_tx_redirect,@function
h03_can13_tx_redirect:
    bra.l h03_can13_tx_gate
    .size h03_can13_tx_redirect,.-h03_can13_tx_redirect
