"""Place and verify the fixed H03 TX13 redirect without producing a BIN."""

from lfj8_h03_layout import Window, pack, symbol_bytes
from lfj8_h03_sensor_hooks import branch_patch


SITE = 0x00C34C
STOCK = "2e7f2a7f"
RESUME = "h03_tx_writer_resume"
OWNER = "h03_can_owner"
GATE = "h03_can13_tx_gate"
REDIRECT = "h03_can13_tx_redirect"
OWNER_LOAD = "h03_can13_tx_owner_load"
REPLAY = "h03_can13_tx_replay"
RESUME_BRANCH = "h03_can13_tx_resume_branch"
REDIRECT_WINDOW = Window("tx13_redirect", SITE, SITE + 4)
MODULES = ("h03_can13_tx_gate.S", "h03_can13_tx_redirect.S")
ROOTS = (GATE, REDIRECT)


def validate_stock(rom):
    if rom[SITE:SITE + 4] != bytes.fromhex(STOCK):
        raise ValueError("Unexpected OEM H03 TX13 writer entry")


def fixed_redirect(flash):
    """Reserve exactly the occupied OEM word outside the erased packing space."""
    name = f".text.{REDIRECT}"
    matches = [s for s in flash if s["name"] == name]
    if len(matches) != 1 or tuple(matches[0][key] for key in ("size", "alignment", "type", "flags")) != (4, 4, 1, 6):
        raise ValueError("Expected one aligned executable H03 TX13 redirect word")
    return pack(matches, (REDIRECT_WINDOW,)), [s for s in flash if s["name"] != name]


def patch_plan(rom, gate):
    if gate < 0x008000 or gate + 4 > len(rom) or SITE <= gate < SITE + 4:
        raise ValueError("The H03 TX13 gate must be in application Flash outside its redirect")
    word = branch_patch(rom, SITE, gate, STOCK, 0xFF000000)
    return {"site": SITE, "stock_word": STOCK, "branch_word": f"{word:08x}",
            "hook": GATE, "target": gate, "redirect_symbol": REDIRECT}


def describe(rom, elf, placements, owner, *, linked):
    """Describe the provisional plan or verify bytes and bindings in a final ELF."""
    by_input = {p["section"]: p for p in placements}
    symbols = elf["symbols"]
    gate = symbols.get(GATE, {})
    placed = by_input.get(f".text.{GATE}")
    if placed is None or not 0 < gate.get("section", 0) < len(elf["sections"]):
        raise ValueError("Missing placed H03 TX13 gate")
    code = elf["sections"][gate["section"]]
    if code["flags"] != 6 or code["size"] != placed["bytes"] or code["size"] < 4:
        raise ValueError("H03 TX13 gate must be in its executable section")
    if linked:
        if code["address"] != placed["address"] or gate["address"] != placed["address"]:
            raise ValueError("H03 TX13 gate differs from the planned entry")
    elif code["name"] != placed["section"] or gate["address"] != 0:
        raise ValueError("H03 TX13 gate is not at the start of its retained section")

    plan = patch_plan(rom, placed["address"])
    report = {"status": "LINKED_ADDRESS_MODEL" if linked else "PROVISIONAL_UNLINKED",
              "installed": False, "elf_words_verified": False, "patch": plan,
              "oem_overlay_bytes": 4, "gate_bytes": placed["bytes"],
              "continuations": {RESUME: SITE + 4}, "can_owner_address": owner}
    if not linked:
        return report

    redirect = symbols.get(REDIRECT, {})
    redirect_section = redirect.get("section", 0)
    if (redirect.get("address") != SITE or not 0 < redirect_section < len(elf["sections"]) or
            symbol_bytes(elf, REDIRECT) != bytes.fromhex(plan["branch_word"])):
        raise ValueError("Final ELF H03 TX13 redirect differs from the OEM-site plan")
    entry = elf["sections"][redirect_section]
    if (entry["address"], entry["size"], entry["flags"]) != (SITE, 4, 6):
        raise ValueError("Final ELF H03 TX13 redirect must occupy one executable OEM word")
    for name, address in ((RESUME, SITE + 4), (OWNER, owner)):
        symbol = symbols.get(name, {})
        if (symbol.get("section"), symbol.get("address")) != (0xFFF1, address):
            raise ValueError(f"Invalid H03 TX13 native binding: {name}")
    if not 0x800000 <= owner < 0x1000000 or owner % 4:
        raise ValueError("Invalid typed H03 CAN owner address")

    for name in (OWNER_LOAD, REPLAY, RESUME_BRANCH):
        label = symbols.get(name, {})
        if label.get("section") != gate["section"] or label.get("address", 1) % 4:
            raise ValueError(f"H03 TX13 instruction is outside its aligned gate: {name}")
    replay = symbols[REPLAY]["address"]
    resume_branch = symbols[RESUME_BRANCH]["address"]
    displacement = ((SITE + 4) - resume_branch) // 4
    expected = {
        OWNER_LOAD: 0xE1000000 | owner,
        REPLAY: int(STOCK, 16),
        RESUME_BRANCH: 0xFF000000 | (displacement & 0xFFFFFF),
    }
    if resume_branch != replay + 4:
        raise ValueError("H03 TX13 return must immediately follow the displaced stock word")
    for name, word in expected.items():
        if symbol_bytes(elf, name) != word.to_bytes(4, "big"):
            raise ValueError(f"Invalid H03 TX13 linked instruction: {name}")

    report["elf_words_verified"] = True
    report["gate_words"] = {name: f"{value:08x}" for name, value in expected.items()}
    return report
