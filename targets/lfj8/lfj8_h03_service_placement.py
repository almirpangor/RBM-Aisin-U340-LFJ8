"""Link and validate the H03 service lockout in an address-model ELF."""

from dataclasses import dataclass
from struct import pack

from lfj8_h03_layout import alloc_sections, read_elf


@dataclass(frozen=True)
class Site:
    address: int
    stock: int
    target: str
    opcode: int = 0xFF

    @property
    def section(self):
        return f".service_site_{self.address:06x}"

    def branch(self, destination):
        delta = destination - self.address
        if self.address % 4 or delta % 4 or not -(1 << 25) <= delta < (1 << 25):
            raise ValueError(f"Unreachable M32R service target: {self.target}")
        return pack(">I", self.opcode << 24 | ((delta // 4) & 0xFFFFFF))


WRITER_SITES = (
    Site(0x2924, 0x2E7F4FF8, "rbm_h03_service_direct_hook"),
    Site(0x294C, 0xFE0002F7, "rbm_h03_service_span_hook", 0xFE),
    Site(0x2D1C, 0x2E7F297F, "rbm_h03_service_copy_hook"),
    Site(0x2E9C, 0xA00A0008, "rbm_h03_service_close_hook"),
)
LOCKOUT = Site(0x3568, 0xB810000B, "h03_service_disable_virtual_flash")
SITES = (*WRITER_SITES, LOCKOUT)
STOCK_TARGETS = {
    "h03_service_direct_after_entry": 0x2928,
    "h03_service_stock_span_check": 0x3528,
    "h03_service_copy_after_entry": 0x2D20,
    "h03_service_close_after_store": 0x2EA0,
    LOCKOUT.target: 0x3594,
}
GUARD_SECTION = ".service_guard"
SPLIT_MODEL_WINDOWS = ((0x020000, 0x030000), (0x07C118, 0x07FFFC))
MONITOR_STATE = (0x808578, 0x808DB4)
CONDITIONAL_STACK_AND_PSW = (0x809700, 0x80A000)


def verify_stock(rom, sites=SITES):
    for site in sites:
        if rom[site.address:site.address + 4] != pack(">I", site.stock):
            raise ValueError(f"Unexpected H03 service word at {site.address:#08x}")


def policy_ranges(blocks):
    if set(blocks) != {"control", "communication", "workspace"}:
        raise ValueError("Expected the three H03 candidate storage groups")
    ranges = sorted((*blocks.values(), MONITOR_STATE, CONDITIONAL_STACK_AND_PSW))
    previous_end = 0x804000
    for start, end in ranges:
        if not previous_end <= start < end <= 0x80A000:
            raise ValueError("Candidate service policy has an invalid or overlapping RAM interval")
        previous_end = end
    return ranges


def policy_source(ranges):
    entries = ",\n".join(f"        {{{start:#x}, {end:#x}}}" for start, end in ranges)
    return ('#include "lfj8_h03_service_guard.h"\n'
            'const Lfj8H03ServicePolicy rbm_h03_service_policy = {\n'
            f'    .count = {len(ranges)},\n    .ranges = {{\n{entries}\n    }}\n}};\n')


def stage_sources(stage, ranges):
    assembly = []
    for site in SITES:
        mnemonic = "bl.l" if site.opcode == 0xFE else "bra.l"
        assembly.extend((f'.section {site.section},"ax",@progbits',
                         f"    {mnemonic} {site.target}"))
    (stage / "service-sites.S").write_text("\n".join(assembly) + "\n", encoding="ascii")
    (stage / "service-policy.c").write_text(policy_source(ranges), encoding="ascii")


def linker_sections():
    sites = "\n".join(f"  {site.section} {site.address:#x} : {{ KEEP(*({site.section})) }}"
                      for site in SITES)
    guard = (f"  {GUARD_SECTION} : {{\n"
             "    service-hooks.o(.text .text.*)\n"
             "    service-guard.o(.text .text.* .rodata .rodata.*)\n"
             "    service-policy.o(.rodata .rodata.*)\n  }")
    return sites, guard


def linker_targets():
    return "\n".join(f"{name} = {address:#x};" for name, address in STOCK_TARGETS.items())


def verify_and_overlay(rom, elf_path, ranges):
    """Return simulator ROM bytes and verified placement metadata from the linked ELF."""
    verify_stock(rom)
    elf = read_elf(elf_path, 2)
    if any(section["type"] in (4, 9) and section["size"] for section in elf["sections"]):
        raise ValueError("H03 service ELF contains unresolved relocations")
    sections = sorted(alloc_sections(elf), key=lambda entry: entry["address"])
    by_name = {section["name"]: section for section in sections}
    symbols = elf["symbols"]
    if GUARD_SECTION not in by_name:
        raise ValueError("Linked H03 service guard is missing")
    guard = by_name[GUARD_SECTION]
    sites = {}
    for name, address in STOCK_TARGETS.items():
        if symbols.get(name, {}).get("address") != address:
            raise ValueError(f"Wrong H03 service continuation: {name}")
    for site in SITES:
        target = symbols.get(site.target, {})
        destination = target.get("address", -1)
        if site != LOCKOUT and (target.get("section") != guard["index"] or
                                not guard["address"] <= destination < guard["address"] + guard["size"]):
            raise ValueError(f"H03 service hook escaped the guard section: {site.target}")
        section = by_name.get(site.section, {})
        branch = site.branch(destination)
        if section.get("address") != site.address or section.get("data") != branch:
            raise ValueError(f"Wrong linked H03 service branch at {site.address:#08x}")
        sites[site.section] = {"address": hex(site.address), "original": f"{site.stock:08x}",
                               "model_patch": branch.hex(), "target": hex(destination)}

    policy = symbols.get("rbm_h03_service_policy", {})
    offset = policy.get("address", 0) - guard["address"]
    words = [len(ranges), *(address for pair in ranges for address in pair)]
    words.extend([0] * (17 - len(words)))  # ABI: count followed by eight interval pairs.
    expected = pack(">17I", *words)
    if (policy.get("section") != guard["index"] or policy.get("size") != len(expected) or
            offset < 0 or guard["data"][offset:offset + len(expected)] != expected):
        raise ValueError("Linked H03 service policy differs from the candidate RAM ranges")
    overlay = bytearray(rom)
    previous_end = 0
    for section in sections:
        start = section["address"]
        end = start + section["size"]
        if (previous_end > start or end > len(rom) or section["flags"] & 1 or
                section["type"] != 1):
            raise ValueError(f"Unsafe H03 model section: {section['name']}")
        if section["name"] not in sites and (
                not any(lo <= start < end <= hi for lo, hi in SPLIT_MODEL_WINDOWS) or
                rom[start:end] != b"\xff" * section["size"]):
            raise ValueError(f"H03 model section exceeds an erased candidate window: {section['name']}")
        overlay[start:end] = section["data"]
        previous_end = end
    report = {"elf_sha256": elf["sha256"], "guard_address": hex(guard["address"]),
              "guard_bytes": guard["size"], "policy_ranges": [[hex(a), hex(b)] for a, b in ranges],
              "sites": list(sites.values()), "target_ownership_verified": False,
              "requires_lower_rom_installation": True}
    return bytes(overlay), report
