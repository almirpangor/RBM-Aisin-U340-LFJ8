OUTPUT_FORMAT(elf32-sh)
OUTPUT_ARCH(sh)
ENTRY(_main)

PHDRS { test_code PT_LOAD FLAGS(5); }

SECTIONS
{
    . = 0x1000;
    .rom : { *(.text .text.*) *(.rodata .rodata.*) } :test_code
    .data : { *(.data .data.* .sdata .sdata.*) } :test_code
    .bss (NOLOAD) : { *(.bss .bss.* .sbss .sbss.*) *(COMMON) } :test_code
    /DISCARD/ : { *(.comment .eh_frame .eh_frame.* .note .note.*) }
}

ASSERT(SIZEOF(.data) == 0 && SIZEOF(.bss) == 0, "SH test uses stack-only writable memory")
ASSERT(SIZEOF(.rom) <= 0xF000, "SH test exceeds emulator ROM span")
