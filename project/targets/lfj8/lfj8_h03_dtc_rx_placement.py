"""Place the native BasicCAN observer below the H03 application boundary."""

from pathlib import Path

from lfj8_h03_layout import Window, alloc_sections, pack, read_elf, symbol_bytes
from lfj8_h03_sensor_hooks import branch_patch


RX_WINDOW = Window("dtc_rx_resident", 0x006000, 0x008000)
REDIRECTS = (
    (0x001534, "rbm_h03_dtc_rx_hook", "80c800ff", 0xFF000000, "rbm_h03_dtc_rx_redirect"),
    (0x004738, "rbm_h03_dtc_rx_dispatch_hook", "fefff32e", 0xFE000000, "rbm_h03_dtc_rx_dispatch_redirect"),
)
REDIRECT_WINDOWS = tuple(
    Window(redirect.removeprefix("rbm_h03_"), site, site + 4)
    for site, _, _, _, redirect in REDIRECTS
)
STOCK_SYMBOLS = {"h03_dtc_rx_resume": 0x001538, "h03_dtc_rx_entry": 0x0013F0}
RX_ROOTS = tuple(hook for _, hook, _, _, _ in REDIRECTS) + ("lfj8_h03_mmio", "lfj8_h03_tml0ct_m32r")
REDIRECT_ROOTS = tuple(redirect for _, _, _, _, redirect in REDIRECTS)
MODULES = ("h03_dtc_rx_hook.S", "h03_dtc_rx_redirects.S", "lfj8_h03_dtc_native.c")
IRQ_ADAPTER = ".text.native_rx_epoch"
POLL_ADAPTER = ".text.native_poll_owner"
OWNER_OPS = ".rodata.native_owner_ops"


def validate_stock(rom):
    for site, _, stock, _, _ in REDIRECTS:
        if rom[site:site + 4] != bytes.fromhex(stock):
            raise ValueError(f"Unexpected H03 DTC RX word at {site:#08x}")
    if (rom[0x0009D8:0x0009DC] != bytes.fromhex("00004724") or
            rom[0x000940:0x00094C] != bytes.fromhex("0000600000007ffe00008000")):
        raise ValueError("Unexpected H03 CAN0 vector or resident RX geometry")


def owner_address(storage):
    block = storage["blocks"]["communication"]
    field = storage["fields"]["communication/can_owner"]
    start = block["address"] + field["offset"]
    end = start + field["bytes"]
    if (not block["address"] <= start < end <= block["end_exclusive"] or
            start % field["alignment"]):
        raise ValueError("The H03 CAN owner is outside its typed communication block")
    return start


def closure_sections(run, gcc, flags, stage):
    """Retain the direct IRQ graph and root its otherwise indirect RX entry."""
    script = Path(stage) / "dtc-rx-closure.ld"
    script.write_text(f'SECTIONS {{ {IRQ_ADAPTER} : {{ KEEP(*({IRQ_ADAPTER})) }} }}\n',
                      encoding="ascii")
    roots = [f"-Wl,--undefined={root}" for root in RX_ROOTS]
    run(gcc, *flags, "-r", "-nostdlib", "-Wl,--gc-sections,-T,dtc-rx-closure.ld",
        *roots, "retained.o", "-o", "dtc-rx-closure.o")
    elf = read_elf(Path(stage) / "dtc-rx-closure.o", 1)
    unresolved = {name for name, symbol in elf["symbols"].items() if symbol["section"] == 0}
    unexpected = unresolved - (STOCK_SYMBOLS.keys() | {"rbm_h03_tml0_1mhz_qualified"})
    if unexpected:
        raise ValueError(f"Unrecognized resident RX dependencies: {sorted(unexpected)}")
    if any(elf["symbols"].get(root, {}).get("section", 0) == 0 for root in RX_ROOTS):
        raise ValueError("Missing native BasicCAN closure root")
    sections = alloc_sections(elf)
    writable = {s["name"] for s in sections if s["flags"] & 1}
    if writable != {".bss.irq_target"}:
        raise ValueError(f"Unexpected resident RX RAM dependencies: {sorted(writable)}")
    names = {s["name"] for s in sections if not s["flags"] & 1}
    if IRQ_ADAPTER not in names or POLL_ADAPTER in names or OWNER_OPS in names:
        raise ValueError("The RX closure must reach the epoch adapter independently of foreground")
    # Keep the table itself low without pulling its foreground poll pointer down.
    return names | {OWNER_OPS}


def fixed_redirects(flash):
    remaining = {section["name"]: section for section in flash}
    fixed = []
    for redirect, window in zip(REDIRECT_ROOTS, REDIRECT_WINDOWS, strict=True):
        section = remaining.pop(f".text.{redirect}", None)
        if section is None or (section["size"], section["type"], section["flags"],
                               section["alignment"]) != (4, 1, 6, 4):
            raise ValueError(f"Expected one aligned executable H03 DTC RX word: {redirect}")
        fixed.extend(pack((section,), (window,)))
    return fixed, list(remaining.values())


def split_flash(flash, resident_names):
    resident, upper = [], []
    missing = resident_names - {s["name"] for s in flash}
    if missing:
        raise ValueError(f"Readonly IRQ sections missing from combined link: {sorted(missing)}")
    for section in flash:
        group = resident if section["name"] in resident_names else upper
        group.append(section)
    return resident, upper


def patch_plan(rom, addresses):
    result = []
    for site, hook, stock, opcode, redirect in REDIRECTS:
        target = addresses.get(hook)
        if target is None or not RX_WINDOW.start <= target < RX_WINDOW.end:
            raise ValueError(f"H03 DTC RX redirect must lead below the application: {hook}")
        word = branch_patch(rom, site, target, stock, opcode)
        result.append({"site": site, "stock_word": stock, "branch_word": f"{word:08x}",
                       "hook": hook, "target": target, "redirect_symbol": redirect})
    return result


def verify_redirects(elf, patches):
    for patch in patches:
        name = patch["redirect_symbol"]
        symbol = elf["symbols"].get(name, {})
        if (symbol.get("address") != patch["site"] or
                symbol_bytes(elf, name) != bytes.fromhex(patch["branch_word"])):
            raise ValueError(f"Final ELF H03 DTC RX redirect differs from the OEM-site plan: {name}")


def describe(rom, elf, placements, owner, *, linked):
    by_input = {p["section"]: p for p in placements}
    symbols = elf["symbols"]
    addresses = {}
    for _, hook, _, _, _ in REDIRECTS:
        symbol = symbols.get(hook, {})
        if not 0 < symbol.get("section", 0) < len(elf["sections"]):
            raise ValueError(f"Missing placed H03 DTC RX hook: {hook}")
        code = elf["sections"][symbol["section"]]
        if not code["flags"] & 4:
            raise ValueError(f"H03 DTC RX hook is outside executable storage: {hook}")
        address = symbol["address"]
        if not linked:
            if code["name"] not in by_input or address >= code["size"]:
                raise ValueError(f"H03 DTC RX hook is outside its retained section: {hook}")
            address += by_input[code["name"]]["address"]
        addresses[hook] = address

    resident = [p for p in placements if p["window"] == RX_WINDOW.name]
    patches = patch_plan(rom, addresses)
    report = {"status": "LINKED_ADDRESS_MODEL" if linked else "PROVISIONAL_UNLINKED",
              "installed": False, "elf_words_verified": False, "patches": patches,
              "oem_overlay_bytes": sum(window.end - window.start for window in REDIRECT_WINDOWS),
              "continuations": STOCK_SYMBOLS,
              "can_owner_address": owner, "readonly_sections": [p["section"] for p in resident],
              "resident_bytes": sum(p["bytes"] for p in resident),
              "resident_extent": max(p["address"] + p["bytes"] for p in resident) - RX_WINDOW.start}
    if linked:
        verify_redirects(elf, patches)
        report["elf_words_verified"] = True

        def in_input(address, name):
            item = by_input[name]
            return item["address"] <= address < item["address"] + item["bytes"]

        for name, address in {**STOCK_SYMBOLS, "h03_can_owner": owner}.items():
            symbol = symbols.get(name, {})
            if symbol.get("section") != 0xFFF1 or symbol.get("address") != address:
                raise ValueError(f"Invalid resident RX native binding: {name}")
        ops = by_input[OWNER_OPS]
        ops_data = next((s["data"] for s in elf["sections"] if s["address"] == ops["address"] and s["size"]), b"")
        if len(ops_data) != 12:
            raise ValueError("Unexpected M32R CAN owner operations table size")
        epoch, poll, context = (int.from_bytes(ops_data[i:i + 4], "big") for i in (0, 4, 8))
        if (not in_input(epoch, IRQ_ADAPTER) or not in_input(poll, POLL_ADAPTER) or
                by_input[POLL_ADAPTER]["window"] == RX_WINDOW.name or context != owner):
            raise ValueError("Incorrect placement or binding of native CAN owner operations")
        mmio = symbol_bytes(elf, "lfj8_h03_mmio")
        if len(mmio) != 28 or any(not RX_WINDOW.start <= int.from_bytes(mmio[i:i + 4], "big") < RX_WINDOW.end
                                  for i in range(4, 28, 4)):
            raise ValueError("An indirect RX MMIO entry is outside the resident window")
        report["indirect_targets_verified"] = True
    return report
