"""Absolute RAM bounds backed by the typed inventory and H03 reset words."""

from lfj8_h03_can_service_placement import referenced_aliases, typed_alias_ranges


STACK_STARTUP = {
    # Both entry paths load the same CR2/SPI value.
    0x0009E0: bytes.fromhex("e2809efc 12a2f000"),
    0x003DA4: bytes.fromhex("e2809efc 12a2f000 e3809f9c e0809f9c 2340f000"),
}
REQUIRED_QUALIFICATION = (
    "rbm_h03_ram_spi_first", "rbm_h03_ram_spi_reserve",
    "rbm_h03_ram_psw_first", "rbm_h03_ram_psw_reserve",
    "rbm_h03_boot_writers_owned",
)
MODULES = ("lfj8_h03_target_memory.c", "lfj8_h03_ram_owner.c")
APPLICATION_FIELDS = {
    "rbm_h03_takeover_state": "control/takeover",
    "rbm_h03_cycle_state": "control/cycle",
    "rbm_h03_runtime_state": "control/runtime",
    "rbm_h03_main_result": "communication/main_result",
    "rbm_h03_cycle_workspace": "workspace/toyota",
    "rbm_h03_cycle_input": "workspace/cycle_input",
}


def confirmed_ranges(rom, blocks):
    """Derive only the bounds used by the native RAM owner's descriptor."""
    for address, expected in STACK_STARTUP.items():
        if rom[address:address + len(expected)] != expected:
            raise ValueError(f"Unexpected H03 stack initialization at {address:#08x}")

    bounds = {}
    for name in ("control", "communication", "workspace"):
        block = blocks[name]
        bounds[f"rbm_h03_ram_{name}_first"] = block["address"]
        bounds[f"rbm_h03_ram_{name}_end"] = block["end_exclusive"]
    spi = int.from_bytes(rom[0x003DA5:0x003DA8], "big")
    cursor = int.from_bytes(rom[0x003DB1:0x003DB4], "big")
    bounds["rbm_h03_ram_spi_end"] = spi
    # Exclusive limit includes the cursor's own four-byte word.
    bounds["rbm_h03_ram_psw_end"] = cursor + 4
    return bounds


def application_addresses(storage):
    return {name: start for name, (start, _) in typed_alias_ranges(storage, APPLICATION_FIELDS).items()}


def bind(symbols, bounds, pinned):
    # The range API checks ABS values and rejects allocated or conflicting symbols.
    aliases = referenced_aliases(symbols, {name: (address, address)
                                           for name, address in bounds.items()}, pinned)
    if aliases.keys() != bounds.keys():
        missing = ", ".join(sorted(bounds.keys() - aliases.keys()))
        raise ValueError("Missing RAM owner or application references: " + missing)
    return aliases


def verify_linked(symbols, aliases):
    for name, address in aliases.items():
        symbol = symbols.get(name, {})
        if (symbol.get("section"), symbol.get("address")) != (0xFFF1, address):
            raise ValueError(f"Linked RAM owner bound differs from its verified absolute alias: {name}")
