"""Fixed native application redirects for the pinned LFJ8-18-9E1C H03."""

from dataclasses import dataclass

from lfj8_h03_layout import Window
from lfj8_h03_sensor_hooks import branch_patch


@dataclass(frozen=True)
class Redirect:
    address: int
    stock_word: str
    hook: str
    opcode: int

    @property
    def section(self):
        return f".h03_app_redirect_{self.address:06x}"

    @property
    def root(self):
        return f"rbm_h03_application_redirect_{self.address:06x}"


REDIRECTS = (
    Redirect(0x008100, "2e7f4ffc", "rbm_h03_application_cold_hook", 0xFF000000),
    Redirect(0x00814C, "fe0009bb", "rbm_h03_phase_startup_hook", 0xFE000000),
    Redirect(0x00816C, "fe00e06e", "rbm_h03_application_foreground_hook", 0xFE000000),
    Redirect(0x040424, "7e11f000", "rbm_h03_phase_release_hook", 0xFE000000),
)
STOCK_SYMBOLS = {
    "h03_stock_application_after_entry": 0x008104,
    "h03_stock_startup_record": 0x00A838,
    "h03_stock_foreground_inputs": 0x040324,
    "h03_stock_phase_release": 0x040468,
}
REDIRECT_WINDOWS = tuple(Window(site.section, site.address, site.address + 4) for site in REDIRECTS)


def assembly(rom, redirects=REDIRECTS):
    """Emit linked instructions, with a relocation to each native wrapper."""
    parts = []
    for site in redirects:
        branch_patch(rom, site.address, site.address, site.stock_word, site.opcode)
        mnemonic = "bl.l" if site.opcode == 0xFE000000 else "bra.l"
        parts.extend((f'    .section {site.section},"ax",@progbits', "    .p2align 2",
                      f"    .global {site.root}", f"    .type {site.root},@function",
                      f"{site.root}:", f"    {mnemonic} {site.hook}",
                      f"    .size {site.root},.-{site.root}"))
    return "\n".join(parts) + "\n"


def fixed_redirects(flash):
    """Place the four words at OEM addresses before packing regular Flash."""
    windows = {window.name: window for window in REDIRECT_WINDOWS}
    redirects = [section for section in flash if section["name"] in windows]
    if {section["name"] for section in redirects} != windows.keys() or len(redirects) != len(windows):
        raise ValueError("Expected exactly one section for each H03 application redirect")

    fixed = []
    for section in redirects:
        if (section["type"], section["size"], section["alignment"], section["flags"]) != (1, 4, 4, 6):
            raise ValueError(f"Invalid H03 application redirect section: {section['name']}")
        window = windows[section["name"]]
        fixed.append({"section": section["name"], "window": window.name, "address": window.start,
                      "bytes": section["size"], "alignment": section["alignment"],
                      "noload": False, "flags": section["flags"]})
    return sorted(fixed, key=lambda item: item["address"]), [
        section for section in flash if section["name"] not in windows]


def verify_linked(rom, elf, code_windows):
    """Validate the exact linked words and stock continuations before overlay."""
    sections = {}
    for section in elf["sections"]:
        if section.get("flags", 0) & 2:
            sections.setdefault(section["address"], []).append(section)
    symbols = elf["symbols"]
    for name, address in STOCK_SYMBOLS.items():
        symbol = symbols.get(name, {})
        if (symbol.get("section"), symbol.get("address")) != (0xFFF1, address):
            raise ValueError(f"Unexpected H03 application continuation: {name}")

    patches = []
    for site in REDIRECTS:
        located = sections.get(site.address, [])
        section = located[0] if len(located) == 1 else {}
        symbol = symbols.get(site.hook, {})
        index = symbol.get("section", 0)
        target = symbol.get("address", -1)
        if not 0 < index < len(elf["sections"]):
            raise ValueError(f"Missing linked H03 application hook: {site.hook}")
        code = elf["sections"][index]
        if (code["type"] != 1 or code["flags"] & 7 != 6 or
                not code["address"] <= target < code["address"] + code["size"] or
                not any(window.start <= target < window.end for window in code_windows)):
            raise ValueError(f"H03 application hook escaped executable Flash: {site.hook}")
        word = branch_patch(rom, site.address, target, site.stock_word, site.opcode)
        if (section.get("address"), section.get("type"), section.get("flags", 0) & 7,
            section.get("data")) != (site.address, 1, 6, word.to_bytes(4, "big")):
            raise ValueError(f"Incorrect linked H03 application redirect at {site.address:#x}")
        patches.append({"address": site.address, "stock_word": site.stock_word,
                        "branch_word": f"{word:08x}", "hook": site.hook, "target": target})
    return patches
