"""Pinned H03 RAM reservation and remaining-stack minima for the bench build."""

from hashlib import sha256
from pathlib import Path

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
NATIVE_SOURCES = (MODULE, "lfj8_h03_ram_owner.c", "h03_dma4_guard.S")
SYMBOL_SOURCE = "h03_bench_memory_symbols.S"
LINKER_FRAGMENT = "h03_bench_memory_symbols.ld"


def stack_symbols():
    return {
        "rbm_h03_ram_spi_first": SPI_FIRST, "rbm_h03_ram_spi_reserve": SPI_REMAINING,
        "rbm_h03_ram_psw_first": PSW_FIRST, "rbm_h03_ram_psw_reserve": PSW_REMAINING,
    }


def absolute_symbol_source(symbols):
    """No allocated storage: these are addresses/counts, not RAM variables."""
    lines = ["/* Generated from the validated pinned H03 memory profile. */"]
    for name, value in sorted(symbols.items()):
        lines.extend((f".globl {name}", f".equ {name}, {value:#x}"))
    return "\n".join(lines) + "\n"


def linker_fragment(symbols, spi_top, psw_cursor):
    """Alternative to SYMBOL_SOURCE; include exactly one symbol input."""
    lines = ["/* Generated H03 memory ABS symbols; no SECTIONS or storage. */"]
    lines.extend(f"{name} = ABSOLUTE({value:#x});" for name, value in sorted(symbols.items()))
    lines.extend((
        f'ASSERT(rbm_h03_ram_spi_first + rbm_h03_ram_spi_reserve <= {spi_top:#x}, "H03 SPI reserve exceeds its region")',
        f'ASSERT(rbm_h03_ram_psw_first + rbm_h03_ram_psw_reserve <= {psw_cursor:#x}, "H03 PSW reserve exceeds its region")',
    ))
    return "\n".join(lines) + "\n"


def native_compile_flags(profile, source):
    """Apply the same opt-in/header only to its three actual native consumers."""
    if Path(source).name not in NATIVE_SOURCES:
        return ()
    destination = Path(profile["header"])
    if destination.name != "h03_bench_memory_profile.h":
        raise ValueError("Unexpected generated H03 memory header")
    return ("-D" + NATIVE_DEFINE, "-I", str(destination.parent),
            '-DRBM_H03_BENCH_MEMORY_HEADER="' + destination.name + '"')


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
    symbols = stack_symbols()
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
    destination.write_text(header(words), encoding="ascii", newline="\n")
    assembly = stage / SYMBOL_SOURCE
    assembly.write_text(absolute_symbol_source(symbols), encoding="ascii", newline="\n")
    linker = stage / LINKER_FRAGMENT
    linker.write_text(linker_fragment(symbols, spi_top, psw_cursor), encoding="ascii", newline="\n")
    return {"symbols": symbols, "early_bindings": {name: first for name, (first, _) in early.items()},
            "header": destination, "policy_ranges": ranges,
            "reserved_ram": (SPI_FIRST, RAM_LIMIT), "spi_top": spi_top, "psw_cursor": psw_cursor,
            "symbol_source": assembly, "linker_fragment": linker, "native_sources": NATIVE_SOURCES}


def verify_linked_profile(profile, elf):
    """Check the final ELF's actual ABS values, native latch opt-in and RAM."""
    if profile["symbols"] != stack_symbols() or set(profile["early_bindings"]) != set(EARLY_STATE):
        raise ValueError("Incomplete or changed H03 memory qualification profile")
    expected = {**profile["symbols"], **profile["early_bindings"]}
    for name, value in expected.items():
        symbol = elf["symbols"].get(name, {})
        if (symbol.get("section"), symbol.get("address")) != (0xFFF1, value):
            raise ValueError("H03 memory ABS symbol differs from its validated profile: " + name)

    def executable(name, first, end):
        symbol = elf["symbols"].get(name, {})
        section_index = symbol.get("section", 0)
        if not 0 < section_index < len(elf["sections"]):
            raise ValueError("Missing executable H03 memory provider: " + name)
        section = elf["sections"][section_index]
        address = symbol["address"]
        if (section["flags"] & 6 != 6 or not first <= address < end or
                not section["address"] <= address < section["address"] + section["size"]):
            raise ValueError("H03 memory provider is outside executable Flash: " + name)
        return symbol

    boot = executable("rbm_h03_boot_writers_owned", 0x8000, 0x80000)
    gate = executable("rbm_h03_early_irq_gate", 0x6000, 0x8000)
    latches = executable("rbm_h03_early_irq_bench_latches", 0x6000, 0x8000)
    if (latches["section"], latches["address"]) != (gate["section"], gate["address"] + 0x0C):
        raise ValueError("H03 early IRQ gate was not built with the bench latch stores")
    verify_ram_placements({"section": section["name"], "flags": section["flags"],
                           "address": section["address"], "bytes": section["size"]}
                          for section in elf["sections"] if section["flags"] & 2 and section["size"])
    return {"absolute_symbols": expected, "boot_writer_address": boot["address"],
            "early_irq_address": gate["address"], "early_latch_address": latches["address"]}


def verify_ram_placements(placements):
    """Reject common linker allocations in the reserved stack pages."""
    for item in placements:
        start = item["address"]
        if item["flags"] & 1 and start < RAM_LIMIT and start + item["bytes"] > SPI_FIRST:
            raise ValueError(f"H03 writable placement overlaps the stack reservation: {item['section']}")
