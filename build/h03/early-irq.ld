h03_dma4_after_entry = 0xcf10;
h03_dtc_irq_pointer = 0x806fac;
h03_dtc_rx_entry = 0x13f0;
h03_dtc_rx_resume = 0x1538;
h03_early_irq_after_entry = 0x3dc0;
h03_service_close_after_store = 0x2ea0;
h03_service_copy_after_entry = 0x2d20;
h03_service_direct_after_entry = 0x2928;
h03_service_disable_virtual_flash = 0x3594;
h03_service_stock_span_check = 0x3528;
rbm_h03_application = 0x806efc;
rbm_h03_tml0_1mhz_qualified = 0x806f14;
ENTRY(rbm_h03_early_irq_redirect)
SECTIONS {
 .p0000 0x1534 : { early-irq.o(".text.rbm_h03_dtc_rx_redirect") }
 .p0001 0x2924 : { early-irq.o(".service_site_002924") }
 .p0002 0x294c : { early-irq.o(".service_site_00294c") }
 .p0003 0x2d1c : { early-irq.o(".service_site_002d1c") }
 .p0004 0x2e9c : { early-irq.o(".service_site_002e9c") }
 .p0005 0x3568 : { early-irq.o(".service_site_003568") }
 .p0006 0x3dbc : { early-irq.o(".text.rbm_h03_early_irq_redirect") }
 .p0007 0x4738 : { early-irq.o(".text.rbm_h03_dtc_rx_dispatch_redirect") }
 .p0008 0x6000 : { early-irq.o(".text.lfj8_h03_dtc_rx_queue_capture_pending") }
 .p0009 0x6200 : { early-irq.o(".text.publish_locked") }
 .p0010 0x6394 : { early-irq.o(".text.rbm_h03_service_hooks") }
 .p0011 0x64d8 : { early-irq.o(".text.lfj8_h03_dtc_rx_queue_capture_basic") }
 .p0012 0x65b4 : { early-irq.o(".text") }
 .p0013 0x668c : { early-irq.o(".text.expire") }
 .p0014 0x6754 : { early-irq.o(".text.capture_basic.part.0") }
 .p0015 0x6814 : { early-irq.o(".text.lfj8_h03_dtc_can_decode_basic") }
 .p0016 0x68c8 : { early-irq.o(".text.rbm_h03_dtc_rx_observe") }
 .p0017 0x6970 : { early-irq.o(".text.rbm_h03_dtc_rx_hook") }
 .p0018 0x6a08 : { early-irq.o(".text.rbm_h03_dtc_rx_dispatch_hook") }
 .p0019 0x6a9c : { early-irq.o(".text.rbm_h03_dtc_rx_begin") }
 .p0020 0x6b2c : { early-irq.o(".text.sample_clocks") }
 .p0021 0x6bb4 : { early-irq.o(".text.lfj8_h03_service_span_allowed") }
 .p0022 0x6c7c : { early-irq.o(".text.h03_can0_operational") }
 .p0023 0x6cd8 : { early-irq.o(".text.lfj8_h03_can0_read_timestamp") }
 .p0024 0x6d34 : { early-irq.o(".text.can0_available") }
 .p0025 0x6d88 : { early-irq.o(".text.lfj8_h03_dtc_rx_dispatch_begin") }
 .p0026 0x6ddc : { early-irq.o(".text.lfj8_h03_dtc_rx_dispatch_skip_paired") }
 .p0027 0x6e30 : { early-irq.o(".rodata.rbm_h03_service_policy") }
 .p0028 0x6ed4 : { early-irq.o(".text.ready") }
 .p0029 0x6efc : { early-irq.o(".text.basiccan_active") }
 .p0030 0x6f20 : { early-irq.o(".text.rbm_h03_early_irq_gate") }
 .p0031 0x6f44 : { early-irq.o(".text.lfj8_h03_service_copy_allowed") }
 .p0032 0x6fb0 : { early-irq.o(".text.increment") }
 .p0033 0xcf0c : { early-irq.o(".text.rbm_h03_dma4_redirect") }
 .p0034 0x2b8e8 : { early-irq.o(".text.rbm_h03_dma4_guard") }
 .p0035 0x806fac (NOLOAD) : { early-irq.o(".bss.irq_target") }
 /DISCARD/ : { *(.note*) *(.comment) }
}
ASSERT(SIZEOF(.p0000) == 4, "Placed section size changed")
ASSERT(SIZEOF(.p0001) == 4, "Placed section size changed")
ASSERT(SIZEOF(.p0002) == 4, "Placed section size changed")
ASSERT(SIZEOF(.p0003) == 4, "Placed section size changed")
ASSERT(SIZEOF(.p0004) == 4, "Placed section size changed")
ASSERT(SIZEOF(.p0005) == 4, "Placed section size changed")
ASSERT(SIZEOF(.p0006) == 4, "Placed section size changed")
ASSERT(SIZEOF(.p0007) == 4, "Placed section size changed")
ASSERT(SIZEOF(.p0008) == 512, "Placed section size changed")
ASSERT(SIZEOF(.p0009) == 404, "Placed section size changed")
ASSERT(SIZEOF(.p0010) == 324, "Placed section size changed")
ASSERT(SIZEOF(.p0011) == 220, "Placed section size changed")
ASSERT(SIZEOF(.p0012) == 216, "Placed section size changed")
ASSERT(SIZEOF(.p0013) == 200, "Placed section size changed")
ASSERT(SIZEOF(.p0014) == 192, "Placed section size changed")
ASSERT(SIZEOF(.p0015) == 180, "Placed section size changed")
ASSERT(SIZEOF(.p0016) == 168, "Placed section size changed")
ASSERT(SIZEOF(.p0017) == 152, "Placed section size changed")
ASSERT(SIZEOF(.p0018) == 148, "Placed section size changed")
ASSERT(SIZEOF(.p0019) == 144, "Placed section size changed")
ASSERT(SIZEOF(.p0020) == 136, "Placed section size changed")
ASSERT(SIZEOF(.p0021) == 104, "Placed section size changed")
ASSERT(SIZEOF(.p0022) == 92, "Placed section size changed")
ASSERT(SIZEOF(.p0023) == 92, "Placed section size changed")
ASSERT(SIZEOF(.p0024) == 84, "Placed section size changed")
ASSERT(SIZEOF(.p0025) == 84, "Placed section size changed")
ASSERT(SIZEOF(.p0026) == 84, "Placed section size changed")
ASSERT(SIZEOF(.p0027) == 68, "Placed section size changed")
ASSERT(SIZEOF(.p0028) == 40, "Placed section size changed")
ASSERT(SIZEOF(.p0029) == 36, "Placed section size changed")
ASSERT(SIZEOF(.p0030) == 36, "Placed section size changed")
ASSERT(SIZEOF(.p0031) == 32, "Placed section size changed")
ASSERT(SIZEOF(.p0032) == 16, "Placed section size changed")
ASSERT(SIZEOF(.p0033) == 4, "Placed section size changed")
ASSERT(SIZEOF(.p0034) == 128, "Placed section size changed")
ASSERT(SIZEOF(.p0035) == 4, "Placed section size changed")
