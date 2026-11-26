/* Fixed OEM sites, linked by the H03 address model below 0x008000. */

    .section .text.rbm_h03_dtc_rx_redirect,"ax"
    .balign 4
    .global rbm_h03_dtc_rx_redirect
    .type rbm_h03_dtc_rx_redirect,@function
rbm_h03_dtc_rx_redirect:
    bra.l rbm_h03_dtc_rx_hook
    .size rbm_h03_dtc_rx_redirect,.-rbm_h03_dtc_rx_redirect

    .section .text.rbm_h03_dtc_rx_dispatch_redirect,"ax"
    .balign 4
    .global rbm_h03_dtc_rx_dispatch_redirect
    .type rbm_h03_dtc_rx_dispatch_redirect,@function
rbm_h03_dtc_rx_dispatch_redirect:
    bl.l rbm_h03_dtc_rx_dispatch_hook
    .size rbm_h03_dtc_rx_dispatch_redirect,.-rbm_h03_dtc_rx_dispatch_redirect
