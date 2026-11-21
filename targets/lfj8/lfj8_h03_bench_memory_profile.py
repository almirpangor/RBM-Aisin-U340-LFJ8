"""Pinned H03 RAM reservation and remaining-stack minima for the bench build."""

from hashlib import sha256

from audit_h03_irq_stack import IMAGE_HASH
from lfj8_h03_can_service_placement import typed_alias_ranges
from lfj8_h03_ram_placement import confirmed_ranges
from lfj8_h03_service_placement import CONDITIONAL_STACK_AND_PSW, policy_ranges


# Aligned past the OEM diagnostic registration limit at 0x04606C.
SPI_FIRST, RAM_LIMIT = CONDITIONAL_STACK_AND_PSW
PSW_FIRST = 0x809F00  # First aligned word above the initial SPI boundary.
SPI_REMAINING = 824 + 3 * 72  # Stock IRQ/SBI modeled maximum plus three native wrappers.
PSW_REMAINING = 16 * 4  # 16 records, a reservation above the modeled IRQ/SBI chain.
DIAGNOSTIC_LIMIT_SITE = 0x04606C
DIAGNOSTIC_LIMIT_WORD = 0xE28096FF
EARLY_STATE = {
    "rbm_h03_application": "control/application",
    "rbm_h03_tml0_1mhz_qualified": "control/clock_qualified",
}
APPLICATION_RUNNING_OFFSET = 4
# Reset vectors, SPI/PSW setup, common reset handoff and the stock service
# mode selector/store/branches, plus the diagnostic RAM pointer limit.
# The early IE word itself is patched and
# verified by the RAM owner. Variant Flash/service ownership is checked there.
BOOT_WORD_ADDRESSES = (
    0x000000, 0x000020, 0x003D94, 0x003DA4, 0x003DA8,
    0x003DAC, 0x003DB0, 0x003DB4, 0x003DC0, 0x003E40,
    0x00D10C, 0x00D124, 0x00D13C, 0x00D140, 0x00D14C, 0x00D1E8,
    0x030018, 0x03001C, DIAGNOSTIC_LIMIT_SITE, 0x046070,
)
MODULE = "lfj8_h03_bench_memory.c"
NATIVE_DEFINE = "RBM_H03_BENCH_EARLY_LATCHES=1"


def pinned_boot_words(rom):
    if sha256(rom).hexdigest() != IMAGE_HASH:
        raise ValueError("Bench memory profile requires the pinned stock H03")
    if rom[0x03001B:0x03001D] != b"\0\0":
        raise ValueError("H03 foreground service flags are enabled")
    if (int.from_bytes(rom[DIAGNOSTIC_LIMIT_SITE:DIAGNOSTIC_LIMIT_SITE + 4], "big") != DIAGNOSTIC_LIMIT_WORD or
            SPI_FIRST <= (DIAGNOSTIC_LIMIT_WORD & 0xFFFFFF)):
        raise ValueError("H03 diagnostic RAM limit reaches the stack reservation")
    return tuple((address, int.from_bytes(rom[address:address + 4], "big"))
                 for address in BOOT_WORD_ADDRESSES)


def header(words):
    rows = ", \\\n    ".join(f"{{0x{address:06x}u, 0x{word:08x}u}}" for address, word in words)
    return "#define RBM_H03_BENCH_BOOT_WORDS { \\\n    " + rows + " }\n"


def prepare(rom, storage, irq_pointer, stage):
    """Emit a real profile header and absolute linker symbols from typed RAM."""
    words = pinned_boot_words(rom)
    blocks = storage["blocks"]
    bounds = confirmed_ranges(rom, blocks)
    regions = {name: (block["address"], block["end_exclusive"]) for name, block in blocks.items()}
    symbols = {
        "rbm_h03_ram_spi_first": SPI_FIRST, "rbm_h03_ram_spi_reserve": SPI_REMAINING,
        "rbm_h03_ram_psw_first": PSW_FIRST, "rbm_h03_ram_psw_reserve": PSW_REMAINING,
    }
    spi_top = bounds["rbm_h03_ram_spi_end"]
    psw_cursor = bounds["rbm_h03_ram_psw_end"] - 4
    if not (SPI_FIRST + SPI_REMAINING <= spi_top < PSW_FIRST and
            PSW_FIRST + PSW_REMAINING <= psw_cursor < RAM_LIMIT):
        raise ValueError("H03 stack reserve exceeds its reserved region")
    early = typed_alias_ranges(storage, EARLY_STATE)
    app_first, app_end = early["rbm_h03_application"]
    clock_first, clock_end = early["rbm_h03_tml0_1mhz_qualified"]
    if not app_first + APPLICATION_RUNNING_OFFSET < app_end or clock_end - clock_first != 1:
        raise ValueError("H03 early reset latches differ from their typed ABI")
    if irq_pointer & 3 or irq_pointer + 4 > SPI_FIRST:
        raise ValueError("H03 BasicCAN pointer violates the stack reservation")

    ranges = policy_ranges(regions, ((irq_pointer, irq_pointer + 4),))
    destination = stage / "h03_bench_memory_profile.h"
    destination.write_text(header(words), encoding="ascii")
    return {"symbols": symbols, "early_bindings": {name: first for name, (first, _) in early.items()},
            "header": destination, "policy_ranges": ranges,
            "reserved_ram": (SPI_FIRST, RAM_LIMIT), "spi_top": spi_top, "psw_cursor": psw_cursor}


def verify_ram_placements(placements):
    """Reject common linker allocations in the reserved stack pages."""
    for item in placements:
        start = item["address"]
        if item["flags"] & 1 and start < RAM_LIMIT and start + item["bytes"] > SPI_FIRST:
            raise ValueError(f"H03 writable placement overlaps the stack reservation: {item['section']}")
