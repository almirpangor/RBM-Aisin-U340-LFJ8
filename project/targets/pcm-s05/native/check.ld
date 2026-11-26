ENTRY(_s05_chery_check)

MEMORY {
    TEST_ROM (rx) : ORIGIN = 0x1000, LENGTH = 0xF000
}

SECTIONS {
    .text : { *(.text .text.*) *(.rodata .rodata.*) } > TEST_ROM
    .data : { *(.data .data.*) } > TEST_ROM
    .bss (NOLOAD) : { *(.bss .bss.*) *(COMMON) } > TEST_ROM
    /DISCARD/ : { *(.comment) *(.note*) }
}

ASSERT(SIZEOF(.data) == 0, "unexpected initialized state")
ASSERT(SIZEOF(.bss) == 0, "unexpected zero-initialized state")
