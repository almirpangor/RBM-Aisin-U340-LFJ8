/* CPU fixture for the two lower RX hooks. The companion link generates
   the sections reachable from the IRQ roots. Writable state and the
   foreground stand-in remain outside the H03 image. */
ENTRY(_start)
SECTIONS {
  .oem_low 0x000000 : { KEEP(*(.oem_low)) }
  .resident_rx 0x006000 : {
    FILL(0xffffffff)
    INCLUDE rx-sections.ld
    KEEP(*(.rodata.native_owner_ops))
    rx_resident_end = .;
    . = 0x2000;
  }
  .oem_app 0x008000 : { KEEP(*(.oem_app)) }
  .fixture 0x100000 : { KEEP(*(.fixture)) }
  .text 0x101000 : { *(.text*) }
  .rodata : { *(.rodata*) }
  .data : { *(.data*) }
  .bss : { *(.bss*) *(COMMON) }
  /DISCARD/ : { *(.note*) *(.comment) }
  ASSERT(SIZEOF(.data) == 0, "Resident RX fixture must not load writable data")
  h03_dtc_rx_resume = 0x001538;
  h03_dtc_rx_entry = 0x0013F0;
}
