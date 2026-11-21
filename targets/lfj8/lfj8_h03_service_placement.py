"""Link and validate the H03 service lockout in an address-model ELF."""

from dataclasses import dataclass
from struct import pack

from lfj8_h03_layout import Window, alloc_sections, pack as place, read_elf, symbol_bytes, verify_linked


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
DMA4_GUARD = Site(0xCF0C, 0x2E7F2A7F, "rbm_h03_dma4_guard")
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
COMMON_REDIRECTS = (
    (Site(0x3DBC, 0x604010A0, "rbm_h03_early_irq_gate"), "rbm_h03_early_irq_redirect"),
    (DMA4_GUARD, "rbm_h03_dma4_redirect"),
)
COMMON_WINDOWS = tuple(Window(name, site.address, site.address + 4) for site, name in COMMON_REDIRECTS)
COMMON_ROOTS = tuple(name for _, name in COMMON_REDIRECTS)
COMMON_STOCK_TARGETS = {
    "h03_dma4_after_entry": DMA4_GUARD.address + 4,
    "h03_early_irq_after_entry": COMMON_REDIRECTS[0][0].address + 4,
}


def redirect_sites(dma4_guard=False):
    return (*SITES, DMA4_GUARD) if dma4_guard else SITES


def stock_targets(dma4_guard=False):
    return dict(STOCK_TARGETS, h03_dma4_after_entry=DMA4_GUARD.address + 4) if dma4_guard else STOCK_TARGETS


def verify_stock(rom, sites=SITES):
    for site in sites:
        if rom[site.address:site.address + 4] != pack(">I", site.stock):
            raise ValueError(f"Unexpected H03 service word at {site.address:#08x}")


def policy_ranges(blocks, additional=()):
    if set(blocks) != {"control", "communication", "workspace"}:
        raise ValueError("Expected the three H03 candidate storage groups")
    ranges = sorted((*blocks.values(), *additional, MONITOR_STATE, CONDITIONAL_STACK_AND_PSW))
    if len(ranges) > 8:
        raise ValueError("Too many H03 service policy intervals")
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


def policy_bytes(ranges):
    words = [len(ranges), *(address for pair in ranges for address in pair)]
    return pack(">17I", *words, *([0] * (17 - len(words))))


def fixed_common_redirects(flash):
    remaining = {section["name"]: section for section in flash}
    fixed = []
    for name, window in zip(COMMON_ROOTS, COMMON_WINDOWS, strict=True):
        section = remaining.pop(f".text.{name}", None)
        if section is None or (section["size"], section["type"], section["flags"],
                               section["alignment"]) != (4, 1, 6, 4):
            raise ValueError("Expected one aligned H03 service redirect word: " + name)
        fixed.extend(place((section,), (window,)))
    return fixed, list(remaining.values())


def verify_common(rom, elf, ranges, irq_pointer):
    verify_stock(rom, (site for site, _ in COMMON_REDIRECTS))
    symbols = elf["symbols"]
    for name, address in {**COMMON_STOCK_TARGETS, "h03_dtc_irq_pointer": irq_pointer}.items():
        symbol = symbols.get(name, {})
        if (symbol.get("section"), symbol.get("address")) != (0xFFF1, address):
            raise ValueError("Incorrect H03 service continuation or RAM alias: " + name)
    pointer = symbols.get("irq_target", {})
    index = pointer.get("section", 0)
    if (pointer.get("address") != irq_pointer or pointer.get("size") != 4 or
            not 0 < index < len(elf["sections"])):
        raise ValueError("The early H03 store must clear the placed BasicCAN pointer")
    backing = elf["sections"][index]
    if (backing["type"], backing["flags"], backing["address"], backing["size"]) != (8, 3, irq_pointer, 4):
        raise ValueError("The early H03 pointer must be one NOLOAD word")
    if not any(start <= irq_pointer and irq_pointer + 4 <= end for start, end in ranges):
        raise ValueError("The H03 service policy must cover the BasicCAN pointer")
    if symbol_bytes(elf, "rbm_h03_service_policy") != policy_bytes(ranges):
        raise ValueError("Incorrect common H03 service policy bytes")
    patches = []
    for site, name in COMMON_REDIRECTS:
        hook = symbols[site.target]
        if not 0 < hook["section"] < len(elf["sections"]) or not elf["sections"][hook["section"]]["flags"] & 4:
            raise ValueError("H03 service redirect target is outside executable storage: " + name)
        target = hook["address"]
        if name == "rbm_h03_early_irq_redirect" and not 0x6000 <= target < 0x8000:
            raise ValueError("Early IRQ gate must be in resident Flash")
        branch = site.branch(target)
        if symbols[name]["address"] != site.address or symbol_bytes(elf, name) != branch:
            raise ValueError("Incorrect common H03 service redirect word: " + name)
        patches.append({"address": site.address, "stock": f"{site.stock:08x}",
                        "branch": branch.hex(), "target": target})
    return patches


def early_overlay(rom, elf_path, model):
    """Recover only the linked early IRQ/DMA4 simulator image."""
    import lfj8_h03_dtc_rx_placement as dtc_rx

    elf = read_elf(elf_path, 2, local_symbols=("irq_target",))
    if model["artifact_kind"] != "EARLY_IRQ_DMA4_SIMULATOR_ONLY" or elf["sha256"] != model["elf_sha256"]:
        raise ValueError("H03 early model ELF hash differs from its layout report")
    verify_linked(elf, model["placements"], model["roots"])
    patches = verify_common(rom, elf, model["policy_ranges"], model["irq_pointer"])
    dtc_rx.validate_stock(rom)
    can = dtc_rx.patch_plan(rom, {root: elf["symbols"][root]["address"]
                                 for _, root, _, _, _ in dtc_rx.REDIRECTS})
    dtc_rx.verify_redirects(elf, can)
    sites = {item["address"] for item in patches} | {item["site"] for item in can}
    result = bytearray(rom)
    end = 0
    for section in sorted(alloc_sections(elf), key=lambda s: s["address"]):
        if section["type"] == 8:
            continue
        start = section["address"]
        stop = start + section["size"]
        if start < end or stop > len(rom) or (start not in sites and rom[start:stop] != b"\xff" * section["size"]):
            raise ValueError("Early H03 model overlaps non-candidate ROM")
        result[start:stop] = section["data"]
        end = stop
    return bytes(result)


def stage_sources(stage, ranges, dma4_guard=False):
    assembly = []
    for site in redirect_sites(dma4_guard):
        mnemonic = "bl.l" if site.opcode == 0xFE else "bra.l"
        assembly.extend((f'.section {site.section},"ax",@progbits',
                         f"    {mnemonic} {site.target}"))
    (stage / "service-sites.S").write_text("\n".join(assembly) + "\n", encoding="ascii")
    (stage / "service-policy.c").write_text(policy_source(ranges), encoding="ascii")


def linker_sections(dma4_guard=False):
    sites = "\n".join(f"  {site.section} {site.address:#x} : {{ KEEP(*({site.section})) }}"
                      for site in redirect_sites(dma4_guard))
    dma4 = "    dma4-guard.o(.text .text.*)\n" if dma4_guard else ""
    guard = (f"  {GUARD_SECTION} : {{\n"
             "    service-hooks.o(.text .text.*)\n"
             f"{dma4}"
             "    service-guard.o(.text .text.* .rodata .rodata.*)\n"
             "    service-policy.o(.rodata .rodata.*)\n  }")
    return sites, guard


def linker_targets(dma4_guard=False):
    return "\n".join(f"{name} = {address:#x};" for name, address in stock_targets(dma4_guard).items())


def verify_and_overlay(rom, elf_path, ranges, dma4_guard=None):
    """Return simulator ROM bytes and verified placement metadata from the linked ELF."""
    elf = read_elf(elf_path, 2)
    if any(section["type"] in (4, 9) and section["size"] for section in elf["sections"]):
        raise ValueError("H03 service ELF contains unresolved relocations")
    sections = sorted(alloc_sections(elf), key=lambda entry: entry["address"])
    by_name = {section["name"]: section for section in sections}
    symbols = elf["symbols"]
    if dma4_guard is None:
        dma4_guard = DMA4_GUARD.section in by_name or DMA4_GUARD.target in symbols
    redirects = redirect_sites(dma4_guard)
    verify_stock(rom, redirects)
    if GUARD_SECTION not in by_name:
        raise ValueError("Linked H03 service guard is missing")
    guard = by_name[GUARD_SECTION]
    sites = {}
    for name, address in stock_targets(dma4_guard).items():
        if symbols.get(name, {}).get("address") != address:
            raise ValueError(f"Wrong H03 service continuation: {name}")
    for site in redirects:
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
    expected = policy_bytes(ranges)
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
              "dma4_guard_included": dma4_guard,
              "requires_lower_rom_installation": True}
    return bytes(overlay), report
